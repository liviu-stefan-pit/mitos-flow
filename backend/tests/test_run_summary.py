"""Phase 28 — Tokens, cost, and run summary calculation tests."""

from __future__ import annotations

import json
from pathlib import Path

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.domain.run import NodeRunResult, NodeRunState
from mitos_api.domain.workflow import Workflow
from mitos_api.services.cost import (
    COST_DISCLAIMER,
    RATE_TABLE_VERSION,
    build_run_summary,
    estimate_call_cost_usd,
    get_rate,
    normalize_usage,
)
from mitos_api.services.runners.fake import FakeRunner
from mitos_api.services.runners.base import SkillExecutionRequest
from mitos_api.services.runs import execute_run

FIXTURES = Path(__file__).parent / "fixtures"


def _load_workflow(name: str) -> Workflow:
    return Workflow.model_validate(
        json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    )


# --- Normalization ------------------------------------------------------------


def test_normalize_usage_fills_total_from_input_and_output():
    usage = normalize_usage(
        RunnerUsage(inputTokens=10, outputTokens=5, totalTokens=None, source="stdout")
    )
    assert usage is not None
    assert usage.totalTokens == 15
    assert usage.inputTokens == 10
    assert usage.outputTokens == 5


def test_normalize_usage_returns_none_when_empty():
    assert normalize_usage(None) is None
    assert normalize_usage(RunnerUsage()) is None


def test_normalize_usage_preserves_total_only():
    usage = normalize_usage(RunnerUsage(totalTokens=42, source="stderr"))
    assert usage is not None
    assert usage.totalTokens == 42
    assert usage.inputTokens is None
    assert usage.outputTokens is None


# --- Rate table / cost estimation --------------------------------------------


def test_rate_table_has_composer_and_fake():
    composer = get_rate("composer-2.5")
    assert composer is not None
    assert composer.inputPerMillionUsd == 0.50
    assert composer.outputPerMillionUsd == 2.50
    fake = get_rate("fake")
    assert fake is not None
    assert fake.inputPerMillionUsd == 0.0
    assert get_rate("unknown-model-xyz") is None
    assert get_rate(None) is None


def test_estimate_call_cost_composer():
    usage = RunnerUsage(inputTokens=1_000_000, outputTokens=1_000_000)
    cost = estimate_call_cost_usd(usage, model="composer-2.5")
    assert cost == 0.50 + 2.50


def test_estimate_call_cost_unknown_when_pricing_missing():
    usage = RunnerUsage(inputTokens=100, outputTokens=50)
    assert estimate_call_cost_usd(usage, model="not-in-table") is None
    assert estimate_call_cost_usd(usage, model=None) is None


def test_estimate_call_cost_unknown_when_split_missing():
    usage = RunnerUsage(totalTokens=100)
    assert estimate_call_cost_usd(usage, model="composer-2.5") is None


# --- Run summary aggregation --------------------------------------------------


def test_build_run_summary_unknown_when_no_usage():
    summary = build_run_summary(
        [
            NodeRunResult(nodeId="input-1", state=NodeRunState.COMPLETED, output="hi"),
            NodeRunResult(nodeId="skill-1", state=NodeRunState.COMPLETED, output="out"),
        ]
    )
    assert summary.usageAvailable is False
    assert summary.pricingAvailable is False
    assert summary.inputTokens is None
    assert summary.outputTokens is None
    assert summary.totalTokens is None
    assert summary.estimatedCostUsd is None
    assert summary.costIsEstimate is True
    assert summary.disclaimer == COST_DISCLAIMER
    assert summary.rateTableVersion == RATE_TABLE_VERSION


