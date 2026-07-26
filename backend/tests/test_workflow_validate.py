"""Phase 9 — workflow schema validation fixtures and endpoint tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mitos_api.domain import Workflow, validate_workflow
from mitos_api.main import app

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_valid_linear_fixture_passes():
    payload = _load_fixture("valid_linear.json")
    workflow = Workflow.model_validate(payload)
    result = validate_workflow(workflow)

    assert result.valid is True
    assert result.errors == []
    assert result.workflow is not None

    # Settings preserved through parse + validate.
    nodes = {n.id: n for n in result.workflow.nodes}
    assert nodes["input-1"].settings.mediaType == "text/plain"
    assert nodes["input-1"].settings.content == "Hello from input"
    assert nodes["skill-1"].settings.description == "Draft the reply"
    assert nodes["skill-1"].settings.joinPolicy.value == "wait_for_all"
    assert nodes["kb-1"].settings.description == "KB for product facts"
    assert nodes["rules-1"].settings.description == "Keep replies concise"
    assert nodes["output-1"].settings.mode.value == "pass-through"


def test_cycle_fixture_rejected():
    workflow = Workflow.model_validate(_load_fixture("cycle.json"))
    result = validate_workflow(workflow)

    assert result.valid is False
    assert any(e.code == "cycle" for e in result.errors)


def test_dangling_edge_fixture_rejected():
    workflow = Workflow.model_validate(_load_fixture("dangling_edge.json"))
    result = validate_workflow(workflow)

    assert result.valid is False
    assert any(e.code == "dangling_edge" for e in result.errors)


def test_duplicate_ids_fixture_rejected():
    workflow = Workflow.model_validate(_load_fixture("duplicate_ids.json"))
    result = validate_workflow(workflow)

    assert result.valid is False
    codes = {e.code for e in result.errors}
    assert "duplicate_node_id" in codes
    assert "duplicate_edge_id" in codes


def test_invalid_edge_kind_fixture_rejected():
    workflow = Workflow.model_validate(_load_fixture("invalid_edge_kind.json"))
    result = validate_workflow(workflow)

    assert result.valid is False
    assert any(e.code == "invalid_edge_kind" for e in result.errors)


@pytest.mark.parametrize(
    "fixture_name,expect_valid",
    [
        ("valid_linear.json", True),
        ("cycle.json", False),
        ("dangling_edge.json", False),
        ("duplicate_ids.json", False),
        ("invalid_edge_kind.json", False),
    ],
)
def test_validate_endpoint_matches_fixtures(fixture_name: str, expect_valid: bool):
    payload = _load_fixture(fixture_name)
    response = client.post("/api/workflows/validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is expect_valid
    if expect_valid:
        assert body["workflow"] is not None
        assert body["errors"] == []
    else:
        assert body["workflow"] is None
        assert len(body["errors"]) > 0


def test_validate_endpoint_rejects_malformed_schema():
    response = client.post(
        "/api/workflows/validate",
        json={"metadata": {"schemaVersion": 1}, "nodes": "not-a-list", "edges": []},
    )
    assert response.status_code == 422
