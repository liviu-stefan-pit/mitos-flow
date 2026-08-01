"""Build ``.flow`` zip archives and inventory previews (Phases 29–30)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from mitos_api.domain.flow_package import (
    FlowExportPreviewResponse,
    FlowExportRequest,
    FlowPackageInventoryItem,
    ReferencedAssetInfo,
    ReferencedAssetStatus,
)
from mitos_api.domain.library import AssetKind, LibraryAssetManifest
from mitos_api.domain.workflow import NodeKind, ValidationIssue, Workflow
from mitos_api.services.flow_package.checksums import (
    build_checksums,
    checksums_json_bytes,
)
from mitos_api.services.flow_package.constants import (
    CHECKSUMS_JSON,
    FLOW_APP_ID,
    FLOW_FORMAT_VERSION,
    FORMAT_JSON,
    WARNING_ASSET_BYTES,
    WARNING_PACKAGE_BYTES,
    WORKFLOW_JSON,
)
from mitos_api.services.flow_package.mode import (
    includes_original,
    manifest_member_path,
    original_member_path,
    original_stored_filename,
    validate_packaging_mode,
)
from mitos_api.services.library.store import LibraryStore, get_library_store

_NODE_KIND_TO_ASSET = {
    NodeKind.SKILL: AssetKind.SKILL,
    NodeKind.RULES: AssetKind.RULES,
    NodeKind.KNOWLEDGE_BASE: AssetKind.KNOWLEDGE_BASE,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def collect_referenced_asset_ids(workflow: Workflow) -> list[tuple[str, NodeKind]]:
    """Return ordered ``(libraryAssetId, nodeKind)`` pairs from the graph."""
    seen: set[str] = set()
    ordered: list[tuple[str, NodeKind]] = []
    for node in workflow.nodes:
        settings = node.settings
        asset_id = getattr(settings, "libraryAssetId", None)
        if not asset_id or asset_id in seen:
            continue
        if node.kind not in (
            NodeKind.SKILL,
            NodeKind.RULES,
            NodeKind.KNOWLEDGE_BASE,
        ):
            continue
        seen.add(asset_id)
        ordered.append((asset_id, node.kind))
    return ordered


def _build_warnings(
    *,
    packaging_mode: str,
    inventory: list[FlowPackageInventoryItem],
    estimated_bytes: int,
) -> list[ValidationIssue]:
    warnings: list[ValidationIssue] = []

    embedded_kb = [
        item
        for item in inventory
        if item.kind == AssetKind.KNOWLEDGE_BASE
        and item.includesOriginal
        and item.status == ReferencedAssetStatus.EXPORTED
    ]
    if packaging_mode == "embedded" and embedded_kb:
        names = ", ".join(item.name for item in embedded_kb)
        warnings.append(
            ValidationIssue(
                code="sensitivity_embedded_kb",
                message=(
                    "Embedded mode includes Knowledge Base source documents "
                    f"({names}), which may contain sensitive data."
                ),
            )
        )

    for item in inventory:
        total = item.manifestBytes + item.originalBytes
        if (
            item.status == ReferencedAssetStatus.EXPORTED
            and total >= WARNING_ASSET_BYTES
        ):
            warnings.append(
                ValidationIssue(
                    code="large_asset",
                    message=(
                        f"Asset '{item.name}' ({item.kind.value}) is "
                        f"{total} bytes; consider whether embedding is needed."
                    ),
                )
            )

    if estimated_bytes >= WARNING_PACKAGE_BYTES:
        warnings.append(
            ValidationIssue(
                code="large_package",
                message=(
                    f"Estimated package size is {estimated_bytes} bytes "
                    f"(threshold {WARNING_PACKAGE_BYTES})."
                ),
            )
        )

    return warnings


def _collect_members_and_inventory(
    request: FlowExportRequest,
    *,
    store: LibraryStore,
) -> tuple[dict[str, bytes], list[FlowPackageInventoryItem], list[ReferencedAssetInfo]]:
    mode = validate_packaging_mode(request.packagingMode)
    format_obj = {
        "formatVersion": FLOW_FORMAT_VERSION,
        "packagingMode": mode,
        "createdAt": _utc_now_iso(),
        "app": FLOW_APP_ID,
    }
    members: dict[str, bytes] = {
        FORMAT_JSON: (
            json.dumps(format_obj, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8"),
        WORKFLOW_JSON: (
            request.workflow.model_dump_json(indent=2) + "\n"
        ).encode("utf-8"),
    }

    inventory: list[FlowPackageInventoryItem] = []
    referenced: list[ReferencedAssetInfo] = []

    for asset_id, node_kind in collect_referenced_asset_ids(request.workflow):
        expected_kind = _NODE_KIND_TO_ASSET[node_kind]
        asset = store.get(asset_id)
        if asset is None:
            inventory.append(
                FlowPackageInventoryItem(
                    id=asset_id,
                    kind=expected_kind,
                    name=asset_id,
                    status=ReferencedAssetStatus.MISSING,
                    includesOriginal=False,
                )
            )
            referenced.append(
                ReferencedAssetInfo(
                    id=asset_id,
                    kind=expected_kind,
                    name=asset_id,
                    status=ReferencedAssetStatus.MISSING,
                )
            )
            continue

        manifest: LibraryAssetManifest = asset.manifest
        m_path = manifest_member_path(manifest.kind, manifest.id)
        m_bytes = (manifest.model_dump_json(indent=2) + "\n").encode("utf-8")
        members[m_path] = m_bytes
        member_paths = [m_path]

        embed = includes_original(mode, manifest.kind)
        original_bytes = 0
        original_name: str | None = None
        if embed:
            o_path = original_member_path(manifest)
            o_raw = asset.originalContent.encode("utf-8")
            members[o_path] = o_raw
            member_paths.append(o_path)
            original_bytes = len(o_raw)
            original_name = original_stored_filename(manifest)

        inventory.append(
            FlowPackageInventoryItem(
                id=manifest.id,
                kind=manifest.kind,
                name=manifest.name,
                status=ReferencedAssetStatus.EXPORTED,
                includesOriginal=embed,
                originalFilename=original_name,
                manifestBytes=len(m_bytes),
                originalBytes=original_bytes,
                memberPaths=member_paths,
            )
        )
        referenced.append(
            ReferencedAssetInfo(
                id=manifest.id,
                kind=manifest.kind,
                name=manifest.name,
                status=ReferencedAssetStatus.EXPORTED,
            )
        )

    return members, inventory, referenced


def preview_flow_package(
    request: FlowExportRequest,
    *,
    store: LibraryStore | None = None,
) -> FlowExportPreviewResponse:
    """
    Build an inventory preview for a planned export (Phase 30).

    Does not write a zip; returns member paths, sizes, and size/sensitivity
    warnings so callers can confirm before exporting.
    """
    lib = store if store is not None else get_library_store()
    mode = validate_packaging_mode(request.packagingMode)
    members, inventory, _referenced = _collect_members_and_inventory(
        request, store=lib
    )
    estimated = sum(len(data) for data in members.values())
    # Checksums.json is added at export time; estimate a small overhead.
    checksum_estimate = len(checksums_json_bytes(build_checksums(members)))
    estimated += checksum_estimate

    warnings = _build_warnings(
        packaging_mode=mode,
        inventory=inventory,
        estimated_bytes=estimated,
    )
    for item in inventory:
        if item.status == ReferencedAssetStatus.MISSING:
            warnings.append(
                ValidationIssue(
                    code="missing_referenced_asset",
                    message=(
                        f"Referenced library asset '{item.id}' was not found "
                        "in the local library; export will omit its files."
                    ),
                )
            )

    member_paths = sorted([*members.keys(), CHECKSUMS_JSON])
    return FlowExportPreviewResponse(
        packagingMode=mode,
        formatVersion=FLOW_FORMAT_VERSION,
        assets=inventory,
        memberPaths=member_paths,
        estimatedUncompressedBytes=estimated,
        warnings=warnings,
    )


def export_flow_package(
    request: FlowExportRequest,
    *,
    store: LibraryStore | None = None,
) -> tuple[bytes, list[ReferencedAssetInfo], list[ValidationIssue]]:
    """
    Build a ``.flow`` zip (graph + manifests + optional originals + checksums).

    Packaging modes (Phase 30):
    - ``reference`` — manifests only
    - ``snapshot`` — Skill/Rules ``original.*`` + manifests (KB manifests only)
    - ``embedded`` — all originals including KB source docs

    Returns ``(zip_bytes, referenced_assets, warnings)``.
    """
    lib = store if store is not None else get_library_store()
    mode = validate_packaging_mode(request.packagingMode)
    members, inventory, referenced = _collect_members_and_inventory(
        request, store=lib
    )

    checksums = build_checksums(members)
    members[CHECKSUMS_JSON] = checksums_json_bytes(checksums)

    estimated = sum(len(data) for data in members.values())
    warnings = _build_warnings(
        packaging_mode=mode,
        inventory=inventory,
        estimated_bytes=estimated,
    )
    for item in inventory:
        if item.status == ReferencedAssetStatus.MISSING:
            warnings.append(
                ValidationIssue(
                    code="missing_referenced_asset",
                    message=(
                        f"Referenced library asset '{item.id}' was not found "
                        "in the local library; export will omit its files."
                    ),
                )
            )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(members):
            zf.writestr(path, members[path])

    return buf.getvalue(), referenced, warnings
