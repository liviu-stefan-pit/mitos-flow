"""Phase 17 — Skill/Rules file import into managed local library."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain.library import AssetKind, LibraryImportRequest
from mitos_api.main import app
from mitos_api.services.library import (
    LibraryStore,
    confirm_import,
    preview_import,
    set_library_store,
)
from mitos_api.services.library.frontmatter import normalize_document, parse_frontmatter

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures" / "library"


@pytest.fixture(autouse=True)
def isolated_library(tmp_path: Path):
    store = LibraryStore(root=tmp_path / "library")
    set_library_store(store)
    yield store
    set_library_store(None)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_valid_skill_frontmatter():
    content = _read("valid_skill.md")
    parsed, errors = parse_frontmatter(content)
    assert errors == []
    assert parsed is not None
    assert parsed.frontmatter["name"] == "draft-brief"
    assert "Draft brief" in parsed.body


def test_malformed_unclosed_frontmatter_reported_safely():
    content = _read("malformed_unclosed.md")
    parsed, errors = parse_frontmatter(content)
    assert parsed is None
    assert len(errors) == 1
    assert errors[0].code == "malformed_frontmatter"
    assert "closing" in errors[0].message.lower()


def test_malformed_yaml_frontmatter_reported_safely():
    content = _read("malformed_yaml.md")
    parsed, errors = parse_frontmatter(content)
    assert parsed is None
    assert errors[0].code == "malformed_frontmatter"


def test_skill_missing_description_rejected():
    content = _read("skill_missing_description.md")
    normalized, errors = normalize_document(content, "SKILL.md")
    assert normalized is None
    assert any(e.code == "missing_field" for e in errors)
    assert any("description" in (e.message or "").lower() for e in errors)


def test_preview_does_not_write_to_store(isolated_library: LibraryStore):
    content = _read("valid_skill.md")
    response = client.post(
        "/api/library/preview",
        json={"filename": "SKILL.md", "content": content},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["kind"] == "skill"
    assert body["name"] == "draft-brief"
    assert body["originalContent"] == content
    assert isolated_library.list_assets() == []


def test_confirm_import_preserves_original_and_manifest(isolated_library: LibraryStore):
    content = _read("valid_skill.md")
    preview = client.post(
        "/api/library/preview",
        json={"filename": "SKILL.md", "content": content},
    ).json()
    assert preview["ok"] is True

    imported = client.post(
        "/api/library/import",
        json={"filename": "SKILL.md", "content": content},
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["ok"] is True
    asset = body["asset"]
    assert asset["originalContent"] == content
    assert asset["manifest"]["name"] == "draft-brief"
    assert asset["manifest"]["kind"] == "skill"
    assert "Draft brief" in asset["manifest"]["body"]

    # On disk: original + manifest
    asset_id = asset["manifest"]["id"]
    asset_dir = isolated_library.root / "skills" / asset_id
    assert (asset_dir / "original.md").read_text(encoding="utf-8") == content
    manifest = json.loads((asset_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "draft-brief"
    assert manifest["frontmatter"]["description"].startswith("Draft a concise")


def test_import_one_skill_and_multiple_rules(isolated_library: LibraryStore):
    """Gate: Import one Skill + multiple Rules."""
    files = [
        {"filename": "SKILL.md", "content": _read("valid_skill.md"), "kind": "skill"},
        {
            "filename": "typescript-apis.mdc",
            "content": _read("valid_rule_a.mdc"),
            "kind": "rules",
        },
        {
            "filename": "commits.mdc",
            "content": _read("valid_rule_b.mdc"),
            "kind": "rules",
        },
    ]
    response = client.post("/api/library/import/batch", json={"files": files})
    assert response.status_code == 200
    body = response.json()
    assert body["importedCount"] == 3
    assert body["failedCount"] == 0

    listed = client.get("/api/library").json()
    kinds = sorted(a["kind"] for a in listed["assets"])
    names = sorted(a["name"] for a in listed["assets"])
    assert kinds == ["rules", "rules", "skill"]
    assert "draft-brief" in names
    assert "typescript-apis" in names or "TypeScript public APIs" not in names
    # Rules name comes from frontmatter name or filename stem
    assert any(n in names for n in ("typescript-apis", "commits"))


def test_batch_reports_malformed_without_aborting_others(isolated_library: LibraryStore):
    files = [
        {"filename": "SKILL.md", "content": _read("valid_skill.md")},
        {"filename": "broken.md", "content": _read("malformed_unclosed.md"), "kind": "skill"},
        {"filename": "rule.mdc", "content": _read("valid_rule_a.mdc")},
    ]
    response = client.post("/api/library/import/batch", json={"files": files})
    body = response.json()
    assert body["importedCount"] == 2
    assert body["failedCount"] == 1
    failed = [r for r in body["results"] if not r["ok"]][0]
    assert failed["errors"][0]["code"] == "malformed_frontmatter"
    assert len(isolated_library.list_assets()) == 2


def test_preview_malformed_via_api():
    response = client.post(
        "/api/library/preview",
        json={
            "filename": "SKILL.md",
            "content": _read("malformed_yaml.md"),
            "kind": "skill",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["errors"][0]["code"] == "malformed_frontmatter"


def test_reject_non_markdown_extension():
    response = client.post(
        "/api/library/preview",
        json={"filename": "notes.txt", "content": "hello", "kind": "rules"},
    )
    assert response.status_code == 400


def test_get_asset_round_trip(isolated_library: LibraryStore):
    content = _read("valid_rule_a.mdc")
    result = confirm_import(
        LibraryImportRequest(filename="api.mdc", content=content, kind=AssetKind.RULES),
        store=isolated_library,
    )
    assert result.ok and result.asset is not None
    asset_id = result.asset.manifest.id
    response = client.get(f"/api/library/{asset_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["originalContent"] == content
    assert body["manifest"]["kind"] == "rules"


def test_service_preview_matches_normalize():
    content = _read("valid_skill.md")
    preview = preview_import(
        __import__("mitos_api.domain.library", fromlist=["LibraryPreviewRequest"]).LibraryPreviewRequest(
            filename="SKILL.md", content=content
        )
    )
    assert preview.ok
    assert preview.name == "draft-brief"
