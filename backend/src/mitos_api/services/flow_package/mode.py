"""Shared helpers for ``.flow`` packaging modes (Phases 29–30)."""

from __future__ import annotations

from mitos_api.domain.library import AssetKind, LibraryAssetManifest
from mitos_api.domain.flow_package import PackagingMode
from mitos_api.services.flow_package.constants import (
    ASSETS_PREFIX,
    PACKAGING_MODE_EMBEDDED,
    PACKAGING_MODE_REFERENCE,
    PACKAGING_MODE_SNAPSHOT,
    PACKAGING_MODES,
)
from mitos_api.services.flow_package.paths import FlowPackageError

_KIND_DIR = {
    AssetKind.SKILL: "skills",
    AssetKind.RULES: "rules",
    AssetKind.KNOWLEDGE_BASE: "kb",
}


def validate_packaging_mode(mode: str) -> PackagingMode:
    if mode not in PACKAGING_MODES:
        raise FlowPackageError(
            f"Unsupported packaging mode: '{mode}'. "
            f"Supported: {', '.join(sorted(PACKAGING_MODES))}.",
            code="unsupported_packaging_mode",
        )
    return mode  # type: ignore[return-value]


def includes_original(packaging_mode: str, kind: AssetKind) -> bool:
    """Whether this packaging mode embeds ``original.*`` for the asset kind."""
    if packaging_mode == PACKAGING_MODE_REFERENCE:
        return False
    if packaging_mode == PACKAGING_MODE_SNAPSHOT:
        return kind in (AssetKind.SKILL, AssetKind.RULES)
    if packaging_mode == PACKAGING_MODE_EMBEDDED:
        return True
    return False


def kind_dir(kind: AssetKind) -> str:
    return _KIND_DIR[kind]


def manifest_member_path(kind: AssetKind, asset_id: str) -> str:
    return f"{ASSETS_PREFIX}{_KIND_DIR[kind]}/{asset_id}/manifest.json"


def original_stored_filename(manifest: LibraryAssetManifest) -> str:
    """Filename used under the managed library / inside the zip."""
    lower = (manifest.originalFilename or "").lower()
    if lower.endswith(".txt"):
        return "original.txt"
    if lower.endswith(".mdc"):
        return "original.mdc"
    if manifest.kind == AssetKind.RULES and not lower.endswith(".md"):
        return "original.mdc"
    return "original.md"


def original_member_path(manifest: LibraryAssetManifest) -> str:
    return (
        f"{ASSETS_PREFIX}{_KIND_DIR[manifest.kind]}/"
        f"{manifest.id}/{original_stored_filename(manifest)}"
    )
