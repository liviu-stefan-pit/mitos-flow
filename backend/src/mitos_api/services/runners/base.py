"""Runner interface for Skill execution (Phase 11)."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class SkillExecutionRequest(BaseModel):
    """Request dispatched to a Skill runner."""

    model_config = ConfigDict(extra="forbid")

    skillNodeId: str = Field(min_length=1)
    skillLabel: str
    description: str = ""
    inputPayload: str
    inputMediaType: str = "text/plain"


class SkillExecutionResult(BaseModel):
    """Deterministic result from a Skill runner."""

    model_config = ConfigDict(extra="forbid")

    outputPayload: str
    mediaType: str = "text/plain"


class Runner(Protocol):
    """Executable backend for a Skill node."""

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """Run the skill and return its output payload."""
        ...
