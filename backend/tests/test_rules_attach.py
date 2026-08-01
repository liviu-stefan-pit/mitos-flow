"""Phase 18 — Attach Rules to Skills (many-to-many, ordered, no duplication)."""

from __future__ import annotations

import json
from pathlib import Path

from mitos_api.domain import Workflow
from mitos_api.services.runners import FakeRunner, SkillExecutionRequest
from mitos_api.services.runners.base import Runner
from mitos_api.services.runs import execute_run
from mitos_api.services.scheduler import collect_attached_rules

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> Workflow:
    return Workflow.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


class RecordingRulesRunner:
    """Records full SkillExecutionRequest including attached rules."""

    def __init__(self) -> None:
        self.requests: list[SkillExecutionRequest] = []
        self._inner = FakeRunner()

    def execute(self, request: SkillExecutionRequest):
        self.requests.append(request)
        return self._inner.execute(request)

    def cleanup(self, skill_node_id: str) -> None:
        self._inner.cleanup(skill_node_id)


def test_collect_attached_rules_ordered_and_deduped():
    workflow = _load("many_rules_one_skill.json")
    skill = next(n for n in workflow.nodes if n.id == "skill-1")
    attached = collect_attached_rules(skill, workflow)

    # Ordered by rules node id: rules-a before rules-b (not edge insertion order).
    assert [r.rulesNodeId for r in attached] == ["rules-a", "rules-b"]
    assert [r.order for r in attached] == [0, 1]
    assert [r.content for r in attached] == [
        "Annotate public APIs.",
        "Keep replies concise.",
    ]
    # Duplicate edge e-res-a-dup must not duplicate rules-a.
    assert len(attached) == 2


def test_many_rules_one_skill_in_runner_and_trace():
    workflow = _load("many_rules_one_skill.json")
    recorder: Runner = RecordingRulesRunner()
    events: list[dict] = []

    def on_event(event_type, *, node_id=None, message=None, attached_rules=None, **_):
        events.append(
            {
                "type": event_type.value if hasattr(event_type, "value") else event_type,
                "nodeId": node_id,
                "message": message,
                "attachedRules": list(attached_rules or []),
            }
        )

    result = execute_run(workflow, runner=recorder, on_event=on_event)

    assert result.status == "completed"
    assert len(recorder.requests) == 1
    rules = recorder.requests[0].rules
    assert [r.rulesNodeId for r in rules] == ["rules-a", "rules-b"]
    assert [r.content for r in rules] == [
        "Annotate public APIs.",
        "Keep replies concise.",
    ]

    expected_output = (
        "fake::Draft::Hello from input"
        "::rules[rules-a=Annotate public APIs.|rules-b=Keep replies concise.]"
    )
    assert result.output == expected_output

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["rules-a"].state.value == "completed"
    assert by_id["rules-b"].state.value == "completed"
    assert by_id["rules-a"].output == "Annotate public APIs."
    assert by_id["skill-1"].attachedRules == rules
    assert by_id["skill-1"].output == expected_output

    skill_completed = [
        e
        for e in events
        if e["nodeId"] == "skill-1" and e["type"] == "completed"
    ]
    assert len(skill_completed) == 1
    assert skill_completed[0]["message"] is not None
    assert skill_completed[0]["message"].startswith(
        "Attached 2 rule(s): Types, Tone"
    )
    assert [r.rulesNodeId for r in skill_completed[0]["attachedRules"]] == [
        "rules-a",
        "rules-b",
    ]


def test_one_rule_many_skills_shared_without_duplication():
    workflow = _load("one_rule_many_skills.json")
    recorder: Runner = RecordingRulesRunner()
    result = execute_run(workflow, runner=recorder)

    assert result.status == "completed"
    assert len(recorder.requests) == 2

    for request in recorder.requests:
        assert len(request.rules) == 1
        assert request.rules[0].rulesNodeId == "rules-shared"
        assert request.rules[0].content == "Be concise and direct."

    # Rules node appears once in nodeResults (completed), not duplicated per skill.
    rules_results = [r for r in result.nodeResults if r.nodeId == "rules-shared"]
    assert len(rules_results) == 1
    assert rules_results[0].state.value == "completed"
    assert rules_results[0].output == "Be concise and direct."

    by_id = {r.nodeId: r for r in result.nodeResults}
    assert len(by_id["skill-1"].attachedRules) == 1
    assert len(by_id["skill-2"].attachedRules) == 1
    assert by_id["skill-1"].output == (
        "fake::Draft::Hello from input"
        "::rules[rules-shared=Be concise and direct.]"
    )
    assert by_id["skill-2"].output == (
        "fake::Polish::fake::Draft::Hello from input"
        "::rules[rules-shared=Be concise and direct.]"
        "::rules[rules-shared=Be concise and direct.]"
    )


def test_attached_empty_rules_still_complete_and_appear_on_skill():
    """valid_linear attaches Rules with empty content — still resolved (not skipped)."""
    workflow = _load("valid_linear.json")
    result = execute_run(workflow)

    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    # KB is attached but has empty content → completed with no keyword matches.
    assert by_id["kb-1"].state.value == "completed"
    assert by_id["rules-1"].state.value == "completed"
    assert by_id["skill-1"].attachedRules[0].rulesNodeId == "rules-1"
    assert by_id["skill-1"].knowledgeChunks == []
    assert by_id["skill-1"].output == (
        "fake::Draft::Hello from input::rules[rules-1=]"
    )


def test_unattached_rules_node_is_skipped():
    workflow = _load("simple_linear.json")
    # Graft an unattached Rules node onto the simple linear workflow.
    data = json.loads((FIXTURES / "simple_linear.json").read_text(encoding="utf-8"))
    data["nodes"].append(
        {
            "id": "rules-orphan",
            "kind": "rules",
            "label": "Orphan",
            "position": {"x": 0, "y": 200},
            "settings": {"description": "unused", "content": "Never attached"},
        }
    )
    workflow = Workflow.model_validate(data)
    result = execute_run(workflow)

    assert result.status == "completed"
    by_id = {r.nodeId: r for r in result.nodeResults}
    assert by_id["rules-orphan"].state.value == "skipped"
    assert by_id["skill-1"].attachedRules == []
    assert by_id["skill-1"].output == "fake::Draft::Hello from input"
