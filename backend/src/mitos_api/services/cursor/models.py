"""Cursor CLI model listing via ``agent --list-models`` (Phase 24.5).

Read-only: never runs user prompts. Filters out ``auto``. Always ensures
``composer-2.5`` is present so the Skill inspector has a cheap default.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from mitos_api.domain.cursor import (
    CursorModelInfo,
    CursorModelsReport,
    CursorModelsStatus,
)
from mitos_api.domain.workflow import DEFAULT_CURSOR_SKILL_MODEL
from mitos_api.services.cursor.probe import (
    CommandResult,
    RunCommand,
    WhichCommand,
    resolve_cursor_executable,
)

_LIST_MODELS_TIMEOUT_SEC = 8.0

# Lines like: "composer-2.5" or "composer-2.5 - Composer 2.5" or "gpt-5.2 (default)"
_MODEL_LINE_RE = re.compile(
    r"^\s*(?P<id>[A-Za-z0-9][A-Za-z0-9._+-]*)"
    r"(?:\s*[-–—:]\s*(?P<label>.+?))?"
    r"(?:\s*\([^)]*\))?\s*$"
)

_SKIP_PREFIXES = (
    "available models",
    "models:",
    "usage:",
    "options:",
    "name",
    "id",
    "---",
)


def _default_run_command(argv: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        timeout=_LIST_MODELS_TIMEOUT_SEC,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def parse_list_models_output(raw: str) -> list[CursorModelInfo]:
    """
    Parse ``agent --list-models`` stdout/stderr into model entries.

    Skips ``auto``. Deduplicates by id (first wins). Does not invent models
    beyond what appears in the text (caller may hard-append the default).
    """
    seen: set[str] = set()
    models: list[CursorModelInfo] = []
    text = raw or ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if any(lower.startswith(prefix) for prefix in _SKIP_PREFIXES):
            continue
        # Table / bullet noise
        if stripped.startswith("|") or stripped.startswith("*"):
            stripped = stripped.lstrip("|*- ").strip()
        match = _MODEL_LINE_RE.match(stripped)
        if not match:
            continue
        model_id = match.group("id").strip()
        if not model_id:
            continue
        if model_id.lower() == "auto":
            continue
        if model_id.lower() in seen:
            continue
        seen.add(model_id.lower())
        label_raw = (match.group("label") or "").strip()
        label = label_raw if label_raw else model_id
        models.append(CursorModelInfo(id=model_id, label=label))
    return models


def ensure_default_model(
    models: list[CursorModelInfo],
    *,
    default_id: str = DEFAULT_CURSOR_SKILL_MODEL,
) -> list[CursorModelInfo]:
    """Hard-append the default model when missing from the parsed list."""
    if any(m.id.lower() == default_id.lower() for m in models):
        return list(models)
    return [
        *models,
        CursorModelInfo(id=default_id, label=default_id),
    ]


def list_cursor_models(
    *,
    environ: Mapping[str, str] | None = None,
    which: WhichCommand | None = None,
    run_command: RunCommand | None = None,
) -> CursorModelsReport:
    """
    Run ``agent --list-models`` and return a filtered catalog.

    Never passes a user prompt. On absence/error, still returns a catalog
    containing at least ``composer-2.5``.
    """
    run = run_command or _default_run_command
    executable = resolve_cursor_executable(environ=environ, which=which)
    default_catalog = ensure_default_model([])

    if not executable:
        return CursorModelsReport(
            status=CursorModelsStatus.ABSENT,
            models=default_catalog,
            defaultModel=DEFAULT_CURSOR_SKILL_MODEL,
            message=(
                "Cursor CLI not found. Using default model "
                f"{DEFAULT_CURSOR_SKILL_MODEL}; install the agent CLI to "
                "refresh the live list."
            ),
        )

    try:
        result = run([executable, "--list-models"])
    except subprocess.TimeoutExpired:
        return CursorModelsReport(
            status=CursorModelsStatus.ERROR,
            models=default_catalog,
            defaultModel=DEFAULT_CURSOR_SKILL_MODEL,
            message="Cursor CLI timed out while listing models.",
            executable=executable,
        )
    except OSError as exc:
        return CursorModelsReport(
            status=CursorModelsStatus.ERROR,
            models=default_catalog,
            defaultModel=DEFAULT_CURSOR_SKILL_MODEL,
            message=f"Could not list Cursor models: {exc}",
            executable=executable,
        )

    combined = "\n".join(
        part for part in (result.stdout, result.stderr) if part
    )
    parsed = parse_list_models_output(combined)
    models = ensure_default_model(parsed)

    if result.exit_code != 0 and not parsed:
        detail = (result.stderr or result.stdout or "").strip()
        return CursorModelsReport(
            status=CursorModelsStatus.ERROR,
            models=models,
            defaultModel=DEFAULT_CURSOR_SKILL_MODEL,
            message=(
                f"Cursor CLI --list-models failed (exit {result.exit_code})"
                + (f": {detail}" if detail else "")
                + f". Defaulting to {DEFAULT_CURSOR_SKILL_MODEL}."
            ),
            executable=executable,
        )

    return CursorModelsReport(
        status=CursorModelsStatus.AVAILABLE,
        models=models,
        defaultModel=DEFAULT_CURSOR_SKILL_MODEL,
        message=f"Loaded {len(models)} model(s) from Cursor CLI.",
        executable=executable,
    )


_models_override: Callable[..., CursorModelsReport] | None = None


def set_cursor_models_override(
    override: Callable[..., CursorModelsReport] | None,
) -> None:
    global _models_override
    _models_override = override


def get_cursor_models(**kwargs: Any) -> CursorModelsReport:
    """Public entry used by the API route."""
    if _models_override is not None:
        return _models_override(**kwargs)
    return list_cursor_models(**kwargs)
