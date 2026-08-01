"""Phase 11–16 — fake runner + POST /api/runs + live snapshot polling."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from mitos_api.domain import Workflow
from mitos_api.main import app
from mitos_api.services.run_store import run_store
from mitos_api.services.runners import FakeRunner, SkillExecutionRequest, SkillExecutionResult
from mitos_api.services.runners.base import Runner
from mitos_api.services.runs import execute_run

client = TestClient(app)


TERMINAL = {"completed", "failed", "cancelled", "rejected"}


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


FIXTURES = Path(__file__).parent / "fixtures"

EXPECTED_FAKE_OUTPUT = "fake::Draft::Hello from input"
EXPECTED_CHAIN_OUTPUT = "fake::Polish::fake::Draft::Hello from input"
EXPECTED_JOIN_OUTPUT = "fake::Draft::brief=Hello A|context=Hello B"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _results_by_id(body: dict) -> dict[str, dict]:
    return {r["nodeId"]: r for r in body["nodeResults"]}


class RecordingRunner:
    """Fake runner that records skill execution order."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._inner = FakeRunner()

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        self.calls.append(request.skillNodeId)
        return self._inner.execute(request)


class FailingOnSkillRunner:
    """Runs FakeRunner until a configured skill id, then raises."""

    def __init__(self, fail_on_skill_id: str) -> None:
        self.fail_on_skill_id = fail_on_skill_id
        self.calls: list[str] = []
        self._inner = FakeRunner()

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        self.calls.append(request.skillNodeId)
        if request.skillNodeId == self.fail_on_skill_id:
            raise RuntimeError(f"simulated failure on {request.skillNodeId}")
        return self._inner.execute(request)


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


def test_execute_valid_linear_resolves_attached_rules_and_kb():
    """Attached Rules resolve; attached empty KB completes with no chunks (Phase 19)."""
    workflow = Workflow.model_validate(_load_fixture("valid_linear.json"))
    result = execute_run(workflow)

    assert result.status == "completed"
    expected = "fake::Draft::Hello from input::rules[rules-1=]"
    assert result.output == expected

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["kb-1"].state.value == "completed"
    assert by_id["rules-1"].state.value == "completed"
    assert by_id["skill-1"].output == expected
    assert by_id["skill-1"].attachedRules[0].rulesNodeId == "rules-1"
    assert by_id["skill-1"].knowledgeChunks == []
    assert by_id["output-1"].output == expected


def test_execute_linear_chain_order_and_composed_output():
    """Input → Draft → Polish → Output runs skills in topo order."""
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    recorder: Runner = RecordingRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "completed"
    assert result.output == EXPECTED_CHAIN_OUTPUT
    assert result.mediaType == "text/plain"
    assert recorder.calls == ["skill-1", "skill-2"]

    # nodeResults order for the chain must follow execution order.
    chain_ids = [
        r.nodeId
        for r in result.nodeResults
        if r.nodeId in {"input-1", "skill-1", "skill-2", "output-1"}
    ]
    assert chain_ids == ["input-1", "skill-1", "skill-2", "output-1"]

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].output == EXPECTED_FAKE_OUTPUT
    assert by_id["skill-2"].output == EXPECTED_CHAIN_OUTPUT
    assert by_id["output-1"].output == EXPECTED_CHAIN_OUTPUT


def test_execute_linear_chain_failure_stops_downstream():
    """When an early skill fails, later skills and output are skipped."""
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    failing: Runner = FailingOnSkillRunner(fail_on_skill_id="skill-1")
    result = execute_run(workflow, runner=failing)

    assert result.status == "failed"
    assert result.output is None
    assert failing.calls == ["skill-1"]
    assert any(e.code == "runner_failed" for e in result.errors)

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["input-1"].state.value == "completed"
    assert by_id["skill-1"].state.value == "failed"
    assert by_id["skill-2"].state.value == "skipped"
    assert by_id["output-1"].state.value == "skipped"


def test_execute_linear_chain_mid_failure_skips_output_only():
    """Failure on the second skill still skips the Artifact Output."""
    workflow = Workflow.model_validate(_load_fixture("linear_chain.json"))
    failing: Runner = FailingOnSkillRunner(fail_on_skill_id="skill-2")
    result = execute_run(workflow, runner=failing)

    assert result.status == "failed"
    assert failing.calls == ["skill-1", "skill-2"]

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].output == EXPECTED_FAKE_OUTPUT
    assert by_id["skill-2"].state.value == "failed"
    assert by_id["output-1"].state.value == "skipped"


