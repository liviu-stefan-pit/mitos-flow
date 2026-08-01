"""Deterministic fake Skill runner (Phase 11+)."""

from __future__ import annotations

import time

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.domain.workflow import AttachedRule, CitedChunk
from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult


def _format_rules_suffix(rules: list[AttachedRule]) -> str:
    """Append ordered attached rules so they are visible in fake output / trace."""
    if not rules:
        return ""
    parts = "|".join(f"{rule.rulesNodeId}={rule.content}" for rule in rules)
    return f"::rules[{parts}]"


def _format_kb_suffix(chunks: list[CitedChunk]) -> str:
    """Append ordered cited KB chunks so retrieval is visible in fake output / trace."""
    if not chunks:
        return ""
    parts = "|".join(
        f"{chunk.chunkId}:{chunk.citation}={chunk.text}" for chunk in chunks
    )
    return f"::kb[{parts}]"


def _synthetic_usage(input_text: str, output_text: str) -> RunnerUsage:
    """
    Deterministic fake token counts (Phase 28).

    Rough char/4 heuristic so local Fake runs still exercise the run summary UI.
    Marked ``source="fake"`` — never treated as real Cursor metering.
    """
    input_tokens = max(1, len(input_text) // 4)
    output_tokens = max(1, len(output_text) // 4)
    return RunnerUsage(
        inputTokens=input_tokens,
        outputTokens=output_tokens,
        totalTokens=input_tokens + output_tokens,
        source="fake",
    )


class FakeRunner:
    """
    Predictable local runner with no external dependencies.

    Single-input output format (frozen for Phases 11–13):
      fake::{skillLabel}::{inputPayload}

    Multi-input output format (Phase 14+), ports sorted by name so arrival
    order cannot change the result:
      fake::{skillLabel}::{portA}={payloadA}|{portB}={payloadB}

    Attached Rules (Phase 18+) append a deterministic suffix:
      …::rules[{rulesNodeId}={content}|…]

    Retrieved KB chunks (Phase 19+) append after rules:
      …::kb[{chunkId}:{citation}={text}|…]

    Prompted Artifact Output projections (Phase 27) use:
      fake::prompted::{label}::{promptTemplate}::{inputPayload}
    so the artifact always differs from a pass-through of the same Skill data.

    Phase 28: every successful execute includes synthetic ``usage`` (source=fake).
    """

    def __init__(self, *, execute_delay_ms: int = 0) -> None:
        self.execute_delay_ms = execute_delay_ms
        self.cleaned_up: list[str] = []
        self.last_request: SkillExecutionRequest | None = None

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        self.last_request = request
        if self.execute_delay_ms > 0:
            time.sleep(self.execute_delay_ms / 1000.0)

        if request.inputs:
            payload = request.inputs[0].payload
            media_type = request.inputs[0].mediaType or "text/plain"
        else:
            payload = request.inputPayload
            media_type = request.inputMediaType or "text/plain"

        prompt_template = (request.promptTemplate or "").strip()
        if prompt_template:
            # Phase 27: explicit second execution for prompted projection.
            output = (
                f"fake::prompted::{request.skillLabel}::"
                f"{prompt_template}::{payload}"
            )
            return SkillExecutionResult(
                outputPayload=output,
                mediaType=media_type,
                usage=_synthetic_usage(payload, output),
            )

        rules_suffix = _format_rules_suffix(request.rules)
        kb_suffix = _format_kb_suffix(request.knowledgeChunks)
        suffix = f"{rules_suffix}{kb_suffix}"

        if len(request.inputs) > 1:
            parts = "|".join(
                f"{envelope.port}={envelope.payload}"
                for envelope in sorted(request.inputs, key=lambda item: item.port)
            )
            output = f"fake::{request.skillLabel}::{parts}{suffix}"
            media_type = next(
                (e.mediaType for e in sorted(request.inputs, key=lambda i: i.port)),
                request.inputMediaType or "text/plain",
            )
            return SkillExecutionResult(
                outputPayload=output,
                mediaType=media_type,
                usage=_synthetic_usage(parts, output),
            )

        output = f"fake::{request.skillLabel}::{payload}{suffix}"
        return SkillExecutionResult(
            outputPayload=output,
            mediaType=media_type,
            usage=_synthetic_usage(payload, output),
        )

    def cleanup(self, skill_node_id: str) -> None:
        """Record cleanup for tests (Phase 16 cleanup hooks)."""
        self.cleaned_up.append(skill_node_id)
