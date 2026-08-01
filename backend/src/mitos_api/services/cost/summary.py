"""Normalize runner usage and build run-level token/cost summaries (Phase 28)."""

from __future__ import annotations

from collections.abc import Sequence

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.domain.run import NodeRunResult, RunSummary, UsageCallSummary
from mitos_api.services.cost.rates import RATE_TABLE_VERSION, get_rate

COST_DISCLAIMER = (
    "Estimated cost from a local rate table — not an exact charge."
)


def normalize_usage(usage: RunnerUsage | None) -> RunnerUsage | None:
    """
    Normalize runner usage into a consistent shape.

    - Fills ``totalTokens`` when both input and output are present.
    - Never invents token counts when none are available.
    - Returns None when usage is missing or empty.
    """
    if usage is None:
        return None
    input_tokens = usage.inputTokens
    output_tokens = usage.outputTokens
    total_tokens = usage.totalTokens
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    if (
        total_tokens is None
        and input_tokens is not None
        and output_tokens is not None
    ):
        total_tokens = input_tokens + output_tokens
    return RunnerUsage(
        inputTokens=input_tokens,
        outputTokens=output_tokens,
        totalTokens=total_tokens,
        source=usage.source,
    )


def estimate_call_cost_usd(
    usage: RunnerUsage,
    *,
    model: str | None,
) -> float | None:
    """
    Estimate USD cost for one call.

    Returns None when pricing is unavailable or input/output split is missing
    (total-only usage cannot be priced from split rates).
    """
    rate = get_rate(model)
    if rate is None:
        return None
    if usage.inputTokens is None or usage.outputTokens is None:
        return None
    return (
        (usage.inputTokens / 1_000_000.0) * rate.inputPerMillionUsd
        + (usage.outputTokens / 1_000_000.0) * rate.outputPerMillionUsd
    )


def _rate_model_for_node(result: NodeRunResult) -> str | None:
    """Resolve which rate-table key to use for a node result."""
    if result.model:
        return result.model
    if result.usage is not None and (result.usage.source or "").lower() == "fake":
        return "fake"
    return None


def build_run_summary(node_results: Sequence[NodeRunResult]) -> RunSummary:
    """
    Aggregate normalized usage from completed model-call nodes into a summary.

    Token fields and ``estimatedCostUsd`` are None when unavailable — UI must
    render those as \"unknown\". When a cost figure is present it is always an
    estimate (see ``disclaimer`` / ``costIsEstimate``).
    """
    calls: list[UsageCallSummary] = []
    sum_in = 0
    sum_out = 0
    sum_total = 0
    any_in = False
    any_out = False
    any_total = False
    sum_cost = 0.0
    any_cost = False
    all_priced = True

    for result in node_results:
        usage = normalize_usage(result.usage)
        if usage is None:
            continue
        rate_model = _rate_model_for_node(result)
        call_cost = estimate_call_cost_usd(usage, model=rate_model)
        if call_cost is None:
            all_priced = False
        else:
            sum_cost += call_cost
            any_cost = True

        if usage.inputTokens is not None:
            sum_in += usage.inputTokens
            any_in = True
        else:
            all_priced = False
        if usage.outputTokens is not None:
            sum_out += usage.outputTokens
            any_out = True
        else:
            all_priced = False
        if usage.totalTokens is not None:
            sum_total += usage.totalTokens
            any_total = True
        elif usage.inputTokens is not None and usage.outputTokens is not None:
            sum_total += usage.inputTokens + usage.outputTokens
            any_total = True

        calls.append(
            UsageCallSummary(
                nodeId=result.nodeId,
                model=rate_model or result.model,
                inputTokens=usage.inputTokens,
                outputTokens=usage.outputTokens,
                totalTokens=usage.totalTokens,
                estimatedCostUsd=call_cost,
                source=usage.source,
            )
        )

    if not calls:
        return RunSummary(
            inputTokens=None,
            outputTokens=None,
            totalTokens=None,
            estimatedCostUsd=None,
            costIsEstimate=True,
            rateTableVersion=RATE_TABLE_VERSION,
            disclaimer=COST_DISCLAIMER,
            usageAvailable=False,
            pricingAvailable=False,
            callCount=0,
            calls=[],
        )

    estimated: float | None
    pricing_available: bool
    if any_cost and all_priced:
        estimated = round(sum_cost, 8)
        pricing_available = True
    elif any_cost:
        # Partial pricing — still surface a partial estimate, never as exact.
        estimated = round(sum_cost, 8)
        pricing_available = True
    else:
        estimated = None
        pricing_available = False

    return RunSummary(
        inputTokens=sum_in if any_in else None,
        outputTokens=sum_out if any_out else None,
        totalTokens=sum_total if any_total else None,
        estimatedCostUsd=estimated,
        costIsEstimate=True,
        rateTableVersion=RATE_TABLE_VERSION,
        disclaimer=COST_DISCLAIMER,
        usageAvailable=True,
        pricingAvailable=pricing_available,
        callCount=len(calls),
        calls=calls,
    )
