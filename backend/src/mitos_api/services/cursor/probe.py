"""Read-only Cursor CLI capability probe (Phase 21).

Detects whether the Cursor agent CLI is on PATH (or overridden), reads
``--version`` / ``--help``, and reports supported features from help text.

Never runs user prompts. Never invents flags that are absent from help.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mitos_api.domain.cursor import (
    CursorCapabilityReport,
    CursorCapabilityStatus,
    CursorFeatureFlags,
)

# Floor for "available". Real Cursor agent builds are far above this;
# tests inject lower versions for the unsupported_version gate case.
MINIMUM_CURSOR_CLI_VERSION = "0.1.0"

# Prefer MITOS_* naming; accept CURSOR_CLI_PATH as a common alternate.
_ENV_EXECUTABLE_KEYS = ("MITOS_CURSOR_CLI", "CURSOR_CLI_PATH")

_CANDIDATE_NAMES = ("agent", "cursor-agent")

# Official installer locations (used when PATH is stale, e.g. uvicorn --reload
# children on Windows that do not inherit a freshly updated user PATH).
_KNOWN_INSTALL_RELATIVE = (
    # Windows native installer (cursor.com/install?win32=true)
    ("LOCALAPPDATA", Path("cursor-agent") / "agent.cmd"),
    ("LOCALAPPDATA", Path("cursor-agent") / "agent.exe"),
    # macOS / Linux / WSL curl installer
    ("HOME", Path(".local") / "bin" / "agent"),
    ("HOME", Path(".local") / "bin" / "cursor-agent"),
)

_PROBE_TIMEOUT_SEC = 5.0

_VERSION_RE = re.compile(
    r"(?P<version>\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.-]+)?)",
)

# Markers searched in help text (discovery only — not assumed a priori).
_FEATURE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("printMode", ("--print",)),
    ("outputFormat", ("--output-format",)),
    ("workspace", ("--workspace",)),
    ("force", ("--force",)),
    ("model", ("--model",)),
    ("listModels", ("--list-models",)),
    ("trust", ("--trust",)),
    ("apiKey", ("--api-key",)),
    ("streamPartialOutput", ("--stream-partial-output",)),
)


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


RunCommand = Callable[[Sequence[str]], CommandResult]
WhichCommand = Callable[[str], str | None]


def _default_run_command(argv: Sequence[str]) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_SEC,
        check=False,
        stdin=subprocess.DEVNULL,
    )
    return CommandResult(
        exit_code=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def _default_which(name: str) -> str | None:
    return shutil.which(name)


def _env_executable(environ: Mapping[str, str]) -> str | None:
    for key in _ENV_EXECUTABLE_KEYS:
        raw = (environ.get(key) or "").strip()
        if raw:
            return raw
    return None


def _known_install_paths(environ: Mapping[str, str]) -> list[str]:
    found: list[str] = []
    for env_key, relative in _KNOWN_INSTALL_RELATIVE:
        root = (environ.get(env_key) or "").strip()
        if not root:
            continue
        candidate = Path(root) / relative
        if candidate.is_file():
            found.append(str(candidate))
    return found


def resolve_cursor_executable(
    *,
    environ: Mapping[str, str] | None = None,
    which: WhichCommand | None = None,
) -> str | None:
    """Return absolute/override path to Cursor CLI, or None if absent."""
    env = environ if environ is not None else os.environ
    override = _env_executable(env)
    if override:
        return override

    which_fn = which or _default_which
    for name in _CANDIDATE_NAMES:
        found = which_fn(name)
        if found:
            return found

    known = _known_install_paths(env)
    if known:
        return known[0]
    return None


def parse_version_string(raw: str) -> str | None:
    """Extract the first dotted numeric version from CLI version output."""
    text = (raw or "").strip()
    if not text:
        return None
    match = _VERSION_RE.search(text)
    if not match:
        return None
    return match.group("version")


def _version_tuple(version: str) -> tuple[int, ...]:
    core = version.split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for piece in core.split("."):
        if not piece.isdigit():
            break
        parts.append(int(piece))
    return tuple(parts) if parts else (0,)


def is_version_supported(
    version: str,
    minimum: str = MINIMUM_CURSOR_CLI_VERSION,
) -> bool:
    return _version_tuple(version) >= _version_tuple(minimum)


def discover_features(help_text: str) -> CursorFeatureFlags:
    """Mark features true only when their markers appear in help output."""
    haystack = help_text or ""
    values: dict[str, bool] = {}
    for field_name, markers in _FEATURE_MARKERS:
        values[field_name] = any(marker in haystack for marker in markers)
    return CursorFeatureFlags(**values)


def _help_excerpt(help_text: str, limit: int = 4000) -> str | None:
    text = (help_text or "").strip()
    if not text:
        return None
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def probe_cursor_capability(
    *,
    environ: Mapping[str, str] | None = None,
    which: WhichCommand | None = None,
    run_command: RunCommand | None = None,
    minimum_version: str = MINIMUM_CURSOR_CLI_VERSION,
) -> CursorCapabilityReport:
    """
    Probe Cursor CLI availability, version, and help-advertised features.

    Side effects are limited to locating an executable and running
    ``--version`` / ``--help``. No user prompt is ever passed.
    """
    run = run_command or _default_run_command
    executable = resolve_cursor_executable(environ=environ, which=which)

    if not executable:
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.ABSENT,
            message=(
                "Cursor CLI not found. Install the Cursor agent CLI "
                "(`agent` / `cursor-agent`) or set MITOS_CURSOR_CLI."
            ),
            minimumVersion=minimum_version,
        )

    try:
        version_result = run([executable, "--version"])
    except subprocess.TimeoutExpired:
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.ERROR,
            message="Cursor CLI timed out while reporting --version.",
            executable=executable,
            minimumVersion=minimum_version,
        )
    except OSError as exc:
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.ERROR,
            message=f"Could not execute Cursor CLI: {exc}",
            executable=executable,
            minimumVersion=minimum_version,
        )

    version_raw = (version_result.stdout or version_result.stderr or "").strip()
    version = parse_version_string(version_raw)

    try:
        help_result = run([executable, "--help"])
    except subprocess.TimeoutExpired:
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.ERROR,
            message="Cursor CLI timed out while reporting --help.",
            executable=executable,
            version=version,
            versionRaw=version_raw or None,
            minimumVersion=minimum_version,
        )
    except OSError as exc:
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.ERROR,
            message=f"Could not execute Cursor CLI help: {exc}",
            executable=executable,
            version=version,
            versionRaw=version_raw or None,
            minimumVersion=minimum_version,
        )

    help_text = "\n".join(
        part
        for part in (help_result.stdout, help_result.stderr)
        if part
    ).strip()
    features = discover_features(help_text)
    excerpt = _help_excerpt(help_text)

    if version is None:
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.ERROR,
            message=(
                "Cursor CLI responded but no version number could be parsed "
                "from --version output."
            ),
            executable=executable,
            versionRaw=version_raw or None,
            minimumVersion=minimum_version,
            helpExcerpt=excerpt,
            features=features,
        )

    if not is_version_supported(version, minimum_version):
        return CursorCapabilityReport(
            status=CursorCapabilityStatus.UNSUPPORTED_VERSION,
            message=(
                f"Cursor CLI version {version} is below the minimum "
                f"supported version {minimum_version}."
            ),
            executable=executable,
            version=version,
            versionRaw=version_raw or None,
            minimumVersion=minimum_version,
            helpExcerpt=excerpt,
            features=features,
        )

    return CursorCapabilityReport(
        status=CursorCapabilityStatus.AVAILABLE,
        message=f"Cursor CLI available (version {version}).",
        executable=executable,
        version=version,
        versionRaw=version_raw or None,
        minimumVersion=minimum_version,
        helpExcerpt=excerpt,
        features=features,
    )


# Optional process-wide override for tests (mirrors library store pattern).
_probe_override: Callable[..., CursorCapabilityReport] | None = None


def set_cursor_probe_override(
    override: Callable[..., CursorCapabilityReport] | None,
) -> None:
    global _probe_override
    _probe_override = override


def get_cursor_capability(**kwargs: Any) -> CursorCapabilityReport:
    """Public entry used by the API route."""
    if _probe_override is not None:
        return _probe_override(**kwargs)
    return probe_cursor_capability(**kwargs)
