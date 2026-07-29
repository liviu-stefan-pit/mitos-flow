"""Phase 15 — live SSE run events, delayed node-by-node progress, reconnect."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mitos_api.domain import RunOptions, Workflow
from mitos_api.domain.run import RunEventScope, RunEventType
from mitos_api.main import app
from mitos_api.services.run_store import run_store
from mitos_api.services.runs import execute_run, start_run

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _wait_terminal(run_id: str, *, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in {"completed", "failed", "cancelled", "rejected"}:
            return last
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for run {run_id}: {last}")


def _parse_sse(raw: str) -> list[dict]:
    events: list[dict] = []
    blocks = raw.strip().split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        event_id = None
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("id: "):
                event_id = line[4:]
            elif line.startswith("event: "):
                event_name = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if data is not None:
            data["_sse_id"] = event_id
            data["_sse_event"] = event_name
            events.append(data)
    return events


def test_delayed_run_emits_node_by_node_events():
    run_store.clear()
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    events: list[tuple[str, str | None]] = []

    def on_event(event_type, *, scope, node_id=None, **_kwargs):
        events.append((f"{scope.value}:{event_type.value}", node_id))

    result = execute_run(
        workflow,
        options=RunOptions(delayMs=20),
        on_event=on_event,
    )
    assert result.status == "completed"

    # Run lifecycle
    assert events[0] == ("run:queued", None)
    assert events[1] == ("run:running", None)
    assert events[-1] == ("run:completed", None)

    # Nodes advance in order: input → skill-1 → skill-2 → output
    node_completed = [
        node_id
        for kind, node_id in events
        if kind == "node:completed"
    ]
    assert node_completed == ["input-1", "skill-1", "skill-2", "output-1"]

    # Each node has queued → running → completed
    for node_id in ("input-1", "skill-1", "skill-2", "output-1"):
        seq = [kind for kind, nid in events if nid == node_id]
        assert seq == ["node:queued", "node:running", "node:completed"]


def test_sse_stream_replays_events_and_completes():
    run_store.clear()
    payload = {
        "workflow": _load_fixture("simple_linear.json"),
        "options": {"delayMs": 30},
    }
    created = client.post("/api/runs", json=payload)
    assert created.status_code == 200
    run_id = created.json()["id"]
    assert created.json()["status"] == "queued"

    with client.stream("GET", f"/api/runs/{run_id}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        raw = "".join(response.iter_text())

    parsed = _parse_sse(raw)
    assert parsed
    assert parsed[0]["scope"] == "run"
    assert parsed[0]["type"] == "queued"
    terminal = [e for e in parsed if e["scope"] == "run" and e["type"] == "completed"]
    assert len(terminal) == 1

    node_types = [
        (e["nodeId"], e["type"])
        for e in parsed
        if e["scope"] == "node"
    ]
    assert ("input-1", "completed") in node_types
    assert ("skill-1", "completed") in node_types
    assert ("output-1", "completed") in node_types

    final = _wait_terminal(run_id)
    assert final["status"] == "completed"
    assert final["output"] == "fake::Draft::Hello from input"


def test_reconnect_does_not_duplicate_terminal_events():
    run_store.clear()
    payload = {
        "workflow": _load_fixture("simple_linear.json"),
        "options": {"delayMs": 15},
    }
    created = client.post("/api/runs", json=payload)
    run_id = created.json()["id"]
    final = _wait_terminal(run_id)
    assert final["status"] == "completed"

    events = final["events"]
    terminal_events = [
        e
        for e in events
        if e["scope"] == "run"
        and e["type"] in {"completed", "failed", "cancelled"}
    ]
    assert len(terminal_events) == 1
    last_id = events[-1]["id"]

    # Reconnect with Last-Event-ID at the end → no further events (esp. no
    # duplicate terminal).
    with client.stream(
        "GET",
        f"/api/runs/{run_id}/events",
        headers={"Last-Event-ID": last_id},
    ) as response:
        assert response.status_code == 200
        raw = "".join(response.iter_text())

    assert raw.strip() == ""

    # Reconnect from before the terminal event → terminal appears once only.
    before_terminal = events[-2]["id"]
    with client.stream(
        "GET",
        f"/api/runs/{run_id}/events",
        headers={"Last-Event-ID": before_terminal},
    ) as response:
        raw = "".join(response.iter_text())
    parsed = _parse_sse(raw)
    terminals = [
        e for e in parsed if e["scope"] == "run" and e["type"] == "completed"
    ]
    assert len(terminals) == 1

    # Producer-side guard: appending another terminal is a no-op duplicate.
    again = run_store.append_event(
        run_id,
        event_type=RunEventType.COMPLETED,
        scope=RunEventScope.RUN,
        message="should not duplicate",
    )
    assert again is not None
    assert again.id == terminal_events[0]["id"]
    snap = client.get(f"/api/runs/{run_id}").json()
    terminals_after = [
        e
        for e in snap["events"]
        if e["scope"] == "run" and e["type"] == "completed"
    ]
    assert len(terminals_after) == 1


def test_start_run_returns_queued_immediately():
    run_store.clear()
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    response = start_run(workflow, options=RunOptions(delayMs=200))
    assert response.status == "queued"
    assert response.nodeResults == []
    # Allow background work to finish so it does not leak into other tests.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snap = run_store.get(response.id)
        assert snap is not None
        if snap.terminal:
            break
        time.sleep(0.02)
