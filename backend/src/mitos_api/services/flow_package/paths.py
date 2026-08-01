"""Zip member path and size validation for ``.flow`` archives (Phases 29–30).

Rejects zip-slip (``..``, absolute, drive/UNC), oversized members/archives,
and unexpected member names before any extraction. Mode-specific original
rules are enforced after ``format.json`` is parsed (see ``assert_members_for_mode``).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import PurePosixPath, PureWindowsPath

from mitos_api.domain.workflow import ValidationIssue
from mitos_api.services.flow_package.constants import (
    ASSETS_PREFIX,
    CHECKSUMS_JSON,
    FORMAT_JSON,
    MAX_ARCHIVE_MEMBERS,
    MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    MAX_MEMBER_UNCOMPRESSED_BYTES,
    ORIGINAL_FILENAMES,
    PACKAGING_MODE_EMBEDDED,
    PACKAGING_MODE_REFERENCE,
    PACKAGING_MODE_SNAPSHOT,
    WORKFLOW_JSON,
)

_UNSAFE_SEGMENT = frozenset({"", ".", ".."})
_KIND_DIRS = frozenset({"skills", "rules", "kb"})
_ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class FlowPackageError(ValueError):
    """Raised when a ``.flow`` archive is invalid or unsafe."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def as_issue(self) -> ValidationIssue:
        return ValidationIssue(code=self.code, message=self.message)


def normalize_member_path(name: str) -> str:
    """
    Normalize a zip member name to a safe forward-slash relative path.

    Raises ``FlowPackageError`` on zip-slip / absolute / empty paths.
    """
    raw = (name or "").strip()
    if not raw:
        raise FlowPackageError(
            "Archive member path is empty.",
            code="zip_slip",
        )

    # Zip stores paths with forward slashes; still reject Windows forms.
    if re.match(r"^[A-Za-z]:", raw) or raw.startswith("\\\\") or raw.startswith("//"):
        raise FlowPackageError(
            f"Absolute or UNC archive path is not allowed: '{name}'",
            code="zip_slip",
        )

    posix = PurePosixPath(raw.replace("\\", "/"))
    if posix.is_absolute():
        raise FlowPackageError(
            f"Absolute archive path is not allowed: '{name}'",
            code="zip_slip",
        )

    parts = list(posix.parts)
    if not parts or any(part in _UNSAFE_SEGMENT for part in parts):
        raise FlowPackageError(
            f"Zip-slip or empty path segment is not allowed: '{name}'",
            code="zip_slip",
        )

    win = PureWindowsPath(raw)
    if win.is_absolute() or getattr(win, "drive", ""):
        raise FlowPackageError(
            f"Absolute archive path is not allowed: '{name}'",
            code="zip_slip",
        )

    return "/".join(parts)


def _is_allowed_member(path: str) -> bool:
    if path in {FORMAT_JSON, WORKFLOW_JSON, CHECKSUMS_JSON}:
        return True
    if not path.startswith(ASSETS_PREFIX):
        return False
    # assets/{skills|rules|kb}/{assetId}/manifest.json|original.*
    rest = path[len(ASSETS_PREFIX) :]
    parts = rest.split("/")
    if len(parts) != 3:
        return False
    kind_dir, asset_id, filename = parts
    if kind_dir not in _KIND_DIRS:
        return False
    if not _ASSET_ID_RE.match(asset_id):
        return False
    return filename == "manifest.json" or filename in ORIGINAL_FILENAMES


def assert_members_for_mode(members: dict[str, bytes], packaging_mode: str) -> None:
    """
    Enforce packaging-mode rules for ``original.*`` members.

    - reference: no originals
    - snapshot: Skill/Rules originals only (no KB originals)
    - embedded: originals allowed for all kinds
    """
    for path in members:
        if not path.startswith(ASSETS_PREFIX):
            continue
        filename = path.rsplit("/", 1)[-1]
        if filename not in ORIGINAL_FILENAMES:
            continue
        kind_dir = path[len(ASSETS_PREFIX) :].split("/", 1)[0]

        if packaging_mode == PACKAGING_MODE_REFERENCE:
            raise FlowPackageError(
                f"Reference-mode archives must not include source docs: '{path}'",
                code="unexpected_member",
            )
        if packaging_mode == PACKAGING_MODE_SNAPSHOT and kind_dir == "kb":
            raise FlowPackageError(
                f"Snapshot-mode archives must not include KB source docs: '{path}'",
                code="unexpected_member",
            )
        if packaging_mode not in {
            PACKAGING_MODE_REFERENCE,
            PACKAGING_MODE_SNAPSHOT,
            PACKAGING_MODE_EMBEDDED,
        }:
            raise FlowPackageError(
                f"Unsupported packagingMode '{packaging_mode}'.",
                code="unsupported_packaging_mode",
            )


def validate_archive_members(
    zf: zipfile.ZipFile,
) -> dict[str, bytes]:
    """
    Inspect every zip member for path safety and size limits.

    Returns a mapping of normalized path → uncompressed bytes.
    Does not write anything to disk. Mode-specific original rules are
    enforced separately via ``assert_members_for_mode``.
    """
    infos = zf.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        raise FlowPackageError(
            f"Archive has too many members ({len(infos)} > {MAX_ARCHIVE_MEMBERS}).",
            code="archive_too_large",
        )

    total = 0
    members: dict[str, bytes] = {}

    for info in infos:
        # Skip directory placeholders.
        if info.is_dir() or info.filename.endswith("/"):
            continue

        path = normalize_member_path(info.filename)

        if info.file_size < 0 or info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise FlowPackageError(
                f"Archive member '{path}' exceeds size limit "
                f"({info.file_size} > {MAX_MEMBER_UNCOMPRESSED_BYTES}).",
                code="archive_too_large",
            )

        total += info.file_size
        if total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise FlowPackageError(
                f"Archive uncompressed size exceeds limit "
                f"({MAX_ARCHIVE_UNCOMPRESSED_BYTES} bytes).",
                code="archive_too_large",
            )

        if not _is_allowed_member(path):
            raise FlowPackageError(
                f"Unexpected archive member: '{path}'",
                code="unexpected_member",
            )

        if path in members:
            raise FlowPackageError(
                f"Duplicate archive member: '{path}'",
                code="duplicate_member",
            )

        data = zf.read(info)
        if len(data) != info.file_size and info.file_size > 0:
            # Trust actual bytes if ZipInfo was wrong; re-check size.
            if len(data) > MAX_MEMBER_UNCOMPRESSED_BYTES:
                raise FlowPackageError(
                    f"Archive member '{path}' exceeds size limit.",
                    code="archive_too_large",
                )
        members[path] = data

    if FORMAT_JSON not in members:
        raise FlowPackageError(
            f"Missing required member '{FORMAT_JSON}'.",
            code="missing_member",
        )
    if WORKFLOW_JSON not in members:
        raise FlowPackageError(
            f"Missing required member '{WORKFLOW_JSON}'.",
            code="missing_member",
        )
    if CHECKSUMS_JSON not in members:
        raise FlowPackageError(
            f"Missing required member '{CHECKSUMS_JSON}'.",
            code="missing_member",
        )

    return members
