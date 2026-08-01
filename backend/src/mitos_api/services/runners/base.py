"""Runner interface for Skill execution (Phase 11+)."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.cursor import RunnerUsage
from mitos_api.domain.workflow import AttachedRule, CitedChunk, InputEnvelope


class SkillExecutionRequest(BaseModel):
    """Request dispatched to a Skill runner."""

    model_config = ConfigDict(extra="forbid")

    skillNodeId: str = Field(min_length=1)
    skillLabel: str
    description: str = ""
    # Phase 28.5: SKILL.md body applied from the managed library.
    content: str = ""
    inputPayload: str = ""
    inputMediaType: str = "text/plain"
    inputs: list[InputEnvelope] = Field(default_factory=list)
    rules: list[AttachedRule] = Field(default_factory=list)
    knowledgeChunks: list[CitedChunk] = Field(default_factory=list)
    # Phase 24.5: resolved Cursor model for this Skill (None for Fake).
    model: str | None = None
    # Phase 27: when set, this request is a prompted Artifact Output projection
    # (explicit second model call), not a Skill step.
    promptTemplate: str | None = None


class SkillExecutionResult(BaseModel):
    """Result from a Skill runner (fake or Cursor)."""

    model_config = ConfigDict(extra="forbid")

    outputPayload: str
    mediaType: str = "text/plain"
    # Phase 23 — optional process capture (Cursor runner)
    stdout: str | None = None
    stderr: str | None = None
    exitCode: int | None = None
    elapsedMs: int | None = None
    usage: RunnerUsage | None = None
    # Phase 24.5 — model actually used for this Cursor spawn
    model: str | None = None


class Runner(Protocol):
    """Executable backend for a Skill node."""

    def execute(self, request: SkillExecutionRequest) -> SkillExecutionResult:
        """Run the skill and return its output payload."""
        ...

    def cleanup(self, skill_node_id: str) -> None:
        """Release resources after a Skill finishes, fails, times out, or is cancelled."""
        ...