def test_execute_three_outputs_same_payload_no_extra_runner_calls():
    """One Skill → three passive outputs; all get the same payload; one runner call."""
    workflow = Workflow.model_validate(_load_fixture("three_outputs.json"))
    recorder: Runner = RecordingRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "completed"
    assert result.output == EXPECTED_FAKE_OUTPUT
    assert result.mediaType == "text/plain"
    assert recorder.calls == ["skill-1"]

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert set(by_id) == {
        "input-1",
        "skill-1",
        "output-1",
        "output-2",
        "output-3",
    }

    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].output == EXPECTED_FAKE_OUTPUT

    for output_id in ("output-1", "output-2", "output-3"):
        assert by_id[output_id].state.value == "completed"
        assert by_id[output_id].output == EXPECTED_FAKE_OUTPUT
        assert by_id[output_id].mediaType == "text/plain"
        # Immutable fan-out: same value as upstream Skill, not a mutated copy.
        assert by_id[output_id].output == by_id["skill-1"].output


def test_execute_three_outputs_failure_skips_all_outputs():
    """When the Skill fails, every branched Artifact Output is skipped."""
    workflow = Workflow.model_validate(_load_fixture("three_outputs.json"))
    failing: Runner = FailingOnSkillRunner(fail_on_skill_id="skill-1")
    result = execute_run(workflow, runner=failing)

    assert result.status == "failed"
    assert failing.calls == ["skill-1"]

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-1"].state.value == "failed"
    assert by_id["output-1"].state.value == "skipped"
    assert by_id["output-2"].state.value == "skipped"
    assert by_id["output-3"].state.value == "skipped"


def test_execute_chain_three_outputs_order_and_shared_payload():
    """Input → Draft → Polish → 3 outputs: topo order, shared payload, 2 runner calls."""
    workflow = Workflow.model_validate(_load_fixture("chain_three_outputs.json"))
    recorder: Runner = RecordingRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "completed"
    assert result.output == EXPECTED_CHAIN_OUTPUT
    assert recorder.calls == ["skill-1", "skill-2"]

    chain_ids = [
        r.nodeId
        for r in result.nodeResults
        if r.nodeId
        in {"input-1", "skill-1", "skill-2", "output-1", "output-2", "output-3"}
    ]
    assert chain_ids == [
        "input-1",
        "skill-1",
        "skill-2",
        "output-1",
        "output-2",
        "output-3",
    ]

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["skill-2"].output == EXPECTED_CHAIN_OUTPUT
    for output_id in ("output-1", "output-2", "output-3"):
        assert by_id[output_id].state.value == "completed"
        assert by_id[output_id].output == EXPECTED_CHAIN_OUTPUT
        assert by_id[output_id].output == by_id["skill-2"].output


def test_happy_path_runner_calls_equal_skill_count():
    """Invariant: completed happy-path runs call the runner once per Skill."""
    cases = [
        ("simple_linear.json", ["skill-1"]),
        ("linear_chain.json", ["skill-1", "skill-2"]),
        ("three_outputs.json", ["skill-1"]),
        ("chain_three_outputs.json", ["skill-1", "skill-2"]),
        ("valid_linear.json", ["skill-1"]),
        ("two_inputs_named.json", ["skill-1"]),
        ("two_inputs_named_reversed.json", ["skill-1"]),
    ]
    for fixture_name, expected_calls in cases:
        workflow = Workflow.model_validate(_load_fixture(fixture_name))
        recorder = RecordingRunner()
        result = execute_run(workflow, runner=recorder)
        assert result.status == "completed", fixture_name
        assert recorder.calls == expected_calls, fixture_name
        skill_count = sum(1 for n in workflow.nodes if n.kind.value == "skill")
        assert len(recorder.calls) == skill_count, fixture_name


def test_execute_two_named_inputs_wait_for_all():
    """Two Inputs → one Skill on named ports; both required before run."""
    workflow = Workflow.model_validate(_load_fixture("two_inputs_named.json"))
    recorder: Runner = RecordingRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "completed"
    assert result.output == EXPECTED_JOIN_OUTPUT
    assert result.mediaType == "text/plain"
    assert recorder.calls == ["skill-1"]

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["input-a"].state.value == "completed"
    assert by_id["input-a"].output == "Hello A"
    assert by_id["input-b"].state.value == "completed"
    assert by_id["input-b"].output == "Hello B"
    assert by_id["skill-1"].state.value == "completed"
    assert by_id["skill-1"].output == EXPECTED_JOIN_OUTPUT
    assert by_id["output-1"].output == EXPECTED_JOIN_OUTPUT


def test_execute_two_named_inputs_arrival_order_independent():
    """Reversing edge/port declaration order must not change Skill output."""
    forward = execute_run(
        Workflow.model_validate(_load_fixture("two_inputs_named.json"))
    )
    reversed_graph = execute_run(
        Workflow.model_validate(_load_fixture("two_inputs_named_reversed.json"))
    )

    assert forward.status == "completed"
    assert reversed_graph.status == "completed"
    assert forward.output == reversed_graph.output == EXPECTED_JOIN_OUTPUT


