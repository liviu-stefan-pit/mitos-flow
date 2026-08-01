"""Filesystem-backed managed local library store (Phase 17)."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mitos_api.domain.library import (
    AssetKind,
    LibraryAsset,
    LibraryAssetManifest,
    LibraryAssetSummary,
)
from mitos_api.services.library.frontmatter import NormalizedPreview

DEFAULT_LIBRARY_DIRNAME = ".mitos-flow-library"


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


class LibraryStore:
    """Persist original Markdown + normalized manifest under a managed root."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = (root if root is not None else default_library_root()).resolve()
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        return self._root

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        (self._root / "skills").mkdir(exist_ok=True)
        (self._root / "rules").mkdir(exist_ok=True)

    def _kind_dir(self, kind: AssetKind) -> Path:
        return self._root / ("skills" if kind is AssetKind.SKILL else "rules")

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

            original_name = "original.mdc" if preview.original_filename.lower().endswith(
                ".mdc"
            ) else "original.md"
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
            for kind in (AssetKind.SKILL, AssetKind.RULES):
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
            for kind in (AssetKind.SKILL, AssetKind.RULES):
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
                for candidate in ("original.md", "original.mdc"):
                    path = asset_dir / candidate
                    if path.exists():
                        original = path.read_text(encoding="utf-8")
                        break
                if original is None:
                    return None
                return LibraryAsset(manifest=manifest, originalContent=original)
            return None

    def clear(self) -> None:
        """Remove all stored assets (tests only)."""
        with self._lock:
            if not self._root.exists():
                return
            for kind in (AssetKind.SKILL, AssetKind.RULES):
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
