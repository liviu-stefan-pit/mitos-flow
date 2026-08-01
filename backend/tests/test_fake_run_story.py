"""
Phase 20.5 — Fake-run regression harness (API workflow stories).

These tests chain real services end to end (library import -> workflow
construction -> POST /api/runs -> SSE-equivalent event log) instead of
exercising isolated units. They exist to lock the fake-runner product story
before the Cursor CLI phases (21-24) start changing execution internals.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mitos_api.domain import Workflow
from mitos_api.domain.library import AssetKind, LibraryImportRequest
from mitos_api.main import app
from mitos_api.services.library.service import confirm_import
from mitos_api.services.library.store import LibraryStore
from mitos_api.services.run_store import run_store
from mitos_api.services.runs import execute_run

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYGROUND = REPO_ROOT / "playground"
FIXTURES = Path(__file__).parent / "fixtures"

TERMINAL = {"completed", "failed", "cancelled", "rejected"}


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _wait_run(run_id: str, *, timeout: float = 5.0) -> dict:
    """Poll GET /api/runs/{id} until the run reaches a terminal status."""
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


def _post_and_wait(payload: dict, *, timeout: float = 5.0) -> dict:
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
    """Import a real playground file through the managed-library service."""
    path = PLAYGROUND / relative_path
    content = path.read_text(encoding="utf-8")
    request = LibraryImportRequest(filename=path.name, content=content, kind=kind)
    result = confirm_import(request, store=store)
    assert result.ok, result.errors
    assert result.asset is not None
    return result.asset.manifest.model_dump(mode="json")


def _build_golden_workflow(
    *, no_facts_body: str, structure_body: str, kb_body: str, input_content: str
) -> dict:
    """
    Input -> Skill (+2 Rules, +1 KB resource attachments) -> Artifact Output.

    Mirrors the canonical fake-run product story: import -> attach -> run.
    """
    return {
        "metadata": {"name": "Phase 20.5 golden story", "schemaVersion": 1},
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
                "label": "Draft",
                "position": {"x": 220, "y": 0},
                "settings": {
                    "description": "Answer using attached rules and KB",
                    "joinPolicy": "wait_for_all",
                },
            },
            {
                "id": "rules-no-invented-facts",
                "kind": "rules",
                "label": "no-invented-facts",
                "position": {"x": 40, "y": 160},
                "settings": {"description": "", "content": no_facts_body},
            },
            {
                "id": "rules-prefer-explicit-structure",
                "kind": "rules",
                "label": "prefer-explicit-structure",
                "position": {"x": 40, "y": 280},
                "settings": {"description": "", "content": structure_body},
            },
            {
                "id": "kb-product-overview",
                "kind": "knowledgeBase",
                "label": "product-overview",
                "position": {"x": 220, "y": 400},
                "settings": {"description": "", "content": kb_body},
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


def test_golden_story_import_attach_run_trace(tmp_path):
    """
    Playground import -> attach Rules+KB to a Skill -> fake run -> SSE trace.

    Regression lock for Phases 17-20 working together: this is the exact
    product story Cursor phases (21-24) must not silently break.
    """
    run_store.clear()
    store = LibraryStore(root=tmp_path / "library")

    no_facts = _import_playground_asset(store, "rules/no-invented-facts.mdc")
    structure = _import_playground_asset(store, "rules/prefer-explicit-structure.mdc")
    kb_overview = _import_playground_asset(store, "kb/product-overview.md")

    assert no_facts["kind"] == "rules"
    assert structure["kind"] == "rules"
    assert kb_overview["kind"] == "knowledgeBase"

    input_content = "What is Mitos Flow and how does it handle named inputs and joins?"
    workflow_json = _build_golden_workflow(
        no_facts_body=no_facts["body"],
        structure_body=structure["body"],
        kb_body=kb_overview["body"],
        input_content=input_content,
    )

    # Validate the constructed workflow through the real domain model too.
    Workflow.model_validate(workflow_json)

    body = _post_and_wait({"workflow": workflow_json, "options": {"delayMs": 10}})
    assert body["status"] == "completed"
    assert body["errors"] == []

    by_id = _results_by_id(body)
    skill_result = by_id["skill-1"]

    # Rules: both attached, ordered, content visible in the trace.
    assert skill_result["state"] == "completed"
    rule_ids = {r["rulesNodeId"] for r in skill_result["attachedRules"]}
    assert rule_ids == {"rules-no-invented-facts", "rules-prefer-explicit-structure"}

    # KB: query recorded, at least one cited chunk with a citation string.
    assert skill_result["knowledgeQuery"] == input_content
    assert len(skill_result["knowledgeChunks"]) >= 1
    for chunk in skill_result["knowledgeChunks"]:
        assert chunk["kbNodeId"] == "kb-product-overview"
        assert chunk["citation"].startswith("product-overview#")
        assert chunk["chunkId"].startswith("kb-product-overview:c")

    # Fake output composes input + rules + kb suffixes deterministically.
    output = skill_result["output"]
    assert output.startswith(f"fake::Draft::{input_content}")
    assert "::rules[" in output
    assert "::kb[" in output
    assert body["output"] == output

    # SSE-equivalent event log (returned in the terminal snapshot) carries
    # the same query/citations the UI Activity timeline renders.
    skill_completed_events = [
        e
        for e in body["events"]
        if e.get("nodeId") == "skill-1" and e["type"] == "completed"
    ]
    assert len(skill_completed_events) == 1
    event = skill_completed_events[0]
    assert event["knowledgeQuery"] == input_content
    assert len(event["knowledgeChunks"]) == len(skill_result["knowledgeChunks"])
    assert len(event["attachedRules"]) == 2


def test_cancel_mid_chain_story():
    """
    Cancel a delayed linear chain after the first Skill starts running.

    Regression lock: downstream Skill/Output must never complete once a run
    is cancelled, independent of how Cursor execution (23-24) is wired in.
    """
    run_store.clear()
    payload = {
        "workflow": _load_fixture("linear_chain.json"),
        "options": {"delayMs": 150},
    }
    created = client.post("/api/runs", json=payload)
    assert created.status_code == 200
    run_id = created.json()["id"]

    deadline = time.monotonic() + 3
    saw_skill_running = False
    while time.monotonic() < deadline:
        snap = client.get(f"/api/runs/{run_id}").json()
        if any(
            e.get("nodeId") == "skill-1" and e.get("type") == "running"
            for e in snap.get("events", [])
        ):
            saw_skill_running = True
            break
        time.sleep(0.02)
    assert saw_skill_running

    cancelled = client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["cancelRequested"] is True

    final = _wait_run(run_id)
    assert final["status"] == "cancelled"
    by_id = _results_by_id(final)
    assert by_id.get("skill-2", {}).get("state") != "completed"
    assert by_id.get("output-1", {}).get("state") != "completed"


def test_linear_chain_composes_nested_fake_output():
    """
    Draft -> Polish composition stays nested and deterministic.

    Regression lock for the scheduler ordering that Phase 24 (per-node
    Fake-or-Cursor execution) must preserve.
    """
    run_store.clear()
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    result = execute_run(workflow)

    assert result.status == "completed"
    expected = "fake::Polish::fake::Draft::Hello from input"
    assert result.output == expected

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].output == "fake::Draft::Hello from input"
    assert by_id["skill-2"].output == expected
    assert by_id["output-1"].output == expected
