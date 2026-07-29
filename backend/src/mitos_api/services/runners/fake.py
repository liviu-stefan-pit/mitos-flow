"""Deterministic fake Skill runner (Phase 11+)."""

from __future__ import annotations

import time

from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult


class FakeRunner:
    """
    Predictable local runner with no external dependencies.

    Single-input output format (frozen for Phases 11–13):
      fake::{skillLabel}::{inputPayload}

    Multi-input output format (Phase 14+), ports sorted by name so arrival
    order cannot change the result:
      fake::{skillLabel}::{portA}={payloadA}|{portB}={payloadB}
    """

    def __init__(self, *, execute_delay_ms: int = 0) -> None:
        self.execute_delay_ms = execute_delay_ms
        self.cleaned_up: list[str] = []

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        if self.execute_delay_ms > 0:
            time.sleep(self.execute_delay_ms / 1000.0)

        if len(request.inputs) > 1:
            parts = "|".join(
                f"{envelope.port}={envelope.payload}"
                for envelope in sorted(request.inputs, key=lambda item: item.port)
            )
            output = f"fake::{request.skillLabel}::{parts}"
            media_type = next(
                (e.mediaType for e in sorted(request.inputs, key=lambda i: i.port)),
                request.inputMediaType or "text/plain",
            )
            return SkillExecutionResult(outputPayload=output, mediaType=media_type)

        if request.inputs:
            payload = request.inputs[0].payload
            media_type = request.inputs[0].mediaType or "text/plain"
        else:
            payload = request.inputPayload
            media_type = request.inputMediaType or "text/plain"

        output = f"fake::{request.skillLabel}::{payload}"
        return SkillExecutionResult(outputPayload=output, mediaType=media_type)

    def cleanup(self, skill_node_id: str) -> None:
        """Record cleanup for tests (Phase 16 cleanup hooks)."""
        self.cleaned_up.append(skill_node_id)
