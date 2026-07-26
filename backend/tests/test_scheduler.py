"""Phase 12–14 — DAG scheduler unit tests (chains, fan-out, named-input joins)."""

from __future__ import annotations

import json
from pathlib import Path

from mitos_api.domain import InputEnvelope, Workflow
from mitos_api.services.runners import FakeRunner, SkillExecutionRequest
from mitos_api.services.scheduler import collect_input_envelopes, plan_linear_chain

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Workflow:
    return Workflow.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


def test_plan_simple_linear_order():
    plan, errors = plan_linear_chain(_load("simple_linear.json"))
    assert errors == []
    assert plan is not None
    assert [n.id for n in plan.input_nodes] == ["input-1"]
    assert plan.input_node.id == "input-1"
    assert [s.id for s in plan.skill_nodes] == ["skill-1"]
    assert [o.id for o in plan.output_nodes] == ["output-1"]
    assert plan.output_node.id == "output-1"


def test_plan_linear_chain_skill_order():
    plan, errors = plan_linear_chain(_load("linear_chain.json"))
    assert errors == []
    assert plan is not None
    assert [s.id for s in plan.skill_nodes] == ["skill-1", "skill-2"]
    assert [s.label for s in plan.skill_nodes] == ["Draft", "Polish"]
    assert [o.id for o in plan.output_nodes] == ["output-1"]


def test_plan_three_outputs_fan_out():
    """Terminal Skill may fan out to multiple pass-through Artifact Outputs."""
    plan, errors = plan_linear_chain(_load("three_outputs.json"))
    assert errors == []
    assert plan is not None
    assert [s.id for s in plan.skill_nodes] == ["skill-1"]
    assert [o.id for o in plan.output_nodes] == [
        "output-1",
        "output-2",
        "output-3",
    ]


def test_plan_chain_three_outputs_order():
    """Linear Skill chain may end in passive output fan-out."""
    plan, errors = plan_linear_chain(_load("chain_three_outputs.json"))
    assert errors == []
    assert plan is not None
    assert [s.id for s in plan.skill_nodes] == ["skill-1", "skill-2"]
    assert [o.id for o in plan.output_nodes] == [
        "output-1",
        "output-2",
        "output-3",
    ]


def test_plan_rejects_skill_to_skill_branch():
    plan, errors = plan_linear_chain(_load("unsupported_branch.json"))
    assert plan is None
    assert any(e.code == "unsupported_graph" for e in errors)
    assert any(
        "Skill→Skill branching" in e.message or "branching" in e.message
        for e in errors
    )


def test_plan_rejects_mixed_skill_and_output_branch():
    """A Skill may not fan out to both another Skill and an Artifact Output."""
    plan, errors = plan_linear_chain(_load("unsupported_mixed_branch.json"))
    assert plan is None
    assert any(e.code == "unsupported_graph" for e in errors)
    assert any(
        "Skill→Skill branching" in e.message or "branching" in e.message
        for e in errors
    )


def test_plan_rejects_same_port_join():
    """Two edges into the same Skill port are still unsupported."""
    plan, errors = plan_linear_chain(_load("unsupported_join.json"))
    assert plan is None
    assert any(e.code == "unsupported_graph" for e in errors)
    assert any(
        "at most one data-flow" in e.message or "port" in e.message for e in errors
    )


def test_plan_two_named_inputs_join():
    plan, errors = plan_linear_chain(_load("two_inputs_named.json"))
    assert errors == []
    assert plan is not None
    assert [n.id for n in plan.input_nodes] == ["input-a", "input-b"]
    assert [s.id for s in plan.skill_nodes] == ["skill-1"]
    assert [o.id for o in plan.output_nodes] == ["output-1"]


def test_plan_missing_input_port_still_plans():
    """Incomplete wiring is accepted at plan time; wait_for_all blocks at run."""
    plan, errors = plan_linear_chain(_load("missing_input_port.json"))
    assert errors == []
    assert plan is not None
    assert [n.id for n in plan.input_nodes] == ["input-a"]


def test_collect_envelopes_arrival_order_does_not_alter_runner_input():
    """Swapping arrival order changes envelope.order only, not FakeRunner output."""
    workflow = _load("two_inputs_named.json")
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    completed = {
        "input-a": ("Hello A", "text/plain"),
        "input-b": ("Hello B", "text/plain"),
    }

    envelopes_ab, err_ab = collect_input_envelopes(
        skill, workflow, completed, {"input-a": 0, "input-b": 1}
    )
    envelopes_ba, err_ba = collect_input_envelopes(
        skill, workflow, completed, {"input-a": 1, "input-b": 0}
    )
    assert err_ab is None and err_ba is None
    assert envelopes_ab is not None and envelopes_ba is not None

    # Port/payload identity is stable; only order (arrival) differs.
    assert [(e.port, e.payload, e.sourceNodeId) for e in envelopes_ab] == [
        (e.port, e.payload, e.sourceNodeId) for e in envelopes_ba
    ]
    assert [e.port for e in envelopes_ab] == ["brief", "context"]
    assert {e.port: e.order for e in envelopes_ab} == {"brief": 0, "context": 1}
    assert {e.port: e.order for e in envelopes_ba} == {"brief": 1, "context": 0}

    runner = FakeRunner()
    out_ab = runner.execute(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="Draft",
            inputs=envelopes_ab,
            inputPayload=envelopes_ab[0].payload,
        )
    )
    out_ba = runner.execute(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="Draft",
            inputs=envelopes_ba,
            inputPayload=envelopes_ba[0].payload,
        )
    )
    assert out_ab.outputPayload == out_ba.outputPayload
    assert out_ab.outputPayload == "fake::Draft::brief=Hello A|context=Hello B"


def test_collect_envelopes_missing_port_blocks():
    workflow = _load("missing_input_port.json")
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    envelopes, err = collect_input_envelopes(
        skill,
        workflow,
        {"input-a": ("Hello A", "text/plain")},
        {"input-a": 0},
    )
    assert envelopes is None
    assert err is not None
    assert err.code == "blocked"
    assert "context" in err.message
    assert err.nodeId == "skill-1"


def test_plan_rejects_selector_output():
    plan, errors = plan_linear_chain(_load("unsupported_selector_output.json"))
    assert plan is None
    assert any("pass-through" in e.message for e in errors)


def test_plan_rejects_mixed_output_modes_in_fan_out():
    """One non-pass-through among multiple outputs rejects the whole plan."""
    plan, errors = plan_linear_chain(_load("unsupported_mixed_output_modes.json"))
    assert plan is None
    assert any(e.code == "unsupported_graph" for e in errors)
    assert any("pass-through" in e.message for e in errors)
    assert any(e.nodeId == "output-2" for e in errors)


def test_input_envelope_model_round_trip():
    envelope = InputEnvelope(
        port="brief",
        payload="Hello",
        mediaType="text/plain",
        sourceNodeId="input-a",
        order=1,
    )
    assert envelope.model_dump(mode="json") == {
        "port": "brief",
        "payload": "Hello",
        "mediaType": "text/plain",
        "sourceNodeId": "input-a",
        "order": 1,
    }
