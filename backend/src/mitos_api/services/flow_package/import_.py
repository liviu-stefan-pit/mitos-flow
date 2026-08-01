"""Import ``.flow`` zip archives (Phases 29–30)."""

from __future__ import annotations

import io
import json
import zipfile

from mitos_api.domain.flow_package import (
    FlowFormatInfo,
    FlowImportResponse,
    PackagingMode,
    ReferencedAssetInfo,
    ReferencedAssetStatus,
)
from mitos_api.domain.library import AssetKind, LibraryAssetManifest
from mitos_api.domain.validation import validate_workflow
from mitos_api.domain.workflow import ValidationIssue, Workflow
from mitos_api.services.flow_package.checksums import verify_checksums
from mitos_api.services.flow_package.constants import (
    ASSETS_PREFIX,
    FLOW_FORMAT_VERSION,
    FORMAT_JSON,
    ORIGINAL_FILENAMES,
    PACKAGING_MODE_REFERENCE,
    WORKFLOW_JSON,
)
from mitos_api.services.flow_package.mode import (
    kind_dir,
    original_stored_filename,
    validate_packaging_mode,
)
from mitos_api.services.flow_package.paths import (
    FlowPackageError,
    assert_members_for_mode,
    validate_archive_members,
)
from mitos_api.services.library.store import LibraryStore, get_library_store

_DIR_TO_KIND = {
    "skills": AssetKind.SKILL,
    "rules": AssetKind.RULES,
    "kb": AssetKind.KNOWLEDGE_BASE,
}


def _fail(*errors: ValidationIssue) -> FlowImportResponse:
    return FlowImportResponse(ok=False, errors=list(errors))


def _parse_format(raw: bytes) -> FlowFormatInfo:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowPackageError(
            f"Invalid '{FORMAT_JSON}': {exc}",
            code="invalid_format",
        ) from exc

    if not isinstance(data, dict):
        raise FlowPackageError(
            f"'{FORMAT_JSON}' must be a JSON object.",
            code="invalid_format",
        )

    version = data.get("formatVersion")
    if version is None:
        raise FlowPackageError(
            f"'{FORMAT_JSON}' is missing formatVersion.",
            code="unsupported_format_version",
        )
    if not isinstance(version, int) or isinstance(version, bool):
        raise FlowPackageError(
            f"Unsupported formatVersion: {version!r}.",
            code="unsupported_format_version",
        )
    if version != FLOW_FORMAT_VERSION:
        raise FlowPackageError(
            f"Unsupported formatVersion {version} "
            f"(this build supports {FLOW_FORMAT_VERSION}).",
            code="unsupported_format_version",
        )

    mode = data.get("packagingMode", PACKAGING_MODE_REFERENCE)
    try:
        mode = validate_packaging_mode(str(mode))
    except FlowPackageError:
        raise

    try:
        return FlowFormatInfo.model_validate(
            {
                **data,
                "formatVersion": version,
                "packagingMode": mode,
            }
        )
    except Exception as exc:  # noqa: BLE001 — surface as package error
        raise FlowPackageError(
            f"Invalid '{FORMAT_JSON}': {exc}",
            code="invalid_format",
        ) from exc


def _parse_workflow(raw: bytes) -> Workflow:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlowPackageError(
            f"Invalid '{WORKFLOW_JSON}': {exc}",
            code="invalid_workflow",
        ) from exc
    try:
        return Workflow.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        raise FlowPackageError(
            f"Invalid workflow document: {exc}",
            code="invalid_workflow",
        ) from exc


def _iter_manifest_members(
    members: dict[str, bytes],
) -> list[tuple[str, LibraryAssetManifest]]:
    results: list[tuple[str, LibraryAssetManifest]] = []
    for path, raw in sorted(members.items()):
        if not path.startswith(ASSETS_PREFIX) or not path.endswith("/manifest.json"):
            continue
        parts = path[len(ASSETS_PREFIX) :].split("/")
        if len(parts) != 3:
            raise FlowPackageError(
                f"Unexpected asset path: '{path}'",
                code="unexpected_member",
            )
        kind_dir, asset_id, _ = parts
        expected_kind = _DIR_TO_KIND.get(kind_dir)
        if expected_kind is None:
            raise FlowPackageError(
                f"Unexpected asset kind directory in '{path}'",
                code="unexpected_member",
            )
        try:
            data = json.loads(raw.decode("utf-8"))
            manifest = LibraryAssetManifest.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            raise FlowPackageError(
                f"Invalid manifest at '{path}': {exc}",
                code="invalid_manifest",
            ) from exc
        if manifest.id != asset_id:
            raise FlowPackageError(
                f"Manifest id '{manifest.id}' does not match path asset id "
                f"'{asset_id}'.",
                code="invalid_manifest",
            )
        if manifest.kind != expected_kind:
            raise FlowPackageError(
                f"Manifest kind '{manifest.kind.value}' does not match path "
                f"directory '{kind_dir}'.",
                code="invalid_manifest",
            )
        results.append((path, manifest))
    return results


