"""Preview and confirm import into the managed library (Phase 17)."""

from __future__ import annotations

from mitos_api.domain.library import (
    AssetKind,
    LibraryAsset,
    LibraryBatchImportRequest,
    LibraryBatchImportResponse,
    LibraryImportRequest,
    LibraryImportResponse,
    LibraryListResponse,
    LibraryPreviewRequest,
    LibraryPreviewResponse,
)
from mitos_api.services.library.frontmatter import normalize_document
from mitos_api.services.library.store import LibraryStore, get_library_store


def preview_import(
    request: LibraryPreviewRequest,
    *,
    store: LibraryStore | None = None,
) -> LibraryPreviewResponse:
    """Parse and normalize without writing to the library."""
    _ = store  # preview is pure; store reserved for future quota checks
    normalized, errors = normalize_document(
        request.content,
        request.filename,
        kind=request.kind,
    )
    if errors or normalized is None:
        return LibraryPreviewResponse(ok=False, errors=errors)

    return LibraryPreviewResponse(
        ok=True,
        kind=normalized.kind,
        name=normalized.name,
        description=normalized.description,
        frontmatter=normalized.frontmatter,
        body=normalized.body,
        originalContent=request.content,
        originalFilename=normalized.original_filename,
        errors=[],
    )


def confirm_import(
    request: LibraryImportRequest,
    *,
    store: LibraryStore | None = None,
) -> LibraryImportResponse:
    """Validate then persist original + normalized manifest."""
    active = store if store is not None else get_library_store()
    normalized, errors = normalize_document(
        request.content,
        request.filename,
        kind=request.kind,
    )
    if errors or normalized is None:
        return LibraryImportResponse(ok=False, errors=errors)

    asset: LibraryAsset = active.save(normalized, request.content)
    return LibraryImportResponse(ok=True, asset=asset, errors=[])


def import_batch(
    request: LibraryBatchImportRequest,
    *,
    store: LibraryStore | None = None,
) -> LibraryBatchImportResponse:
    """Import multiple files; each file succeeds or fails independently."""
    active = store if store is not None else get_library_store()
    results: list[LibraryImportResponse] = []
    for file_req in request.files:
        results.append(confirm_import(file_req, store=active))
    imported = sum(1 for r in results if r.ok)
    return LibraryBatchImportResponse(
        results=results,
        importedCount=imported,
        failedCount=len(results) - imported,
    )


def list_library(*, store: LibraryStore | None = None) -> LibraryListResponse:
    active = store if store is not None else get_library_store()
    return LibraryListResponse(assets=active.list_assets())


def get_library_asset(
    asset_id: str,
    *,
    store: LibraryStore | None = None,
) -> LibraryAsset | None:
    active = store if store is not None else get_library_store()
    return active.get(asset_id)


def allowed_upload_extension(filename: str) -> bool:
    lower = filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return lower.endswith((".md", ".mdc", ".markdown"))


def coerce_kind(value: str | None) -> AssetKind | None:
    if value is None or value == "":
        return None
    return AssetKind(value)
