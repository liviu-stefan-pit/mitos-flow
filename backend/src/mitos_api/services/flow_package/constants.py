"""Constants for the versioned ``.flow`` zip package (Phases 29–30)."""

from __future__ import annotations

FLOW_FORMAT_VERSION = 1
FLOW_APP_ID = "mitos-flow"

PACKAGING_MODE_REFERENCE = "reference"
PACKAGING_MODE_SNAPSHOT = "snapshot"
PACKAGING_MODE_EMBEDDED = "embedded"

PACKAGING_MODES = frozenset(
    {
        PACKAGING_MODE_REFERENCE,
        PACKAGING_MODE_SNAPSHOT,
        PACKAGING_MODE_EMBEDDED,
    }
)

# Archive member names (posix, forward slashes only).
FORMAT_JSON = "format.json"
WORKFLOW_JSON = "workflow.json"
CHECKSUMS_JSON = "checksums.json"
ASSETS_PREFIX = "assets/"

# Safety limits — validated before any extraction.
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_MEMBER_UNCOMPRESSED_BYTES = 2 * 1024 * 1024  # 2 MiB
MAX_ARCHIVE_MEMBERS = 500

# Soft thresholds for export inventory warnings (Phase 30).
WARNING_PACKAGE_BYTES = 1 * 1024 * 1024  # 1 MiB
WARNING_ASSET_BYTES = 256 * 1024  # 256 KiB

ORIGINAL_FILENAMES = frozenset({"original.md", "original.mdc", "original.txt"})
