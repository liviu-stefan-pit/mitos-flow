"""Cursor CLI Skill runner — spawn + capture (Phase 23)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from mitos_api.domain.cursor import (
    CursorFeatureFlags,
    CursorRunOptions,
    DEFAULT_CURSOR_TIMEOUT_MS,
)
from mitos_api.services.cursor.command_builder import (
    CursorCommandBuildError,
    build_cursor_command,
    get_workspace_root,
)
from mitos_api.services.cursor.executor import (
    CursorExecutionError,
    SpawnCommand,
    spawn_cursor_command,
)
from mitos_api.services.cursor.probe import get_cursor_capability
from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult


class CursorRunner:
    """
    Spawns the Cursor CLI for each Skill execution request.

    Builds argv+stdin via Phase 22 command builder, then captures stdout,
    stderr, exit status, elapsed time, and best-effort usage metadata.
    """

    def __init__(
        self,
        *,
        executable: str,
        features: CursorFeatureFlags | None = None,
        workspace: str | Path | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_ms: int = DEFAULT_CURSOR_TIMEOUT_MS,
        force: bool = False,
        trust: bool = True,
        output_format: str = "text",
        allowed_root: str | Path | None = None,
        environ: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
        spawn: SpawnCommand | None = None,
    ) -> None:
        if not (executable or "").strip():
            raise CursorCommandBuildError(
                "Cursor CLI executable is required.",
                code="executable_missing",
            )
        self.executable = executable.strip()
        self.features = features or CursorFeatureFlags()
        env = environ if environ is not None else os.environ
        self.environ = env
        self.cwd = cwd
        if workspace is not None and str(workspace).strip():
            self.workspace = str(workspace).strip()
        else:
            self.workspace = str(get_workspace_root(environ=env, cwd=cwd))
        self.model = model
        self.api_key = api_key
        self.timeout_ms = timeout_ms
        self.force = force
        self.trust = trust
        self.output_format = output_format
        self.allowed_root = allowed_root
        self._spawn = spawn
        self.cleaned_up: list[str] = []
        self.last_process = None

    @classmethod
    def from_options(
        cls,
        options: CursorRunOptions | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        cwd: str | Path | None = None,
        spawn: SpawnCommand | None = None,
    ) -> CursorRunner:
        """Resolve executable/features from options or the capability probe."""
        env = environ if environ is not None else os.environ
        opts = options or CursorRunOptions()

        executable = (opts.executable or "").strip() or None
        features = opts.features
        if executable is None or features is None:
            report = get_cursor_capability(environ=env)
            if report.executable:
                executable = executable or report.executable
            features = features or report.features
            if report.status.value != "available" and not opts.executable:
                raise CursorCommandBuildError(
                    report.message or "Cursor CLI is not available.",
                    code="cursor_unavailable",
                )

        if not executable:
            raise CursorCommandBuildError(
                "Cursor CLI executable not resolved. Set MITOS_CURSOR_CLI or "
                "pass cursor.executable.",
                code="executable_missing",
            )

        api_key = (opts.apiKey or "").strip() or None
        if api_key is None:
            api_key = (env.get("CURSOR_API_KEY") or "").strip() or None

        workspace = (opts.workspace or "").strip() or None

        return cls(
            executable=executable,
            features=features,
            workspace=workspace,
            model=opts.model,
            api_key=api_key,
            timeout_ms=opts.timeoutMs,
            force=opts.force,
            trust=opts.trust,
            output_format=opts.outputFormat,
            environ=env,
            cwd=cwd,
            spawn=spawn,
        )

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        try:
            built = build_cursor_command(
                request,
                executable=self.executable,
                workspace=self.workspace,
                features=self.features,
                model=self.model,
                api_key=self.api_key,
                timeout_ms=self.timeout_ms,
                force=self.force,
                trust=self.trust,
                output_format=self.output_format,
                allowed_root=self.allowed_root,
                environ=self.environ,
                cwd=self.cwd,
            )
        except CursorCommandBuildError:
            raise

        process = spawn_cursor_command(built, spawn=self._spawn)
        self.last_process = process

        if process.exit_code != 0:
            detail = (process.stderr or process.stdout or "").strip()
            message = (
                f"Cursor CLI exited with code {process.exit_code}"
                + (f": {detail}" if detail else "")
            )
            raise CursorExecutionError(
                message,
                exit_code=process.exit_code,
                stdout=process.stdout,
                stderr=process.stderr,
                elapsed_ms=process.elapsed_ms,
            )

        output = process.stdout.rstrip("\r\n")
        if not output and process.stderr.strip():
            # Some CLIs write the answer to stderr in headless mode.
            output = process.stderr.rstrip("\r\n")

        return SkillExecutionResult(
            outputPayload=output,
            mediaType="text/plain",
            stdout=process.stdout,
            stderr=process.stderr,
            exitCode=process.exit_code,
            elapsedMs=process.elapsed_ms,
            usage=process.usage,
        )

    def cleanup(self, skill_node_id: str) -> None:
        """Record cleanup for tests (cancel / timeout / success hooks)."""
        self.cleaned_up.append(skill_node_id)
