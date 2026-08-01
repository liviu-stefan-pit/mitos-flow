"""Filesystem-backed managed local library store (Phase 17+)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from mitos_api.domain.library import (
    AssetKind,
    LibraryAsset,
    LibraryAssetManifest,
    LibraryAssetSummary,
)
from mitos_api.services.library.frontmatter import NormalizedPreview

DEFAULT_LIBRARY_DIRNAME = ".mitos-flow-library"

_KIND_DIR = {
    AssetKind.SKILL: "skills",
    AssetKind.RULES: "rules",
    AssetKind.KNOWLEDGE_BASE: "kb",
}


def default_library_root() -> Path:
    """
    Resolve the managed library root.

    Override with MITOS_LIBRARY_ROOT. Default is a project-local directory
    (not an arbitrary user path) under the process working directory.
    """
    override = os.getenv("MITOS_LIBRARY_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.cwd() / DEFAULT_LIBRARY_DIRNAME).resolve()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _original_filename_for(preview: NormalizedPreview) -> str:
    lower = preview.original_filename.lower()
    if lower.endswith(".txt"):
        return "original.txt"
    if lower.endswith(".mdc"):
        return "original.mdc"
    return "original.md"


def _original_filename_from_manifest(manifest: LibraryAssetManifest) -> str:
    lower = (manifest.originalFilename or "").lower()
    if lower.endswith(".txt"):
        return "original.txt"
    if lower.endswith(".mdc"):
        return "original.mdc"
    if manifest.kind == AssetKind.RULES and not lower.endswith(".md"):
        return "original.mdc"
    return "original.md"


def _synthesize_original(manifest: LibraryAssetManifest) -> str:
    """Rebuild a readable original from stored frontmatter + body."""
    fm = manifest.frontmatter or {}
    body = manifest.body or ""
    if not fm:
        return body
    dumped = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{dumped}\n---\n{body}"


class LibraryStore:
    """Persist original file + normalized manifest under a managed root."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = (root if root is not None else default_library_root()).resolve()
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        return self._root

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for dirname in _KIND_DIR.values():
            (self._root / dirname).mkdir(exist_ok=True)

    def _kind_dir(self, kind: AssetKind) -> Path:
        return self._root / _KIND_DIR[kind]

    def _asset_dir(self, kind: AssetKind, asset_id: str) -> Path:
        return self._kind_dir(kind) / asset_id

    def save(
        self,
        preview: NormalizedPreview,
        original_content: str,
        *,
        asset_id: str | None = None,
    ) -> LibraryAsset:
        """Write original + manifest into the managed library."""
        with self._lock:
            self._ensure_root()
            aid = asset_id or str(uuid.uuid4())
            asset_dir = self._asset_dir(preview.kind, aid)
            asset_dir.mkdir(parents=True, exist_ok=False)

            original_name = _original_filename_for(preview)
            original_path = asset_dir / original_name
            original_path.write_text(original_content, encoding="utf-8")

            manifest = LibraryAssetManifest(
                id=aid,
                kind=preview.kind,
                name=preview.name,
                description=preview.description,
                originalFilename=preview.original_filename,
                importedAt=_utc_now_iso(),
                frontmatter=preview.frontmatter,
                body=preview.body,
            )
            (asset_dir / "manifest.json").write_text(
                manifest.model_dump_json(indent=2),
                encoding="utf-8",
            )
            return LibraryAsset(manifest=manifest, originalContent=original_content)

    def list_assets(self) -> list[LibraryAssetSummary]:
        with self._lock:
            self._ensure_root()
            summaries: list[LibraryAssetSummary] = []
            for kind in (AssetKind.SKILL, AssetKind.RULES, AssetKind.KNOWLEDGE_BASE):
                kind_dir = self._kind_dir(kind)
                if not kind_dir.exists():
                    continue
                for child in sorted(kind_dir.iterdir()):
                    if not child.is_dir():
                        continue
                    manifest_path = child / "manifest.json"
                    if not manifest_path.exists():
                        continue
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        manifest = LibraryAssetManifest.model_validate(data)
                    except (OSError, json.JSONDecodeError, ValueError):
                        continue
                    summaries.append(
                        LibraryAssetSummary(
                            id=manifest.id,
                            kind=manifest.kind,
                            name=manifest.name,
                            description=manifest.description,
                            originalFilename=manifest.originalFilename,
                            importedAt=manifest.importedAt,
                        )
                    )
            summaries.sort(key=lambda s: (s.kind.value, s.name.lower(), s.importedAt))
            return summaries

    def get(self, asset_id: str) -> LibraryAsset | None:
        with self._lock:
            self._ensure_root()
            for kind in (AssetKind.SKILL, AssetKind.RULES, AssetKind.KNOWLEDGE_BASE):
                asset_dir = self._asset_dir(kind, asset_id)
                manifest_path = asset_dir / "manifest.json"
                if not manifest_path.exists():
                    continue
                try:
                    manifest = LibraryAssetManifest.model_validate(
                        json.loads(manifest_path.read_text(encoding="utf-8"))
                    )
                except (OSError, json.JSONDecodeError, ValueError):
                    return None
                original: str | None = None
                for candidate in ("original.md", "original.mdc", "original.txt"):
                    path = asset_dir / candidate
                    if path.exists():
                        original = path.read_text(encoding="utf-8")
                        break
                if original is None:
                    return None
                return LibraryAsset(manifest=manifest, originalContent=original)
            return None

    def restore_from_manifest(self, manifest: LibraryAssetManifest) -> LibraryAsset:
        """
        Restore an asset from a reference-mode package manifest (Phase 29).

        Synthesizes a minimal ``original.*`` from frontmatter + body so the
        store layout stays compatible with ``get()``. Does not overwrite an
        existing asset with the same id.
        """
        return self.restore_from_package(manifest, original_content=None)

    def restore_from_package(
        self,
        manifest: LibraryAssetManifest,
        *,
        original_content: str | None = None,
    ) -> LibraryAsset:
        """
        Restore an asset from a ``.flow`` package (Phases 29–30).

        When ``original_content`` is provided (snapshot/embedded modes), write
        those bytes as the managed ``original.*``. Otherwise synthesize from
        frontmatter + body (reference mode). Does not overwrite an existing
        asset with the same id.
        """
        with self._lock:
            self._ensure_root()
            existing = self.get(manifest.id)
            if existing is not None:
                return existing

            asset_dir = self._asset_dir(manifest.kind, manifest.id)
            asset_dir.mkdir(parents=True, exist_ok=False)

            original_name = _original_filename_from_manifest(manifest)
            content = (
                original_content
                if original_content is not None
                else _synthesize_original(manifest)
            )
            (asset_dir / original_name).write_text(content, encoding="utf-8")
            (asset_dir / "manifest.json").write_text(
                manifest.model_dump_json(indent=2),
                encoding="utf-8",
            )
            return LibraryAsset(manifest=manifest, originalContent=content)

    def clear(self) -> None:
        """Remove all stored assets (tests only)."""
        with self._lock:
            if not self._root.exists():
                return
            for kind in (AssetKind.SKILL, AssetKind.RULES, AssetKind.KNOWLEDGE_BASE):
                kind_dir = self._kind_dir(kind)
                if not kind_dir.exists():
                    continue
                for child in kind_dir.iterdir():
                    if child.is_dir():
                        for file in child.iterdir():
                            file.unlink(missing_ok=True)
                        child.rmdir()


# Process-wide store; tests may replace via get/set helpers.
_library_store: LibraryStore | None = None
_store_lock = threading.Lock()


def get_library_store() -> LibraryStore:
    global _library_store
    with _store_lock:
        if _library_store is None:
            _library_store = LibraryStore()
        return _library_store


def set_library_store(store: LibraryStore | None) -> None:
    global _library_store
    with _store_lock:
        _library_store = store
