"""Phase 16 — cancellation, per-node timeout, cleanup hooks, branch failure."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mitos_api.domain import RunOptions, Workflow
from mitos_api.main import app
from mitos_api.services.run_store import run_store
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult
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


class RecordingFakeRunner(FakeRunner):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        self.calls.append(request.skillNodeId)
        return super().execute(request)


def test_cancel_delayed_run_stops_before_downstream_skill():
    """Cancel mid-run: no downstream Skill starts (Phase 16 gate)."""
    run_store.clear()
    runner = RecordingFakeRunner()
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))

    started = threading.Event()
    events: list[str] = []

    def on_event(event_type, *, scope, node_id=None, **_kwargs):
        key = f"{scope.value}:{event_type.value}:{node_id}"
        events.append(key)
        if node_id == "skill-1" and event_type.value == "running":
            started.set()

    cancel_flag = {"value": False}

    def worker():
        execute_run(
            workflow,
            runner=runner,
            options=RunOptions(delayMs=80),
            on_event=on_event,
            is_cancelled=lambda: cancel_flag["value"],
        )

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    assert started.wait(timeout=2.0)
    cancel_flag["value"] = True
    thread.join(timeout=3.0)
    assert not thread.is_alive()

    # skill-1 may complete or be cancelled depending on timing after "running";
    # skill-2 must never execute.
    assert "skill-2" not in runner.calls
    assert any(e.startswith("run:cancelled") for e in events)
    assert not any(
        e == "node:running:skill-2" or e == "node:completed:skill-2" for e in events
    )


def test_cancel_endpoint_mid_run():
    run_store.clear()
    payload = {
        "workflow": _load_fixture("linear_chain.json"),
        "options": {"delayMs": 120},
    }
    created = client.post("/api/runs", json=payload)
    assert created.status_code == 200
    run_id = created.json()["id"]

    # Wait until first skill is running so cancel is mid-flight.
    deadline = time.monotonic() + 3
    saw_skill = False
    while time.monotonic() < deadline:
        snap = client.get(f"/api/runs/{run_id}").json()
        if any(
            e.get("nodeId") == "skill-1" and e.get("type") == "running"
            for e in snap.get("events", [])
        ):
            saw_skill = True
            break
        time.sleep(0.02)
    assert saw_skill

    cancelled = client.post(f"/api/runs/{run_id}/cancel")
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["id"] == run_id
    assert body["cancelRequested"] is True

    final = _wait_terminal(run_id)
    assert final["status"] == "cancelled"
    by_id = {r["nodeId"]: r for r in final["nodeResults"]}
    # Downstream skill must not have completed.
    assert by_id.get("skill-2", {}).get("state") in {
        "cancelled",
        "skipped",
        None,
    } or by_id.get("skill-2", {}).get("state") == "cancelled"
    if "skill-2" in by_id:
        assert by_id["skill-2"]["state"] != "completed"
    if "output-1" in by_id:
        assert by_id["output-1"]["state"] != "completed"


def test_per_node_timeout_fails_skill_and_skips_downstream():
    run_store.clear()
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    # Skill execute takes longer than the timeout.
    runner = FakeRunner(execute_delay_ms=200)
    result = execute_run(
        workflow,
        runner=runner,
        options=RunOptions(delayMs=0, nodeTimeoutMs=50),
    )
    assert result.status == "failed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "timeout"
    assert by_id["skill-2"].state.value == "skipped"
    assert by_id["output-1"].state.value == "skipped"
    assert any(e.code == "timeout" for e in result.errors)
    # Cleanup hook ran for the timed-out skill.
    assert "skill-1" in runner.cleaned_up


def test_cleanup_hook_runs_on_success_and_failure():
    workflow = Workflow.model_validate(_load_fixture("simple_linear.json"))
    runner = FakeRunner()
    result = execute_run(workflow, runner=runner)
    assert result.status == "completed"
    assert runner.cleaned_up == ["skill-1"]

    class Boom(FakeRunner):
        def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
            raise RuntimeError("boom")

    boom = Boom()
    failed = execute_run(workflow, runner=boom)
    assert failed.status == "failed"
    assert boom.cleaned_up == ["skill-1"]


def test_branch_failure_reports_each_skipped_output():
    """When upstream fails, each output branch is reported as skipped."""
    workflow = Workflow.model_validate(_load_fixture("three_outputs.json"))

    class Boom(FakeRunner):
        def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
            raise RuntimeError("branch-fail")

    result = execute_run(workflow, runner=Boom())
    assert result.status == "failed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "failed"
    for oid in ("output-1", "output-2", "output-3"):
        assert by_id[oid].state.value == "skipped"
        assert by_id[oid].error is not None
        assert "upstream" in (by_id[oid].error or "")


def test_cancel_unknown_run_404():
    run_store.clear()
    response = client.post("/api/runs/does-not-exist/cancel")
    assert response.status_code == 404