def _find_original(
    members: dict[str, bytes],
    manifest: LibraryAssetManifest,
) -> tuple[str, str] | None:
    """Return ``(stored_filename, content)`` if an original is present for the asset."""
    prefix = f"{ASSETS_PREFIX}{kind_dir(manifest.kind)}/{manifest.id}/"
    # Prefer the expected stored name, then any allowed original.*.
    expected = original_stored_filename(manifest)
    candidate_names = [expected, *sorted(ORIGINAL_FILENAMES - {expected})]
    for name in candidate_names:
        path = f"{prefix}{name}"
        raw = members.get(path)
        if raw is None:
            continue
        try:
            return name, raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FlowPackageError(
                f"Invalid UTF-8 in '{path}': {exc}",
                code="invalid_original",
            ) from exc
    return None


def import_flow_package(
    archive_bytes: bytes,
    *,
    store: LibraryStore | None = None,
) -> FlowImportResponse:
    """
    Validate and import a ``.flow`` archive.

    Validates paths, sizes, format version, packaging-mode original rules,
    and checksums **before** writing any library assets. Restores manifests
    and embedded ``original.*`` content when present; otherwise synthesizes
    originals from the manifest (reference / snapshot-without-KB).
    """
    if not archive_bytes:
        return _fail(
            ValidationIssue(
                code="empty_archive",
                message="Archive is empty.",
            )
        )

    lib = store if store is not None else get_library_store()

    try:
        try:
            zf = zipfile.ZipFile(io.BytesIO(archive_bytes), mode="r")
        except zipfile.BadZipFile as exc:
            raise FlowPackageError(
                f"Not a valid zip archive: {exc}",
                code="invalid_archive",
            ) from exc

        with zf:
            members = validate_archive_members(zf)
            verify_checksums(members)
            fmt = _parse_format(members[FORMAT_JSON])
            assert_members_for_mode(members, fmt.packagingMode)
            workflow = _parse_workflow(members[WORKFLOW_JSON])
            manifests = _iter_manifest_members(members)
    except FlowPackageError as exc:
        return _fail(exc.as_issue())

    validation = validate_workflow(workflow)
    if not validation.valid:
        return FlowImportResponse(
            ok=False,
            formatVersion=fmt.formatVersion,
            packagingMode=fmt.packagingMode,
            errors=validation.errors,
        )

    referenced: list[ReferencedAssetInfo] = []
    warnings: list[ValidationIssue] = []

    for _path, manifest in manifests:
        existing = lib.get(manifest.id)
        if existing is not None:
            referenced.append(
                ReferencedAssetInfo(
                    id=manifest.id,
                    kind=manifest.kind,
                    name=manifest.name,
                    status=ReferencedAssetStatus.ALREADY_PRESENT,
                )
            )
            continue

        original = _find_original(members, manifest)
        try:
            if original is not None:
                _stored_name, original_content = original
                lib.restore_from_package(
                    manifest,
                    original_content=original_content,
                )
            else:
                lib.restore_from_manifest(manifest)
        except Exception as exc:  # noqa: BLE001
            return _fail(
                ValidationIssue(
                    code="restore_failed",
                    message=f"Failed to restore asset '{manifest.id}': {exc}",
                )
            )
        referenced.append(
            ReferencedAssetInfo(
                id=manifest.id,
                kind=manifest.kind,
                name=manifest.name,
                status=ReferencedAssetStatus.RESTORED,
            )
        )

    packaging: PackagingMode = fmt.packagingMode
    return FlowImportResponse(
        ok=True,
        formatVersion=fmt.formatVersion,
        packagingMode=packaging,
        workflow=workflow,
        referencedAssets=referenced,
        warnings=warnings,
        errors=[],
    )
