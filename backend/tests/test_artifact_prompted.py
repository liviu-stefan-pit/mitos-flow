"""Phase 27 — Prompted Artifact Output projections."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mitos_api.domain.workflow import ArtifactOutputMode, Workflow
from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.runs import execute_run
from mitos_api.services.scheduler import plan_linear_chain

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_workflow(name: str) -> Workflow:
    return Workflow.model_validate(_load(name))


class EchoThenPromptRunner:
    """
    Echo Skill payloads unchanged; run FakeRunner for prompted projections.

    Lets the three-output gate fixture feed JSON to selectors while still
    exercising FakeRunner's prompted format for the second model call.
    """

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
        return None


# --- Domain / scheduler -------------------------------------------------------


def test_prompted_settings_require_prompt_template():
    with pytest.raises(ValidationError):
        _load_workflow("unsupported_prompted_output.json")


def test_plan_accepts_prompted_output():
    plan, errors = plan_linear_chain(_load_workflow("prompted_simple.json"))
    assert errors == []
    assert plan is not None
    assert plan.output_nodes[0].settings.mode is ArtifactOutputMode.PROMPTED


def test_plan_accepts_three_mode_fan_out():
    plan, errors = plan_linear_chain(_load_workflow("prompted_three_outputs.json"))
    assert errors == []
    assert plan is not None
    modes = {n.settings.mode for n in plan.output_nodes}
    assert modes == {
        ArtifactOutputMode.PASS_THROUGH,
        ArtifactOutputMode.SELECTOR,
        ArtifactOutputMode.PROMPTED,
    }


# --- FakeRunner prompted format -----------------------------------------------


def test_fake_runner_prompted_format_differs_from_passthrough():
    runner = FakeRunner()
    skill = runner.execute(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="Draft",
            inputPayload="Hello from input",
        )
    )
    prompted = runner.execute(
        SkillExecutionRequest(
            skillNodeId="output-1",
            skillLabel="Rewrite",
            inputPayload=skill.outputPayload,
            promptTemplate="Rewrite as a one-line headline",
        )
    )
    assert skill.outputPayload == "fake::Draft::Hello from input"
    assert prompted.outputPayload == (
        "fake::prompted::Rewrite::Rewrite as a one-line headline::"
        "fake::Draft::Hello from input"
    )
    assert prompted.outputPayload != skill.outputPayload


# --- Integration gate ---------------------------------------------------------


def test_execute_simple_prompted_differs_from_skill_payload():
    workflow = _load_workflow("prompted_simple.json")
    result = execute_run(workflow, runner=FakeRunner())

    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    skill_out = by_id["skill-1"].output
    prompted_out = by_id["output-1"].output
    assert skill_out == "fake::Draft::Hello from input"
    assert prompted_out == (
        "fake::prompted::Rewrite::Rewrite as a one-line headline::"
        "fake::Draft::Hello from input"
    )
    assert prompted_out != skill_out
    assert by_id["output-1"].promptTemplate == "Rewrite as a one-line headline"


def test_gate_three_outputs_two_model_calls():
    """
    Gate: One Skill → 3 outputs (pass-through, selector, prompted);
    trace shows 2 model calls (Skill + prompted).
    """
    workflow = _load_workflow("prompted_three_outputs.json")
    runner = EchoThenPromptRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    assert runner.calls == ["skill-1", "output-3"]  # exactly 2 model calls
    by_id = {r.nodeId: r for r in result.nodeResults}

    # Pass-through: full upstream JSON
    assert by_id["output-1"].state.value == "completed"
    assert "full body for prompt" in (by_id["output-1"].output or "")

    # Selector: no extra runner call
    assert by_id["output-2"].state.value == "completed"
    assert by_id["output-2"].output == "Extract me with JSONPath"

    # Prompted: second call, different artifact, template in trace
    assert by_id["output-3"].state.value == "completed"
    assert by_id["output-3"].promptTemplate == (
        "Summarize the upstream skill result as a short blurb"
    )
    assert (by_id["output-3"].output or "").startswith("fake::prompted::Summary::")
    assert by_id["output-3"].output != by_id["output-1"].output
