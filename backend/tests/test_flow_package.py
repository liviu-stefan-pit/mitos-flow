"""Phase 29–30 — Workflow export/import (.flow zip) + packaging modes."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.flow_package import FlowExportRequest
from mitos_api.domain.workflow import Workflow
from mitos_api.main import app
from mitos_api.services.flow_package import (
    FLOW_FORMAT_VERSION,
    export_flow_package,
    import_flow_package,
    preview_flow_package,
)
from mitos_api.services.flow_package.checksums import (
    build_checksums,
    checksums_json_bytes,
)
from mitos_api.services.flow_package.constants import (
    CHECKSUMS_JSON,
    FORMAT_JSON,
    WORKFLOW_JSON,
)
from mitos_api.services.library import LibraryStore, set_library_store

client = TestClient(app)
LIBRARY_FIXTURES = Path(__file__).parent / "fixtures" / "library"


@pytest.fixture(autouse=True)
def isolated_library(tmp_path: Path):
    store = LibraryStore(root=tmp_path / "library")
    set_library_store(store)
    yield store
    set_library_store(None)


def _read_library(name: str) -> str:
    return (LIBRARY_FIXTURES / name).read_text(encoding="utf-8")


def _import_skill_rules_kb(isolated_library: LibraryStore) -> dict[str, str]:
    """Import one Skill + Rules + KB; return {kind: asset_id}."""
    skill = client.post(
        "/api/library/import",
        json={"filename": "SKILL.md", "content": _read_library("valid_skill.md")},
    ).json()
    assert skill["ok"] is True

    rules = client.post(
        "/api/library/import",
        json={"filename": "tone.mdc", "content": _read_library("valid_rule_a.mdc")},
    ).json()
    assert rules["ok"] is True

    kb_content = (
        "Acme Widget is a durable office gadget.\n\n"
        "It ships with a two-year warranty."
    )
    kb = client.post(
        "/api/library/import",
        json={"filename": "product.txt", "content": kb_content, "kind": "knowledgeBase"},
    ).json()
    assert kb["ok"] is True

    return {
        "skill": skill["asset"]["manifest"]["id"],
        "rules": rules["asset"]["manifest"]["id"],
        "kb": kb["asset"]["manifest"]["id"],
        "skill_body": skill["asset"]["manifest"]["body"],
        "rules_body": rules["asset"]["manifest"]["body"],
        "kb_body": kb["asset"]["manifest"]["body"],
        "skill_name": skill["asset"]["manifest"]["name"],
        "rules_name": rules["asset"]["manifest"]["name"],
        "kb_name": kb["asset"]["manifest"]["name"],
    }


def _workflow_with_refs(ids: dict[str, str]) -> dict:
    return {
        "metadata": {"name": "Reference Portability", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "Brief",
                "position": {"x": 0, "y": 0},
                "settings": {"mediaType": "text/plain", "content": "Hello"},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": ids["skill_name"],
                "position": {"x": 220, "y": 0},
                "settings": {
                    "description": "Draft",
                    "content": ids["skill_body"],
                    "libraryAssetId": ids["skill"],
                    "joinPolicy": "wait_for_all",
                },
            },
            {
                "id": "rules-1",
                "kind": "rules",
                "label": ids["rules_name"],
                "position": {"x": 220, "y": 160},
                "settings": {
                    "description": "Tone",
                    "content": ids["rules_body"],
                    "libraryAssetId": ids["rules"],
                },
            },
            {
                "id": "kb-1",
                "kind": "knowledgeBase",
                "label": ids["kb_name"],
                "position": {"x": 220, "y": -160},
                "settings": {
                    "description": "Product KB",
                    "content": ids["kb_body"],
                    "libraryAssetId": ids["kb"],
                },
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "Out",
                "position": {"x": 440, "y": 0},
                "settings": {"mode": "pass-through"},
            },
        ],
        "edges": [
            {
                "id": "e-data-1",
                "kind": "dataFlow",
                "sourceNodeId": "input-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e-data-2",
                "kind": "dataFlow",
                "sourceNodeId": "skill-1",
                "targetNodeId": "output-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e-res-rules",
                "kind": "resourceAttachment",
                "sourceNodeId": "rules-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "resource-out",
                "targetPortId": "resource-in",
            },
            {
                "id": "e-res-kb",
                "kind": "resourceAttachment",
                "sourceNodeId": "kb-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "resource-out",
                "targetPortId": "resource-in-top",
            },
        ],
    }


def _member_names(zip_bytes: bytes) -> set[str]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return {i.filename for i in zf.infolist() if not i.is_dir()}


def _read_member(zip_bytes: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        return zf.read(name)


def _build_zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, data in sorted(members.items()):
            zf.writestr(path, data)
    return buf.getvalue()


def _signed_members(
    *,
    format_obj: dict,
    workflow: dict,
    assets: dict[str, bytes] | None = None,
) -> dict[str, bytes]:
    members: dict[str, bytes] = {
        FORMAT_JSON: (json.dumps(format_obj, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        ),
        WORKFLOW_JSON: (json.dumps(workflow, indent=2) + "\n").encode("utf-8"),
    }
    if assets:
        members.update(assets)
    checksums = build_checksums(members)
    members[CHECKSUMS_JSON] = checksums_json_bytes(checksums)
    return members


# --- Gate: round-trip ---------------------------------------------------------


def test_round_trip_export_import_restores_graph_and_manifests(
    isolated_library: LibraryStore,
):
    ids = _import_skill_rules_kb(isolated_library)
    workflow_json = _workflow_with_refs(ids)

    export_resp = client.post(
        "/api/workflows/export",
        json={"workflow": workflow_json, "packagingMode": "reference"},
    )
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("application/zip")
    zip_bytes = export_resp.content

    names = _member_names(zip_bytes)
    assert FORMAT_JSON in names
    assert WORKFLOW_JSON in names
    assert CHECKSUMS_JSON in names
    assert f"assets/skills/{ids['skill']}/manifest.json" in names
    assert f"assets/rules/{ids['rules']}/manifest.json" in names
    assert f"assets/kb/{ids['kb']}/manifest.json" in names
    # Reference mode: no KB (or other) source docs.
    assert not any(n.endswith("original.txt") for n in names)
    assert not any("/original." in n for n in names)

    # Fresh instance: wipe library, then import.
    isolated_library.clear()
    assert isolated_library.list_assets() == []

    import_resp = client.post(
        "/api/workflows/import",
        files={"file": ("Reference Portability.flow", zip_bytes, "application/zip")},
    )
    assert import_resp.status_code == 200
    body = import_resp.json()
    assert body["ok"] is True
    assert body["formatVersion"] == FLOW_FORMAT_VERSION
    assert body["packagingMode"] == "reference"
    assert body["workflow"]["metadata"]["name"] == "Reference Portability"

    # Graph settings (inlined content + libraryAssetId) restored.
    skill_node = next(n for n in body["workflow"]["nodes"] if n["id"] == "skill-1")
    assert skill_node["settings"]["libraryAssetId"] == ids["skill"]
    assert skill_node["settings"]["content"] == ids["skill_body"]

    kb_node = next(n for n in body["workflow"]["nodes"] if n["id"] == "kb-1")
    assert kb_node["settings"]["libraryAssetId"] == ids["kb"]
    assert kb_node["settings"]["content"] == ids["kb_body"]

    restored_ids = {a["id"] for a in body["referencedAssets"]}
    assert ids["skill"] in restored_ids
    assert ids["rules"] in restored_ids
    assert ids["kb"] in restored_ids
    assert all(a["status"] == "restored" for a in body["referencedAssets"])

    # Library has manifests again (synthesized originals allow get()).
    assert isolated_library.get(ids["skill"]) is not None
    assert isolated_library.get(ids["rules"]) is not None
    assert isolated_library.get(ids["kb"]) is not None
    assert isolated_library.get(ids["kb"]).manifest.body == ids["kb_body"]


def test_round_trip_service_level_equals_workflow(
    isolated_library: LibraryStore,
):
    ids = _import_skill_rules_kb(isolated_library)
    workflow = Workflow.model_validate(_workflow_with_refs(ids))
    zip_bytes, referenced, warnings = export_flow_package(
        FlowExportRequest(workflow=workflow, packagingMode="reference"),
        store=isolated_library,
    )
    assert warnings == []
    assert len(referenced) == 3

    isolated_library.clear()
    result = import_flow_package(zip_bytes, store=isolated_library)
    assert result.ok is True
    assert result.workflow is not None
    assert result.workflow.model_dump() == workflow.model_dump()


# --- Gate: checksum failure ---------------------------------------------------


def test_checksum_failure_rejects_before_library_write(
    isolated_library: LibraryStore,
):
    ids = _import_skill_rules_kb(isolated_library)
    workflow = Workflow.model_validate(_workflow_with_refs(ids))
    zip_bytes, _, _ = export_flow_package(
        FlowExportRequest(workflow=workflow),
        store=isolated_library,
    )

    # Tamper with workflow.json bytes after signing.
    with zipfile.ZipFile(io.BytesIO(zip_bytes), mode="r") as zf:
        members = {i.filename: zf.read(i) for i in zf.infolist() if not i.is_dir()}
    members[WORKFLOW_JSON] = members[WORKFLOW_JSON] + b"\n"
    tampered = _build_zip(members)

    before = {a.id for a in isolated_library.list_assets()}
    isolated_library.clear()

    result = import_flow_package(tampered, store=isolated_library)
    assert result.ok is False
    assert any(e.code == "checksum_mismatch" for e in result.errors)
    assert isolated_library.list_assets() == []

    # Also via API.
    set_library_store(isolated_library)
    resp = client.post(
        "/api/workflows/import",
        files={"file": ("bad.flow", tampered, "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
    assert resp.json()["errors"][0]["code"] == "checksum_mismatch"
    assert before  # sanity: we had assets before clear


# --- Gate: zip-slip -----------------------------------------------------------


def test_zip_slip_rejected_library_untouched(isolated_library: LibraryStore):
    ids = _import_skill_rules_kb(isolated_library)
    before_count = len(isolated_library.list_assets())

    # Craft a zip with a traversal member; validation must fail before extract.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        zf.writestr("../../etc/passwd", b"root:x:0:0:root:/root:/bin/sh\n")
        zf.writestr(
            FORMAT_JSON,
            json.dumps(
                {
                    "formatVersion": FLOW_FORMAT_VERSION,
                    "packagingMode": "reference",
                    "createdAt": "2026-08-01T00:00:00+00:00",
                    "app": "mitos-flow",
                }
            ).encode(),
        )
    slip_bytes = buf.getvalue()

    result = import_flow_package(slip_bytes, store=isolated_library)
    assert result.ok is False
    assert any(e.code == "zip_slip" for e in result.errors)
    assert len(isolated_library.list_assets()) == before_count
    assert isolated_library.get(ids["skill"]) is not None


def test_zip_slip_assets_relative_traversal(isolated_library: LibraryStore):
    workflow = {
        "metadata": {"name": "x", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "In",
                "position": {"x": 0, "y": 0},
                "settings": {"content": "a"},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": "S",
                "position": {"x": 1, "y": 0},
                "settings": {},
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "O",
                "position": {"x": 2, "y": 0},
                "settings": {"mode": "pass-through"},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "kind": "dataFlow",
                "sourceNodeId": "input-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e2",
                "kind": "dataFlow",
                "sourceNodeId": "skill-1",
                "targetNodeId": "output-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
        ],
    }
    members = {
        FORMAT_JSON: b'{"formatVersion":1,"packagingMode":"reference",'
        b'"createdAt":"2026-08-01T00:00:00+00:00","app":"mitos-flow"}\n',
        WORKFLOW_JSON: (json.dumps(workflow) + "\n").encode(),
        "assets/../secrets.txt": b"nope",
    }
    # Intentionally skip valid checksums — zip-slip must fire first.
    result = import_flow_package(_build_zip(members), store=isolated_library)
    assert result.ok is False
    assert any(e.code == "zip_slip" for e in result.errors)


# --- Gate: unsupported-version ------------------------------------------------


def test_unsupported_format_version(isolated_library: LibraryStore):
    workflow = {
        "metadata": {"name": "x", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "In",
                "position": {"x": 0, "y": 0},
                "settings": {"content": "a"},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": "S",
                "position": {"x": 1, "y": 0},
                "settings": {},
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "O",
                "position": {"x": 2, "y": 0},
                "settings": {"mode": "pass-through"},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "kind": "dataFlow",
                "sourceNodeId": "input-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e2",
                "kind": "dataFlow",
                "sourceNodeId": "skill-1",
                "targetNodeId": "output-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
        ],
    }
    members = _signed_members(
        format_obj={
            "formatVersion": 999,
            "packagingMode": "reference",
            "createdAt": "2026-08-01T00:00:00+00:00",
            "app": "mitos-flow",
        },
        workflow=workflow,
    )
    result = import_flow_package(_build_zip(members), store=isolated_library)
    assert result.ok is False
    assert any(e.code == "unsupported_format_version" for e in result.errors)
    assert isolated_library.list_assets() == []


def test_missing_format_version_unsupported(isolated_library: LibraryStore):
    workflow = {
        "metadata": {"name": "x", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "In",
                "position": {"x": 0, "y": 0},
                "settings": {"content": "a"},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": "S",
                "position": {"x": 1, "y": 0},
                "settings": {},
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "O",
                "position": {"x": 2, "y": 0},
                "settings": {"mode": "pass-through"},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "kind": "dataFlow",
                "sourceNodeId": "input-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e2",
                "kind": "dataFlow",
                "sourceNodeId": "skill-1",
                "targetNodeId": "output-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
        ],
    }
    # Build members without going through FlowFormatInfo (missing version).
    members: dict[str, bytes] = {
        FORMAT_JSON: (
            json.dumps(
                {
                    "packagingMode": "reference",
                    "createdAt": "2026-08-01T00:00:00+00:00",
                    "app": "mitos-flow",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8"),
        WORKFLOW_JSON: (json.dumps(workflow) + "\n").encode("utf-8"),
    }
    members[CHECKSUMS_JSON] = checksums_json_bytes(build_checksums(members))
    result = import_flow_package(_build_zip(members), store=isolated_library)
    assert result.ok is False
    assert any(e.code == "unsupported_format_version" for e in result.errors)


def test_reference_mode_rejects_embedded_original(
    isolated_library: LibraryStore,
):
    """Reference archives must not ship KB source docs."""
    workflow = {
        "metadata": {"name": "x", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "In",
                "position": {"x": 0, "y": 0},
                "settings": {"content": "a"},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": "S",
                "position": {"x": 1, "y": 0},
                "settings": {},
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "O",
                "position": {"x": 2, "y": 0},
                "settings": {"mode": "pass-through"},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "kind": "dataFlow",
                "sourceNodeId": "input-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e2",
                "kind": "dataFlow",
                "sourceNodeId": "skill-1",
                "targetNodeId": "output-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
        ],
    }
    members = _signed_members(
        format_obj={
            "formatVersion": FLOW_FORMAT_VERSION,
            "packagingMode": "reference",
            "createdAt": "2026-08-01T00:00:00+00:00",
            "app": "mitos-flow",
        },
        workflow=workflow,
        assets={"assets/kb/abc/original.txt": b"secret kb source"},
    )
    # Re-sign after adding original — still rejected as unexpected member.
    # _signed_members already signed including the original; import must reject.
    result = import_flow_package(_build_zip(members), store=isolated_library)
    assert result.ok is False
    codes = {e.code for e in result.errors}
    assert "unexpected_member" in codes


def test_sha256_helper_stable():
    data = b"hello"
    assert hashlib.sha256(data).hexdigest() == hashlib.sha256(data).hexdigest()


# --- Phase 30: snapshot / embedded modes + inventory preview ---------------


def test_snapshot_round_trip_includes_skill_rules_originals_not_kb(
    isolated_library: LibraryStore,
):
    ids = _import_skill_rules_kb(isolated_library)
    skill_original = isolated_library.get(ids["skill"]).originalContent
    rules_original = isolated_library.get(ids["rules"]).originalContent
    workflow = Workflow.model_validate(_workflow_with_refs(ids))

    zip_bytes, referenced, warnings = export_flow_package(
        FlowExportRequest(workflow=workflow, packagingMode="snapshot"),
        store=isolated_library,
    )
    assert len(referenced) == 3
    assert not any(w.code == "sensitivity_embedded_kb" for w in warnings)

    names = _member_names(zip_bytes)
    assert f"assets/skills/{ids['skill']}/manifest.json" in names
    assert f"assets/rules/{ids['rules']}/manifest.json" in names
    assert f"assets/kb/{ids['kb']}/manifest.json" in names
    assert any(
        n.startswith(f"assets/skills/{ids['skill']}/original.") for n in names
    )
    assert any(
        n.startswith(f"assets/rules/{ids['rules']}/original.") for n in names
    )
    assert not any(n.startswith(f"assets/kb/{ids['kb']}/original.") for n in names)

    isolated_library.clear()
    result = import_flow_package(zip_bytes, store=isolated_library)
    assert result.ok is True
    assert result.packagingMode == "snapshot"
    assert result.workflow.model_dump() == workflow.model_dump()

    restored_skill = isolated_library.get(ids["skill"])
    restored_rules = isolated_library.get(ids["rules"])
    restored_kb = isolated_library.get(ids["kb"])
    assert restored_skill is not None
    assert restored_rules is not None
    assert restored_kb is not None
    assert restored_skill.originalContent == skill_original
    assert restored_rules.originalContent == rules_original
    # KB restored from manifest body (no embedded original).
    assert restored_kb.manifest.body == ids["kb_body"]


def test_embedded_round_trip_includes_kb_original(
    isolated_library: LibraryStore,
):
    ids = _import_skill_rules_kb(isolated_library)
    kb_original = isolated_library.get(ids["kb"]).originalContent
    skill_original = isolated_library.get(ids["skill"]).originalContent
    workflow = Workflow.model_validate(_workflow_with_refs(ids))

    zip_bytes, referenced, warnings = export_flow_package(
        FlowExportRequest(workflow=workflow, packagingMode="embedded"),
        store=isolated_library,
    )
    assert len(referenced) == 3
    assert any(w.code == "sensitivity_embedded_kb" for w in warnings)

    names = _member_names(zip_bytes)
    kb_original_members = [
        n for n in names if n.startswith(f"assets/kb/{ids['kb']}/original.")
    ]
    assert len(kb_original_members) == 1
    assert _read_member(zip_bytes, kb_original_members[0]).decode("utf-8") == kb_original
    assert any(
        n.startswith(f"assets/skills/{ids['skill']}/original.") for n in names
    )

    isolated_library.clear()
    result = import_flow_package(zip_bytes, store=isolated_library)
    assert result.ok is True
    assert result.packagingMode == "embedded"
    assert result.workflow.model_dump() == workflow.model_dump()

    restored_kb = isolated_library.get(ids["kb"])
    restored_skill = isolated_library.get(ids["skill"])
    assert restored_kb is not None
    assert restored_skill is not None
    assert restored_kb.originalContent == kb_original
    assert restored_skill.originalContent == skill_original


def test_each_packaging_mode_api_round_trip(isolated_library: LibraryStore):
    """Gate: each packaging mode has a round-trip via the HTTP API."""
    ids = _import_skill_rules_kb(isolated_library)
    workflow_json = _workflow_with_refs(ids)

    for mode in ("reference", "snapshot", "embedded"):
        export_resp = client.post(
            "/api/workflows/export",
            json={"workflow": workflow_json, "packagingMode": mode},
        )
        assert export_resp.status_code == 200, mode
        zip_bytes = export_resp.content
        names = _member_names(zip_bytes)

        if mode == "reference":
            assert not any("/original." in n for n in names)
        elif mode == "snapshot":
            assert any("/skills/" in n and "/original." in n for n in names)
            assert not any("/kb/" in n and "/original." in n for n in names)
        else:
            assert any("/kb/" in n and "/original." in n for n in names)

        isolated_library.clear()
        import_resp = client.post(
            "/api/workflows/import",
            files={"file": (f"{mode}.flow", zip_bytes, "application/zip")},
        )
        assert import_resp.status_code == 200, mode
        body = import_resp.json()
        assert body["ok"] is True, mode
        assert body["packagingMode"] == mode
        assert body["workflow"]["metadata"]["name"] == "Reference Portability"

        # Re-import library assets for the next mode iteration.
        ids = _import_skill_rules_kb(isolated_library)
        workflow_json = _workflow_with_refs(ids)


def test_embedded_preview_matches_bundle_contents(
    isolated_library: LibraryStore,
):
    """Manual-check gate: export embedded; bundle members match preview."""
    ids = _import_skill_rules_kb(isolated_library)
    workflow_json = _workflow_with_refs(ids)

    preview_resp = client.post(
        "/api/workflows/export/preview",
        json={"workflow": workflow_json, "packagingMode": "embedded"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["packagingMode"] == "embedded"
    assert preview["formatVersion"] == FLOW_FORMAT_VERSION
    assert any(w["code"] == "sensitivity_embedded_kb" for w in preview["warnings"])

    # Inventory lists Skill + Rules + KB with originals.
    by_id = {a["id"]: a for a in preview["assets"]}
    assert by_id[ids["skill"]]["includesOriginal"] is True
    assert by_id[ids["rules"]]["includesOriginal"] is True
    assert by_id[ids["kb"]]["includesOriginal"] is True
    assert by_id[ids["kb"]]["originalBytes"] > 0

    export_resp = client.post(
        "/api/workflows/export",
        json={"workflow": workflow_json, "packagingMode": "embedded"},
    )
    assert export_resp.status_code == 200
    names = _member_names(export_resp.content)

    preview_paths = set(preview["memberPaths"])
    assert names == preview_paths

    # Every inventory memberPath appears in the zip.
    for asset in preview["assets"]:
        for path in asset["memberPaths"]:
            assert path in names


def test_snapshot_preview_excludes_kb_original(
    isolated_library: LibraryStore,
):
    ids = _import_skill_rules_kb(isolated_library)
    workflow = Workflow.model_validate(_workflow_with_refs(ids))
    preview = preview_flow_package(
        FlowExportRequest(workflow=workflow, packagingMode="snapshot"),
        store=isolated_library,
    )
    kb_item = next(a for a in preview.assets if a.id == ids["kb"])
    skill_item = next(a for a in preview.assets if a.id == ids["skill"])
    assert kb_item.includesOriginal is False
    assert skill_item.includesOriginal is True
    assert not any(
        p.startswith(f"assets/kb/{ids['kb']}/original.") for p in preview.memberPaths
    )
    assert not any(w.code == "sensitivity_embedded_kb" for w in preview.warnings)


def test_snapshot_mode_rejects_kb_original_on_import(
    isolated_library: LibraryStore,
):
    workflow = {
        "metadata": {"name": "x", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "In",
                "position": {"x": 0, "y": 0},
                "settings": {"content": "a"},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": "S",
                "position": {"x": 1, "y": 0},
                "settings": {},
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "O",
                "position": {"x": 2, "y": 0},
                "settings": {"mode": "pass-through"},
            },
        ],
        "edges": [
            {
                "id": "e1",
                "kind": "dataFlow",
                "sourceNodeId": "input-1",
                "targetNodeId": "skill-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
            {
                "id": "e2",
                "kind": "dataFlow",
                "sourceNodeId": "skill-1",
                "targetNodeId": "output-1",
                "sourcePortId": "data-out",
                "targetPortId": "data-in",
            },
        ],
    }
    members = _signed_members(
        format_obj={
            "formatVersion": FLOW_FORMAT_VERSION,
            "packagingMode": "snapshot",
            "createdAt": "2026-08-01T00:00:00+00:00",
            "app": "mitos-flow",
        },
        workflow=workflow,
        assets={"assets/kb/abc/original.txt": b"secret kb source"},
    )
    result = import_flow_package(_build_zip(members), store=isolated_library)
    assert result.ok is False
    assert any(e.code == "unexpected_member" for e in result.errors)


def test_unsupported_packaging_mode_rejected(isolated_library: LibraryStore):
    ids = _import_skill_rules_kb(isolated_library)
    workflow_json = _workflow_with_refs(ids)
    resp = client.post(
        "/api/workflows/export",
        json={"workflow": workflow_json, "packagingMode": "bundle"},
    )
    assert resp.status_code == 422  # pydantic validation


def test_large_package_warning(isolated_library: LibraryStore, monkeypatch):
    from mitos_api.services.flow_package import export as export_mod

    monkeypatch.setattr(export_mod, "WARNING_PACKAGE_BYTES", 100)
    ids = _import_skill_rules_kb(isolated_library)
    workflow = Workflow.model_validate(_workflow_with_refs(ids))
    preview = preview_flow_package(
        FlowExportRequest(workflow=workflow, packagingMode="embedded"),
        store=isolated_library,
    )
    assert any(w.code == "large_package" for w in preview.warnings)