def test_execute_missing_input_blocks_skill():
    """wait_for_all with an unwired required port → blocked-node error."""
    workflow = Workflow.model_validate(_load_fixture("missing_input_port.json"))
    recorder: Runner = RecordingRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "failed"
    assert result.output is None
    assert recorder.calls == []
    assert any(e.code == "blocked" for e in result.errors)
    assert any("context" in e.message for e in result.errors)

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["input-a"].state.value == "completed"
    assert by_id["skill-1"].state.value == "blocked"
    assert by_id["output-1"].state.value == "skipped"


def test_runs_endpoint_simple_linear():
    run_store.clear()
    payload = {"workflow": _load_fixture("simple_linear.json")}
    body = _post_and_wait(payload)
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


def test_runs_endpoint_linear_chain():
    run_store.clear()
    payload = {"workflow": _load_fixture("linear_chain.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "completed"
    assert body["output"] == EXPECTED_CHAIN_OUTPUT

    by_id = _results_by_id(body)
    assert by_id["skill-1"]["output"] == EXPECTED_FAKE_OUTPUT
    assert by_id["skill-2"]["output"] == EXPECTED_CHAIN_OUTPUT
    assert by_id["output-1"]["output"] == EXPECTED_CHAIN_OUTPUT


def test_runs_endpoint_three_outputs():
    run_store.clear()
    payload = {"workflow": _load_fixture("three_outputs.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "completed"
    assert body["output"] == EXPECTED_FAKE_OUTPUT
    assert body["mediaType"] == "text/plain"
    assert body["errors"] == []

    by_id = _results_by_id(body)
    assert by_id["skill-1"]["output"] == EXPECTED_FAKE_OUTPUT
    assert by_id["output-1"]["output"] == EXPECTED_FAKE_OUTPUT
    assert by_id["output-2"]["output"] == EXPECTED_FAKE_OUTPUT
    assert by_id["output-3"]["output"] == EXPECTED_FAKE_OUTPUT


def test_runs_endpoint_two_named_inputs():
    run_store.clear()
    payload = {"workflow": _load_fixture("two_inputs_named.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "completed"
    assert body["output"] == EXPECTED_JOIN_OUTPUT
    assert body["errors"] == []

    by_id = _results_by_id(body)
    assert by_id["input-a"]["output"] == "Hello A"
    assert by_id["input-b"]["output"] == "Hello B"
    assert by_id["skill-1"]["output"] == EXPECTED_JOIN_OUTPUT
    assert by_id["output-1"]["output"] == EXPECTED_JOIN_OUTPUT


def test_runs_endpoint_missing_input_blocked():
    run_store.clear()
    payload = {"workflow": _load_fixture("missing_input_port.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "failed"
    assert body["output"] is None
    assert any(e["code"] == "blocked" for e in body["errors"])

    by_id = _results_by_id(body)
    assert by_id["skill-1"]["state"] == "blocked"
    assert by_id["output-1"]["state"] == "skipped"


def test_runs_endpoint_rejects_skill_to_skill_branch():
    run_store.clear()
    payload = {"workflow": _load_fixture("unsupported_branch.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "rejected"
    assert body["output"] is None
    assert body["nodeResults"] == []
    assert any(e["code"] == "unsupported_graph" for e in body["errors"])


def test_runs_endpoint_rejects_mixed_skill_and_output_branch():
    run_store.clear()
    payload = {"workflow": _load_fixture("unsupported_mixed_branch.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "rejected"
    assert any(e["code"] == "unsupported_graph" for e in body["errors"])


def test_runs_endpoint_rejects_empty_prompted_template_in_fan_out():
    """Empty promptTemplate fails request validation (422)."""
    run_store.clear()
    payload = {"workflow": _load_fixture("unsupported_mixed_output_modes.json")}
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 422


def test_runs_endpoint_rejects_same_port_join():
    run_store.clear()
    payload = {"workflow": _load_fixture("unsupported_join.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "rejected"
    assert any(e["code"] == "unsupported_graph" for e in body["errors"])
    assert any("port" in e["message"] for e in body["errors"])


def test_runs_endpoint_rejects_empty_prompt_template():
    run_store.clear()
    payload = {"workflow": _load_fixture("unsupported_prompted_output.json")}
    response = client.post("/api/runs", json=payload)
    assert response.status_code == 422


def test_runs_endpoint_runs_prompted_simple():
    run_store.clear()
    payload = {"workflow": _load_fixture("prompted_simple.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "completed"
    by_id = _results_by_id(body)
    assert by_id["output-1"]["state"] == "completed"
    assert by_id["output-1"]["output"].startswith("fake::prompted::Rewrite::")
    assert by_id["output-1"]["promptTemplate"] == "Rewrite as a one-line headline"


def test_runs_endpoint_rejects_invalid_workflow():
    run_store.clear()
    payload = {"workflow": _load_fixture("cycle.json")}
    body = _post_and_wait(payload)
    assert body["status"] == "rejected"
    assert any(e["code"] == "cycle" for e in body["errors"])


def test_runs_endpoint_rejects_malformed_body():
    response = client.post("/api/runs", json={"workflow": {"nodes": "nope"}})
    assert response.status_code == 422