def test_build_run_summary_aggregates_tokens_and_estimated_cost():
    results = [
        NodeRunResult(
            nodeId="skill-1",
            state=NodeRunState.COMPLETED,
            usage=RunnerUsage(
                inputTokens=1000,
                outputTokens=500,
                totalTokens=1500,
                source="stdout",
            ),
            model="composer-2.5",
        ),
        NodeRunResult(
            nodeId="output-prompted",
            state=NodeRunState.COMPLETED,
            usage=RunnerUsage(
                inputTokens=2000,
                outputTokens=1000,
                totalTokens=3000,
                source="stdout",
            ),
            model="composer-2.5",
        ),
    ]
    summary = build_run_summary(results)
    assert summary.usageAvailable is True
    assert summary.pricingAvailable is True
    assert summary.inputTokens == 3000
    assert summary.outputTokens == 1500
    assert summary.totalTokens == 4500
    assert summary.callCount == 2
    expected = (
        (1000 / 1_000_000) * 0.50
        + (500 / 1_000_000) * 2.50
        + (2000 / 1_000_000) * 0.50
        + (1000 / 1_000_000) * 2.50
    )
    assert summary.estimatedCostUsd == round(expected, 8)
    assert summary.costIsEstimate is True
    assert "not an exact charge" in summary.disclaimer.lower()


def test_build_run_summary_cost_unknown_for_unpriced_model_with_tokens():
    summary = build_run_summary(
        [
            NodeRunResult(
                nodeId="skill-1",
                state=NodeRunState.COMPLETED,
                usage=RunnerUsage(inputTokens=10, outputTokens=5, totalTokens=15),
                model="mystery-model",
            )
        ]
    )
    assert summary.usageAvailable is True
    assert summary.inputTokens == 10
    assert summary.outputTokens == 5
    assert summary.totalTokens == 15
    assert summary.estimatedCostUsd is None
    assert summary.pricingAvailable is False


def test_build_run_summary_fake_usage_priced_at_zero():
    summary = build_run_summary(
        [
            NodeRunResult(
                nodeId="skill-1",
                state=NodeRunState.COMPLETED,
                usage=RunnerUsage(
                    inputTokens=40,
                    outputTokens=20,
                    totalTokens=60,
                    source="fake",
                ),
            )
        ]
    )
    assert summary.usageAvailable is True
    assert summary.pricingAvailable is True
    assert summary.estimatedCostUsd == 0.0
    assert summary.calls[0].model == "fake"


# --- Integration: Fake run exposes summary ------------------------------------


def test_fake_runner_emits_synthetic_usage():
    result = FakeRunner().execute(
        SkillExecutionRequest(
            skillNodeId="skill-1",
            skillLabel="Draft",
            inputPayload="Hello from input",
        )
    )
    assert result.usage is not None
    assert result.usage.source == "fake"
    assert result.usage.inputTokens is not None
    assert result.usage.outputTokens is not None
    assert result.usage.totalTokens == (
        result.usage.inputTokens + result.usage.outputTokens
    )


def test_execute_run_summary_has_tokens_and_estimated_cost():
    workflow = _load_workflow("simple_linear.json")
    response = execute_run(workflow)
    assert response.status == "completed"
    assert response.summary is not None
    summary = response.summary
    assert summary.usageAvailable is True
    assert summary.inputTokens is not None and summary.inputTokens > 0
    assert summary.outputTokens is not None and summary.outputTokens > 0
    assert summary.totalTokens is not None and summary.totalTokens > 0
    assert summary.estimatedCostUsd is not None
    assert summary.costIsEstimate is True
    assert "estimate" in summary.disclaimer.lower() or "exact charge" in summary.disclaimer.lower()
    assert summary.rateTableVersion == RATE_TABLE_VERSION


def test_execute_run_prompted_counts_two_usage_calls():
    """Skill + prompted output → two FakeRunner calls with usage in the summary."""
    workflow = _load_workflow("prompted_simple.json")
    response = execute_run(workflow)
    assert response.status == "completed"
    assert response.summary is not None
    assert response.summary.callCount == 2
    assert response.summary.usageAvailable is True
    assert response.summary.estimatedCostUsd is not None
    assert response.summary.costIsEstimate is True
