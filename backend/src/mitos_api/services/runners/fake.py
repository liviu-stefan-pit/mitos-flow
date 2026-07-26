"""Deterministic fake Skill runner (Phase 11)."""

from __future__ import annotations

from mitos_api.services.runners.base import SkillExecutionRequest, SkillExecutionResult


class FakeRunner:
    """
    Predictable local runner with no external dependencies.

    Output format (frozen for tests):
      fake::{skillLabel}::{inputPayload}
    """

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        output = f"fake::{request.skillLabel}::{request.inputPayload}"
        return SkillExecutionResult(
            outputPayload=output,
            mediaType=request.inputMediaType or "text/plain",
        )
