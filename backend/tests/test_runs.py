"""Phase 11 — fake runner + synchronous POST /api/runs integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from mitos_api.domain import Workflow
from mitos_api.main import app
from mitos_api.services.runners import FakeRunner, SkillExecutionRequest
from mitos_api.services.runs import execute_run

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"

EXPECTED_FAKE_OUTPUT = "fake::Draft::Hello from input"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _results_by_id(body: dict) -> dict[str, dict]:
    return {r["nodeId"]: r for r in body["nodeResults"]}


def test_fake_runner_is_deterministic():
    runner = FakeRunner()
    request = SkillExecutionRequest(
        skillNodeId="skill-1",
        skillLabel="Draft",
        description="Draft the reply",
        inputPayload="Hello from input",
        inputMediaType="text/plain",
    )
    first = runner.execute(request)
    second = runner.execute(request)

    assert first.outputPayload == EXPECTED_FAKE_OUTPUT
    assert first.mediaType == "text/plain"
    assert second.outputPayload == first.outputPayload


def test_execute_simple_linear_exact_io_and_node_states():
    workflow = Workflow.model_validate(_load_fixture("simple_linear.json"))
    result = execute_run(workflow)

    assert result.status == "completed"
    assert result.output == EXPECTED_FAKE_OUTPUT
    assert result.mediaType == "text/plain"
    assert result.errors == []

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert set(by_id) == {"input-1", "skill-1", "output-1"}

    assert by_id["input-1"].state.value == "completed"
    assert by_id["input-1"].output == "Hello from input"
    assert by_id["input-1"].mediaType == "text/plain"

    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].output == EXPECTED_FAKE_OUTPUT

    assert by_id["output-1"].state.value == "completed"
    assert by_id["output-1"].output == EXPECTED_FAKE_OUTPUT


def test_execute_valid_linear_skips_resource_nodes():
    """KB/Rules may be attached but are not executed in Phase 11."""
    workflow = Workflow.model_validate(_load_fixture("valid_linear.json"))
    result = execute_run(workflow)

    assert result.status == "completed"
    assert result.output == EXPECTED_FAKE_OUTPUT

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["kb-1"].state.value == "skipped"
    assert by_id["rules-1"].state.value == "skipped"
    assert by_id["skill-1"].output == EXPECTED_FAKE_OUTPUT
    assert by_id["output-1"].output == EXPECTED_FAKE_OUTPUT


def test_runs_endpoint_simple_linear():
    payload = {"workflow": _load_fixture("simple_linear.json")}
    response = client.post("/api/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["output"] == EXPECTED_FAKE_OUTPUT
    assert body["mediaType"] == "text/plain"
    assert body["id"]
    assert body["errors"] == []

    by_id = _results_by_id(body)
    assert by_id["input-1"]["state"] == "completed"
    assert by_id["input-1"]["output"] == "Hello from input"
    assert by_id["skill-1"]["state"] == "completed"
    assert by_id["skill-1"]["output"] == EXPECTED_FAKE_OUTPUT
    assert by_id["output-1"]["state"] == "completed"
    assert by_id["output-1"]["output"] == EXPECTED_FAKE_OUTPUT


def test_runs_endpoint_rejects_two_skills():
    payload = {"workflow": _load_fixture("unsupported_two_skills.json")}
    response = client.post("/api/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["output"] is None
    assert body["nodeResults"] == []
    assert any(e["code"] == "unsupported_graph" for e in body["errors"])
    assert any("exactly one Skill" in e["message"] for e in body["errors"])


def test_runs_endpoint_rejects_selector_output():
    payload = {"workflow": _load_fixture("unsupported_selector_output.json")}
    response = client.post("/api/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert any(e["code"] == "unsupported_graph" for e in body["errors"])
    assert any("pass-through" in e["message"] for e in body["errors"])


def test_runs_endpoint_rejects_invalid_workflow():
    payload = {"workflow": _load_fixture("cycle.json")}
    response = client.post("/api/runs", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert any(e["code"] == "cycle" for e in body["errors"])


def test_runs_endpoint_rejects_malformed_body():
    response = client.post("/api/runs", json={"workflow": {"nodes": "nope"}})
    assert response.status_code == 422
