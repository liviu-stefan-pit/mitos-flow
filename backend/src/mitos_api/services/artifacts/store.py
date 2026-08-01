"""Managed artifact file writes under an approved output root (Phase 25).

Writes are constrained to ``MITOS_OUTPUT_ROOT`` (default
``.mitos-flow-artifacts`` under cwd). Paths are resolved relative to that
root; traversal and absolute paths are rejected. File replacement is atomic
(``os.replace`` after a same-directory temp write).
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

from mitos_api.domain.workflow import ArtifactFileWriteMode

DEFAULT_OUTPUT_DIRNAME = ".mitos-flow-artifacts"
_ENV_OUTPUT_ROOT = "MITOS_OUTPUT_ROOT"

# Reject empty segments, ``.``, ``..``, and Windows drive / UNC forms.
_UNSAFE_SEGMENT = frozenset({"", ".", ".."})

_output_root_override: Path | None = None
_override_lock = threading.Lock()


class ArtifactWriteError(ValueError):
    """Raised when an artifact path is invalid or a write fails."""

    def __init__(self, message: str, *, code: str = "artifact_write_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ArtifactWriteResult:
    """Result of a successful managed-file write."""

    absolute_path: Path
    relative_path: str
    bytes_written: int
    write_mode: ArtifactFileWriteMode


def default_output_root() -> Path:
    """
    Resolve the approved artifact output root.

    Override with ``MITOS_OUTPUT_ROOT``. Default is a project-local directory
    under the process working directory (not an arbitrary user path).
    """
    override = os.getenv(_ENV_OUTPUT_ROOT, "").strip()
    if override:
        return Path(override).expanduser().resolve(strict=False)
    return (Path.cwd() / DEFAULT_OUTPUT_DIRNAME).resolve(strict=False)


def get_output_root() -> Path:
    """Return the active output root (test override or default)."""
    with _override_lock:
        if _output_root_override is not None:
            return _output_root_override
    return default_output_root()


def set_output_root_override(root: Path | None) -> None:
    """Tests may pin a temp output root."""
    global _output_root_override
    with _override_lock:
        _output_root_override = (
            root.resolve(strict=False) if root is not None else None
        )


def _normalize_relative(relative_path: str) -> str:
    """Normalize to forward-slash relative form; reject absolute / traversal."""
    raw = (relative_path or "").strip()
    if not raw:
        raise ArtifactWriteError(
            "filePath is required for managed-file destinations",
            code="artifact_path_required",
        )

    # Reject Windows drive letters and UNC before Path normalization.
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("\\\\") or raw.startswith("//"):
        raise ArtifactWriteError(
            f"Absolute or UNC path is not allowed: '{relative_path}'",
            code="artifact_path_absolute",
        )

    # Normalize separators then inspect posix-style segments.
    posix = PurePosixPath(raw.replace("\\", "/"))
    if posix.is_absolute():
        raise ArtifactWriteError(
            f"Absolute path is not allowed: '{relative_path}'",
            code="artifact_path_absolute",
        )

    parts = list(posix.parts)
    if not parts or any(part in _UNSAFE_SEGMENT for part in parts):
        raise ArtifactWriteError(
            f"Path traversal or empty segment is not allowed: '{relative_path}'",
            code="artifact_path_traversal",
        )

    # Also reject Windows-specific absolute forms that PurePosixPath missed.
    win = PureWindowsPath(raw)
    if win.is_absolute() or getattr(win, "drive", ""):
        raise ArtifactWriteError(
            f"Absolute path is not allowed: '{relative_path}'",
            code="artifact_path_absolute",
        )

    return "/".join(parts)


def resolve_under_output_root(
    relative_path: str,
    *,
    root: Path | None = None,
) -> tuple[Path, str]:
    """
    Resolve ``relative_path`` under the approved output root.

    Returns ``(absolute_path, normalized_relative)``.
    """
    normalized = _normalize_relative(relative_path)
    approved = (root if root is not None else get_output_root()).resolve(strict=False)

    candidate = (approved / Path(*normalized.split("/"))).resolve(strict=False)
    try:
        candidate.relative_to(approved)
    except ValueError as exc:
        raise ArtifactWriteError(
            f"Path '{relative_path}' resolves outside the approved output root "
            f"'{approved}'.",
            code="artifact_path_traversal",
        ) from exc

    # Refuse writing the root directory itself as a file.
    if candidate == approved:
        raise ArtifactWriteError(
            "filePath must name a file under the output root, not the root itself",
            code="artifact_path_invalid",
        )

    return candidate, normalized


def _timestamp_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _timestamped_path(target: Path) -> Path:
    """Insert a UTC timestamp before the file suffix: ``name-TS.ext``."""
    stamp = _timestamp_suffix()
    stem = target.stem or target.name
    suffix = target.suffix
    return target.with_name(f"{stem}-{stamp}{suffix}")


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` via same-directory temp + ``os.replace``."""
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def write_artifact(
    content: str,
    *,
    relative_path: str,
    write_mode: ArtifactFileWriteMode = ArtifactFileWriteMode.TIMESTAMPED,
    root: Path | None = None,
    encoding: str = "utf-8",
) -> ArtifactWriteResult:
    """
    Write artifact bytes under the approved output root.

    ``overwrite`` replaces the named file atomically.
    ``timestamped`` writes a new ``name-YYYYMMDDTHHMMSSZ.ext`` beside it.
    """
    base_target, normalized = resolve_under_output_root(relative_path, root=root)
    if write_mode is ArtifactFileWriteMode.TIMESTAMPED:
        target = _timestamped_path(base_target)
    elif write_mode is ArtifactFileWriteMode.OVERWRITE:
        target = base_target
    else:  # pragma: no cover - enum exhaustiveness
        raise ArtifactWriteError(
            f"Unsupported write mode: {write_mode}",
            code="artifact_write_mode",
        )

    data = content.encode(encoding)
    try:
        _atomic_write_bytes(target, data)
    except OSError as exc:
        raise ArtifactWriteError(
            f"Failed to write artifact '{target}': {exc}",
            code="artifact_write_failed",
        ) from exc

    approved = (root if root is not None else get_output_root()).resolve(strict=False)
    written_relative = target.relative_to(approved).as_posix()
    return ArtifactWriteResult(
        absolute_path=target,
        relative_path=written_relative,
        bytes_written=len(data),
        write_mode=write_mode,
    )
