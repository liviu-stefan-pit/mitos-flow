"""
Phase 31 — End-to-end regression suite (API workflow stories).

Extends the Phase 20.5 fake-run harness with:
- Complete fake-run + ``.flow`` portability (export → wipe library → import → re-run)
- Fuller matrix (three-output fan-out: pass-through / selector / prompted)
- Cursor stubbed (no real CLI tokens in CI)
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain import Workflow
from mitos_api.domain.cursor import CursorFeatureFlags
from mitos_api.domain.library import AssetKind, LibraryImportRequest
from mitos_api.main import app
from mitos_api.services.library.service import confirm_import
from mitos_api.services.library.store import LibraryStore, set_library_store
from mitos_api.services.run_store import run_store
from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.runs import execute_run

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYGROUND = REPO_ROOT / "playground"
FIXTURES = Path(__file__).parent / "fixtures"
STUBS = FIXTURES / "cursor_stubs"

TERMINAL = {"completed", "failed", "cancelled", "rejected"}

FULL_FEATURES = CursorFeatureFlags(
    printMode=True,
    outputFormat=True,
    workspace=True,
    force=False,
    model=True,
    listModels=True,
    trust=True,
    apiKey=False,
    streamPartialOutput=False,
)


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _wait_run(run_id: str, *, timeout: float = 8.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in TERMINAL:
            return last
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not finish; last={last}")


def _post_and_wait(payload: dict, *, timeout: float = 8.0) -> dict:
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 200
    body = response.json()
    if body["status"] == "rejected":
        return body
    assert body["status"] == "queued"
    return _wait_run(body["id"], timeout=timeout)


def _results_by_id(body: dict) -> dict[str, dict]:
    return {r["nodeId"]: r for r in body["nodeResults"]}


def _import_playground_asset(
    store: LibraryStore, relative_path: str, *, kind: AssetKind | None = None
) -> dict:
    path = PLAYGROUND / relative_path
    content = path.read_text(encoding="utf-8")
    request = LibraryImportRequest(filename=path.name, content=content, kind=kind)
    result = confirm_import(request, store=store)
    assert result.ok, result.errors
    assert result.asset is not None
    return result.asset.manifest.model_dump(mode="json")


def _build_portability_workflow(
    *,
    skill_id: str,
    skill_name: str,
    skill_body: str,
    no_facts_id: str,
    no_facts_body: str,
    structure_id: str,
    structure_body: str,
    kb_id: str,
    kb_body: str,
    input_content: str,
) -> dict:
    """Golden Input→Skill(+Rules/KB)→Output with libraryAssetId refs for packaging."""
    return {
        "metadata": {"name": "Phase 31 portability story", "schemaVersion": 1},
        "nodes": [
            {
                "id": "input-1",
                "kind": "input",
                "label": "Brief",
                "position": {"x": 0, "y": 0},
                "settings": {"mediaType": "text/plain", "content": input_content},
            },
            {
                "id": "skill-1",
                "kind": "skill",
                "label": skill_name,
                "position": {"x": 220, "y": 0},
                "settings": {
                    "description": "Answer using attached rules and KB",
                    "content": skill_body,
                    "libraryAssetId": skill_id,
                    "joinPolicy": "wait_for_all",
                    "runner": "fake",
                },
            },
            {
                "id": "rules-no-invented-facts",
                "kind": "rules",
                "label": "no-invented-facts",
                "position": {"x": 40, "y": 160},
                "settings": {
                    "description": "",
                    "content": no_facts_body,
                    "libraryAssetId": no_facts_id,
                },
            },
            {
                "id": "rules-prefer-explicit-structure",
                "kind": "rules",
                "label": "prefer-explicit-structure",
                "position": {"x": 40, "y": 280},
                "settings": {
                    "description": "",
                    "content": structure_body,
                    "libraryAssetId": structure_id,
                },
            },
            {
                "id": "kb-product-overview",
                "kind": "knowledgeBase",
                "label": "product-overview",
                "position": {"x": 220, "y": 400},
                "settings": {
                    "description": "",
                    "content": kb_body,
                    "libraryAssetId": kb_id,
                },
            },
            {
                "id": "output-1",
                "kind": "artifactOutput",
                "label": "Save",
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
                "id": "e-res-facts",
                "kind": "resourceAttachment",
                "sourceNodeId": "rules-no-invented-facts",
                "targetNodeId": "skill-1",
                "sourcePortId": "resource-out",
                "targetPortId": "resource-in",
            },
            {
                "id": "e-res-structure",
                "kind": "resourceAttachment",
                "sourceNodeId": "rules-prefer-explicit-structure",
                "targetNodeId": "skill-1",
                "sourcePortId": "resource-out",
                "targetPortId": "resource-in",
            },
            {
                "id": "e-res-kb",
                "kind": "resourceAttachment",
                "sourceNodeId": "kb-product-overview",
                "targetNodeId": "skill-1",
                "sourcePortId": "resource-out",
                "targetPortId": "resource-in",
                "settings": {"topK": 5, "threshold": 0},
            },
        ],
    }


class EchoThenPromptRunner:
    """Skill echoes input JSON; prompted outputs use FakeRunner projection."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._fake = FakeRunner()

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        self.calls.append(request.skillNodeId)
        if request.promptTemplate:
            return self._fake.execute(request)
        if request.inputs:
            payload = request.inputs[0].payload
            media_type = request.inputs[0].mediaType or "text/plain"
        else:
            payload = request.inputPayload
            media_type = request.inputMediaType or "text/plain"
        return SkillExecutionResult(outputPayload=payload, mediaType=media_type)

    def cleanup(self, skill_node_id: str) -> None:
        self._fake.cleanup(skill_node_id)


