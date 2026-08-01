"""Phase 26 — Deterministic Artifact Output selectors."""

from __future__ import annotations

import json
from pathlib import Path

from mitos_api.domain.workflow import (
    SelectorKind,
    Workflow,
)
from mitos_api.services.artifacts.selectors import (
    SelectorError,
    SelectorMatch,
    SelectorMiss,
    apply_selector,
)
from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult
from mitos_api.services.runs import execute_run
from mitos_api.services.scheduler import plan_linear_chain

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_workflow(name: str) -> Workflow:
    return Workflow.model_validate(_load(name))


class EchoJsonRunner:
    """
    Test runner that returns the input payload unchanged.

    Lets selector fixtures feed real JSON/markdown without FakeRunner wrapping.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        self.calls.append(request.skillNodeId)
        if request.inputs:
            payload = request.inputs[0].payload
            media_type = request.inputs[0].mediaType or "text/plain"
        else:
            payload = request.inputPayload
            media_type = request.inputMediaType or "text/plain"
        return SkillExecutionResult(outputPayload=payload, mediaType=media_type)


# --- Unit: selector engine ----------------------------------------------------


def test_jsonpath_extracts_string_field():
    payload = json.dumps(
        {"output": {"headline": "Extract me with JSONPath", "n": 1}}
    )
    result = apply_selector(
        payload,
        kind=SelectorKind.JSON_PATH,
        expression="$.output.headline",
    )
    assert isinstance(result, SelectorMatch)
    assert result.payload == "Extract me with JSONPath"
    assert result.media_type == "text/plain"


def test_jsonpath_extracts_nested_object_as_json():
    payload = json.dumps({"output": {"metrics": {"skillsExecuted": 1}}})
    result = apply_selector(
        payload,
        kind=SelectorKind.JSON_PATH,
        expression="$.output.metrics",
    )
    assert isinstance(result, SelectorMatch)
    assert json.loads(result.payload) == {"skillsExecuted": 1}
    assert result.media_type == "application/json"


def test_jsonpath_array_index():
    payload = json.dumps({"artifacts": [{"name": "preview"}, {"name": "saved"}]})
    result = apply_selector(
        payload,
        kind=SelectorKind.JSON_PATH,
        expression="$.artifacts[1].name",
    )
    assert isinstance(result, SelectorMatch)
    assert result.payload == "saved"


def test_jsonpath_miss_returns_selector_miss():
    payload = json.dumps({"output": {"headline": "hi"}})
    result = apply_selector(
        payload,
        kind=SelectorKind.JSON_PATH,
        expression="$.output.missing",
    )
    assert isinstance(result, SelectorMiss)


def test_jsonpath_rejects_non_json_payload():
    try:
        apply_selector(
            "not-json",
            kind=SelectorKind.JSON_PATH,
            expression="$.a",
        )
        raise AssertionError("expected SelectorError")
    except SelectorError as exc:
        assert exc.code == "selector_not_json"


def test_jsonpath_rejects_invalid_expression():
    try:
        apply_selector(
            "{}",
            kind=SelectorKind.JSON_PATH,
            expression="output.headline",
        )
        raise AssertionError("expected SelectorError")
    except SelectorError as exc:
        assert exc.code == "selector_jsonpath_invalid"


def test_named_section_extracts_body():
    payload = "# Brief\n\n## Goal\nShip Phase 26.\n\n## Notes\nOther.\n"
    result = apply_selector(
        payload,
        kind=SelectorKind.NAMED_SECTION,
        expression="Goal",
    )
    assert isinstance(result, SelectorMatch)
    assert result.payload == "Ship Phase 26."
    assert result.media_type == "text/markdown"


def test_named_section_case_insensitive():
    payload = "## GOAL\nDone.\n"
    result = apply_selector(
        payload,
        kind=SelectorKind.NAMED_SECTION,
        expression="goal",
    )
    assert isinstance(result, SelectorMatch)
    assert result.payload == "Done."


def test_named_section_miss():
    payload = "## Goal\nShip it.\n"
    result = apply_selector(
        payload,
        kind=SelectorKind.NAMED_SECTION,
        expression="Missing",
    )
    assert isinstance(result, SelectorMiss)


# --- Scheduler: allow selectors + prompted ------------------------------------


def test_plan_accepts_selector_output():
    plan, errors = plan_linear_chain(_load_workflow("selector_jsonpath.json"))
    assert errors == []
    assert plan is not None
    assert plan.output_nodes[0].settings.mode.value == "selector"


def test_plan_accepts_mixed_pass_through_and_selector():
    plan, errors = plan_linear_chain(_load_workflow("selector_mixed_fanout.json"))
    assert errors == []
    assert plan is not None
    modes = {n.settings.mode.value for n in plan.output_nodes}
    assert modes == {"pass-through", "selector"}


def test_plan_accepts_prompted_in_mixed_fan_out():
    plan, errors = plan_linear_chain(
        _load_workflow("prompted_three_outputs.json")
    )
    assert errors == []
    assert plan is not None
    modes = {n.settings.mode.value for n in plan.output_nodes}
    assert modes == {"pass-through", "selector", "prompted"}


# --- Integration: execute with EchoJsonRunner ---------------------------------


def test_execute_jsonpath_selector_extracts_headline():
    workflow = _load_workflow("selector_jsonpath.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    assert runner.calls == ["skill-1"]
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].state.value == "completed"
    assert by_id["output-1"].output == "Extract me with JSONPath"


def test_execute_named_section_selector():
    workflow = _load_workflow("selector_named_section.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].output == "Ship Phase 26 selectors."


def test_selectors_cause_zero_extra_runner_calls_on_fanout():
    """Gate: selectors cause zero runner calls beyond the Skill count."""
    workflow = _load_workflow("selector_mixed_fanout.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    assert runner.calls == ["skill-1"]  # one Skill only — not per output
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].output is not None
    assert "headline" in (by_id["output-1"].output or "")
    assert by_id["output-2"].output == "Extract me with JSONPath"


def test_missing_policy_skip_fixture():
    workflow = _load_workflow("selector_miss_skip.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    assert runner.calls == ["skill-1"]
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].state.value == "skipped"


def test_missing_policy_empty_fixture():
    workflow = _load_workflow("selector_miss_empty.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].state.value == "completed"
    assert by_id["output-1"].output == ""


def test_missing_policy_warning_fixture():
    workflow = _load_workflow("selector_miss_warning.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].state.value == "completed"
    assert (by_id["output-1"].output or "").startswith("WARNING:")
    assert "$.output.missing" in (by_id["output-1"].output or "")


def test_missing_policy_fail_fixture():
    workflow = _load_workflow("selector_miss_fail.json")
    runner = EchoJsonRunner()
    result = execute_run(workflow, runner=runner)

    assert result.status == "failed"
    assert runner.calls == ["skill-1"]
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["output-1"].state.value == "failed"
    assert any(e.code == "selector_miss" for e in result.errors)
