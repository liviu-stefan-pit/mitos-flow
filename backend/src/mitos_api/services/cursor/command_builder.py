"""Cursor CLI command builder and dry-run preview (Phase 22).

Converts a ``SkillExecutionRequest`` into argv + stdin **without spawning**.
Applies workspace boundary checks, secret redaction, and Windows quoting for
the preview surface. Phase 23 will spawn from the unredacted build.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mitos_api.domain.cursor import (
    CursorCommandPreview,
    CursorDryRunOptions,
    CursorDryRunRequest,
    CursorDryRunResponse,
    CursorFeatureFlags,
    CursorSkillPayload,
    DEFAULT_CURSOR_TIMEOUT_MS,
)
from mitos_api.domain.workflow import (
    AttachedRule,
    CitedChunk,
    DEFAULT_CURSOR_SKILL_MODEL,
    InputEnvelope,
)
from mitos_api.services.cursor.probe import (
    get_cursor_capability,
)
from mitos_api.services.runners.base import SkillExecutionRequest

# Env override for the approved workspace root (boundary).
_ENV_WORKSPACE_ROOT = "MITOS_CURSOR_WORKSPACE_ROOT"

# Values following these flags are redacted in previews.
_SECRET_FLAGS = frozenset({"--api-key"})

_REDACTION_TOKEN = "***"


@dataclass(frozen=True)
class BuiltCursorCommand:
    """Unredacted argv + stdin ready for a future spawn (Phase 23)."""

    argv: list[str]
    stdin: str
    timeout_ms: int
    workspace: str
    executable: str


class CursorCommandBuildError(ValueError):
    """Raised when the command cannot be built safely."""

    def __init__(self, message: str, *, code: str = "build_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def get_workspace_root(
    *,
    environ: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """Return the approved workspace root for boundary checks."""
    env = environ if environ is not None else os.environ
    override = (env.get(_ENV_WORKSPACE_ROOT) or "").strip()
    if override:
        return Path(override).expanduser().resolve(strict=False)
    base = Path(cwd) if cwd is not None else Path.cwd()
    return base.resolve(strict=False)


def check_workspace_boundary(
    workspace: str | Path,
    *,
    allowed_root: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """
    Resolve ``workspace`` and ensure it stays under the approved root.

    Rejects path traversal (``..`` escapes) and absolute paths outside the root.
    """
    root = (
        Path(allowed_root).resolve(strict=False)
        if allowed_root is not None
        else get_workspace_root(environ=environ, cwd=cwd)
    )
    raw = Path(workspace).expanduser()
    try:
        resolved = raw.resolve(strict=False)
    except OSError as exc:
        raise CursorCommandBuildError(
            f"Could not resolve workspace path: {exc}",
            code="workspace_invalid",
        ) from exc

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CursorCommandBuildError(
            f"Workspace '{resolved}' is outside the approved root '{root}'.",
            code="workspace_boundary",
        ) from exc

    return resolved


def quote_windows_arg(arg: str) -> str:
    """
    Quote a single argument for a Windows command line.

    Mirrors ``subprocess.list2cmdline`` rules for one token so unit tests can
    assert escaping of spaces, quotes, and backslashes independently of argv
    joining.
    """
    if not arg:
        return '""'
    if re.search(r'[\s"]', arg) is None:
        return arg

    result: list[str] = ['"']
    num_backslashes = 0
    for char in arg:
        if char == "\\":
            num_backslashes += 1
            continue
        if char == '"':
            result.append("\\" * (num_backslashes * 2 + 1))
            result.append('"')
            num_backslashes = 0
            continue
        if num_backslashes:
            result.append("\\" * num_backslashes)
            num_backslashes = 0
        result.append(char)
    if num_backslashes:
        # Trailing backslashes before the closing quote must be doubled.
        result.append("\\" * (num_backslashes * 2))
    result.append('"')
    return "".join(result)


def quote_windows_command(argv: Sequence[str]) -> str:
    """Join argv into a Windows-safe display / CreateProcess command line."""
    return subprocess.list2cmdline(list(argv))


def redact_argv(argv: Sequence[str]) -> list[str]:
    """Copy argv with secret flag values replaced by ``***``."""
    redacted: list[str] = []
    hide_next = False
    for item in argv:
        if hide_next:
            redacted.append(_REDACTION_TOKEN)
            hide_next = False
            continue
        if item in _SECRET_FLAGS:
            redacted.append(item)
            hide_next = True
            continue
        # Support --api-key=secret form
        matched = False
        for flag in _SECRET_FLAGS:
            prefix = f"{flag}="
            if item.startswith(prefix):
                redacted.append(f"{prefix}{_REDACTION_TOKEN}")
                matched = True
                break
        if not matched:
            redacted.append(item)
    return redacted


def redact_text_secrets(text: str, secrets: Sequence[str]) -> str:
    """Replace known secret substrings in free-form preview text."""
    result = text
    for secret in secrets:
        if secret:
            result = result.replace(secret, _REDACTION_TOKEN)
    return result


def assemble_prompt(request: SkillExecutionRequest | CursorSkillPayload) -> str:
    """Build the stdin / prompt body from a Skill or prompted-output request."""
    prompt_template = (getattr(request, "promptTemplate", None) or "").strip()
    if prompt_template:
        # Phase 27: prompted Artifact Output — explicit projection call.
        sections: list[str] = [
            f"# Prompted projection: {request.skillLabel}",
            "## Prompt template",
            prompt_template,
            "## Upstream data",
            _format_inputs(request),
            "## Instructions\n"
            "Apply the prompt template to the upstream data. Reply with the "
            "projected artifact only.",
        ]
        return "\n\n".join(sections).strip() + "\n"

    sections = [
        f"# Skill: {request.skillLabel}",
    ]
    description = (request.description or "").strip()
    if description:
        sections.append("## Description")
        sections.append(description)

    content = (getattr(request, "content", None) or "").strip()
    if content:
        # Phase 28.5: applied SKILL.md body (Instructions body, not the
        # closing operational directive below).
        sections.append("## Instructions")
        sections.append(content)

    if request.rules:
        sections.append("## Rules")
        sections.extend(_format_rules(list(request.rules)))

    if request.knowledgeChunks:
        sections.append("## Knowledge")
        sections.extend(_format_kb_chunks(list(request.knowledgeChunks)))

    sections.append("## Input")
    sections.append(_format_inputs(request))

    sections.append(
        "## Task\n"
        "Follow the skill description, instructions, and rules. Use only the "
        "provided input and knowledge. Reply with the skill result only."
    )
    return "\n\n".join(sections).strip() + "\n"


def _format_rules(rules: list[AttachedRule]) -> list[str]:
    parts: list[str] = []
    for rule in rules:
        label = rule.label or rule.rulesNodeId
        content = (rule.content or "").strip()
        parts.append(f"### {label}\n{content}" if content else f"### {label}")
    return parts


def _format_kb_chunks(chunks: list[CitedChunk]) -> list[str]:
    parts: list[str] = []
    for chunk in chunks:
        header = f"### {chunk.citation} (`{chunk.chunkId}`)"
        text = (chunk.text or "").strip()
        parts.append(f"{header}\n{text}" if text else header)
    return parts


def _format_inputs(request: SkillExecutionRequest | CursorSkillPayload) -> str:
    if len(request.inputs) > 1:
        blocks: list[str] = []
        for envelope in sorted(request.inputs, key=lambda item: item.port):
            blocks.append(_format_envelope(envelope))
        return "\n\n".join(blocks)
    if request.inputs:
        return _format_envelope(request.inputs[0])
    payload = request.inputPayload or ""
    media = request.inputMediaType or "text/plain"
    return f"(mediaType: {media})\n{payload}"


def _format_envelope(envelope: InputEnvelope) -> str:
    return (
        f"### Port `{envelope.port}` "
        f"(from {envelope.sourceNodeId}, mediaType: {envelope.mediaType})\n"
        f"{envelope.payload}"
    )


def build_cursor_command(
    request: SkillExecutionRequest | CursorSkillPayload,
    *,
    executable: str,
    workspace: str | Path,
    features: CursorFeatureFlags | None = None,
    model: str | None = None,
    api_key: str | None = None,
    timeout_ms: int = DEFAULT_CURSOR_TIMEOUT_MS,
    force: bool = False,
    trust: bool = True,
    output_format: str = "text",
    allowed_root: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
) -> BuiltCursorCommand:
    """
    Convert a Skill request into argv + stdin without spawning.

    Flags are included only when advertised in ``features`` (from the Phase 21
    probe). The prompt body is placed on **stdin**; argv carries flags only so
    Windows command-line length limits are avoided.
    """
    if not (executable or "").strip():
        raise CursorCommandBuildError(
            "Cursor CLI executable is required.",
            code="executable_missing",
        )
    if timeout_ms <= 0:
        raise CursorCommandBuildError(
            "timeoutMs must be a positive integer.",
            code="timeout_invalid",
        )

    flags = features or CursorFeatureFlags()
    resolved_workspace = check_workspace_boundary(
        workspace,
        allowed_root=allowed_root,
        environ=environ,
        cwd=cwd,
    )

    argv: list[str] = [executable.strip()]

    if flags.printMode:
        argv.append("--print")

    if flags.outputFormat:
        fmt = (output_format or "text").strip() or "text"
        argv.extend(["--output-format", fmt])

    if flags.workspace:
        argv.extend(["--workspace", str(resolved_workspace)])

    if flags.trust and trust:
        argv.append("--trust")

    if flags.force and force:
        argv.append("--force")

    # Phase 24.5: always pass --model when a model id is provided so the CLI
    # never silently falls through to expensive ``auto``.
    if model and model.strip():
        argv.extend(["--model", model.strip()])

    if flags.apiKey and api_key and api_key.strip():
        argv.extend(["--api-key", api_key.strip()])

    stdin = assemble_prompt(request)

    return BuiltCursorCommand(
        argv=argv,
        stdin=stdin,
        timeout_ms=timeout_ms,
        workspace=str(resolved_workspace),
        executable=executable.strip(),
    )


def preview_built_command(
    built: BuiltCursorCommand,
    *,
    secrets: Sequence[str] = (),
) -> CursorCommandPreview:
    """Build a redacted, Windows-quoted preview from an unredacted command."""
    redacted_argv = redact_argv(built.argv)
    display = quote_windows_command(redacted_argv)
    stdin_preview = redact_text_secrets(built.stdin, secrets)
    return CursorCommandPreview(
        argv=redacted_argv,
        commandDisplay=display,
        stdin=built.stdin,
        stdinPreview=stdin_preview,
        timeoutMs=built.timeout_ms,
        workspace=built.workspace,
        executable=built.executable,
    )


def dry_run_cursor_command(
    body: CursorDryRunRequest,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    capability_executable: str | None = None,
    capability_features: CursorFeatureFlags | None = None,
) -> CursorDryRunResponse:
    """
    Public dry-run entry: build argv+stdin, redact, enforce confirmation gate.

    Does **not** spawn the Cursor CLI.
    """
    env = environ if environ is not None else os.environ
    options = body.options or CursorDryRunOptions()
    errors: list[str] = []

    executable = (options.executable or "").strip() or None
    features = options.features

    if executable is None or features is None:
        if capability_executable is not None and capability_features is not None:
            executable = executable or capability_executable
            features = features or capability_features
        else:
            report = get_cursor_capability(environ=env)
            if report.executable:
                executable = executable or report.executable
            features = features or report.features
            if report.status.value != "available" and not options.executable:
                errors.append(report.message)

    if not executable:
        errors.append(
            "Cursor CLI executable not resolved. Set MITOS_CURSOR_CLI or "
            "pass options.executable."
        )
        return CursorDryRunResponse(
            ok=False,
            errors=errors,
            confirmationRequired=True,
            confirmed=False,
            message="Cannot build Cursor command until the CLI is available.",
            spawned=False,
        )

    features = features or CursorFeatureFlags()

    workspace = (options.workspace or "").strip()
    if not workspace:
        workspace = str(get_workspace_root(environ=env, cwd=cwd))

    api_key = (options.apiKey or "").strip() or None
    if api_key is None:
        api_key = (env.get("CURSOR_API_KEY") or "").strip() or None

    # Phase 24.5: dry-run defaults to composer-2.5 so preview never omits --model.
    model = (options.model or "").strip() or DEFAULT_CURSOR_SKILL_MODEL

    try:
        built = build_cursor_command(
            body.request,
            executable=executable,
            workspace=workspace,
            features=features,
            model=model,
            api_key=api_key,
            timeout_ms=options.timeoutMs,
            force=options.force,
            trust=options.trust,
            output_format=options.outputFormat,
            environ=env,
            cwd=cwd,
        )
    except CursorCommandBuildError as exc:
        return CursorDryRunResponse(
            ok=False,
            errors=[exc.message],
            confirmationRequired=True,
            confirmed=False,
            message=exc.message,
            spawned=False,
        )

    secrets = [s for s in (api_key,) if s]
    preview = preview_built_command(built, secrets=secrets)

    confirmed = bool(options.confirmed)
    if not confirmed:
        return CursorDryRunResponse(
            ok=True,
            errors=[],
            preview=preview,
            confirmationRequired=True,
            confirmed=False,
            message=(
                "Review the redacted command preview, then confirm and run "
                "with options.runner='cursor' (Phase 23)."
            ),
            spawned=False,
        )

    return CursorDryRunResponse(
        ok=True,
        errors=[],
        preview=preview,
        confirmationRequired=True,
        confirmed=True,
        message=(
            "Command preview confirmed. Start a run with "
            "options.runner='cursor' and options.cursor.confirmed=true "
            "to spawn the Cursor CLI."
        ),
        spawned=False,
    )