def _write_stub_wrapper(tmp_path: Path, script_name: str, wrapper_stem: str) -> str:
    """Spawnable stub executable (Windows ``.cmd`` / POSIX shell)."""
    if sys.platform == "win32":
        wrapper = tmp_path / f"{wrapper_stem}.cmd"
        if script_name == "stub_ok.py":
            body = "@echo off\r\necho STUB_OK:Hello from input\r\nexit /b 0\r\n"
        else:
            raise AssertionError(f"unsupported stub for cmd wrapper: {script_name}")
        wrapper.write_text(body, encoding="utf-8")
        return str(wrapper)

    launcher = tmp_path / f"{wrapper_stem}.py"
    launcher.write_text(
        (STUBS / script_name).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    shell = tmp_path / wrapper_stem
    shell.write_text(
        f"#!/bin/sh\nexec {sys.executable!s} {launcher!s} \"$@\"\n",
        encoding="utf-8",
    )
    shell.chmod(0o755)
    return str(shell)


def test_portability_story_export_wipe_import_rerun(tmp_path: Path):
    """
    Gate story: fake-run → export embedded ``.flow`` → wipe library → import → re-run.

    Locks Phases 17–20 + 29–30 together: a portable package must restore enough
    state that the same fake-run product story completes with identical output.
    """
    run_store.clear()
    store = LibraryStore(root=tmp_path / "library")
    set_library_store(store)

    try:
        skill = _import_playground_asset(store, "skills/draft-brief/SKILL.md")
        no_facts = _import_playground_asset(store, "rules/no-invented-facts.mdc")
        structure = _import_playground_asset(
            store, "rules/prefer-explicit-structure.mdc"
        )
        kb_overview = _import_playground_asset(store, "kb/product-overview.md")

        input_content = (
            "What is Mitos Flow and how does it handle named inputs and joins?"
        )
        workflow_json = _build_portability_workflow(
            skill_id=skill["id"],
            skill_name=skill["name"],
            skill_body=skill["body"],
            no_facts_id=no_facts["id"],
            no_facts_body=no_facts["body"],
            structure_id=structure["id"],
            structure_body=structure["body"],
            kb_id=kb_overview["id"],
            kb_body=kb_overview["body"],
            input_content=input_content,
        )
        Workflow.model_validate(workflow_json)

        before = _post_and_wait(
            {"workflow": workflow_json, "options": {"delayMs": 0}}
        )
        assert before["status"] == "completed", before
        assert before["errors"] == []
        before_output = before["output"]
        assert before_output.startswith(f"fake::{skill['name']}::{input_content}")
        assert "::rules[" in before_output
        assert "::kb[" in before_output
        assert before["summary"] is not None
        assert before["summary"]["costIsEstimate"] is True

        preview = client.post(
            "/api/workflows/export/preview",
            json={"workflow": workflow_json, "packagingMode": "embedded"},
        )
        assert preview.status_code == 200
        preview_body = preview.json()
        assert preview_body["packagingMode"] == "embedded"
        assert len(preview_body["memberPaths"]) >= 4

        export_resp = client.post(
            "/api/workflows/export",
            json={"workflow": workflow_json, "packagingMode": "embedded"},
        )
        assert export_resp.status_code == 200
        zip_bytes = export_resp.content
        assert zip_bytes[:2] == b"PK"

        # Fresh instance: wipe managed library, then import the package.
        store.clear()
        assert store.list_assets() == []

        import_resp = client.post(
            "/api/workflows/import",
            files={"file": ("portability.flow", zip_bytes, "application/zip")},
        )
        assert import_resp.status_code == 200
        imported = import_resp.json()
        assert imported["ok"] is True
        assert imported["packagingMode"] == "embedded"
        assert imported["workflow"] is not None
        restored_ids = {a["id"] for a in imported["referencedAssets"]}
        assert skill["id"] in restored_ids
        assert no_facts["id"] in restored_ids
        assert structure["id"] in restored_ids
        assert kb_overview["id"] in restored_ids
        assert {a["status"] for a in imported["referencedAssets"]} == {"restored"}

        after = _post_and_wait(
            {"workflow": imported["workflow"], "options": {"delayMs": 0}}
        )
        assert after["status"] == "completed", after
        assert after["output"] == before_output

        after_skill = _results_by_id(after)["skill-1"]
        assert after_skill["knowledgeQuery"] == input_content
        assert len(after_skill["knowledgeChunks"]) >= 1
        assert len(after_skill["attachedRules"]) == 2
    finally:
        set_library_store(None)


def test_three_output_matrix_story():
    """
    Fuller matrix: one Skill → pass-through + selector + prompted (2 model calls).

    Regression lock for Phases 25–27 working together after packaging phases.
    """
    run_store.clear()
    workflow = Workflow.model_validate(_load_fixture("prompted_three_outputs.json"))
    runner = EchoThenPromptRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    assert runner.calls == ["skill-1", "output-3"]
    by_id = {r.nodeId: r for r in result.nodeResults}

    assert by_id["output-1"].state.value == "completed"
    assert "full body for prompt" in (by_id["output-1"].output or "")

    assert by_id["output-2"].state.value == "completed"
    assert by_id["output-2"].output == "Extract me with JSONPath"

    assert by_id["output-3"].state.value == "completed"
    assert (by_id["output-3"].output or "").startswith("fake::prompted::Summary::")
    assert by_id["output-3"].output != by_id["output-1"].output

    assert result.summary is not None
    assert result.summary.costIsEstimate is True


def test_cursor_stub_story(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Cursor stubbed in CI: Input → Cursor Skill → Output with a local stub executable.

    Never spawns a real Cursor CLI — Phase 31 documents the manual smoke separately.
    """
    run_store.clear()
    monkeypatch.setenv("MITOS_CURSOR_WORKSPACE_ROOT", str(tmp_path))
    executable = _write_stub_wrapper(tmp_path, "stub_ok.py", "stub_agent")
    workflow = _load_fixture("cursor_simple_linear.json")
    # Per-Skill Cursor runner (Phase 24) so the story matches the UI path.
    workflow["nodes"][1]["settings"]["runner"] = "cursor"
    workflow["nodes"][1]["settings"]["model"] = "composer-2.5"

    finished = _post_and_wait(
        {
            "workflow": workflow,
            "options": {
                "delayMs": 0,
                "cursor": {
                    "executable": executable,
                    "workspace": str(tmp_path),
                    "features": FULL_FEATURES.model_dump(),
                    "timeoutMs": 10_000,
                    "confirmed": True,
                },
            },
        },
        timeout=15.0,
    )
    assert finished["status"] == "completed", finished
    assert finished["output"] == "STUB_OK:Hello from input"
    by_id = _results_by_id(finished)
    assert by_id["skill-1"]["exitCode"] == 0
    assert "STUB_OK" in (by_id["skill-1"]["stdout"] or "")
    assert by_id["skill-1"].get("model") == "composer-2.5"
