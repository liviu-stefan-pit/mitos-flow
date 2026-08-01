"""Run request/response and live event models (Phases 11–16)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.cursor import CursorRunOptions, RunnerUsage
from mitos_api.domain.workflow import (
    AttachedRule,
    CitedChunk,
    ValidationIssue,
    Workflow,
)

RunnerKind = Literal["fake", "cursor"]


class NodeRunState(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class RunEventType(str, Enum):
    """SSE event types: queued → running → completed / failed / cancelled."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class RunEventScope(str, Enum):
    RUN = "run"
    NODE = "node"


RunStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "rejected",
    "cancelled",
]


class RunOptions(BaseModel):
    """Execution options for live / cancellable runs (fake or Cursor)."""

    model_config = ConfigDict(extra="forbid")

    delayMs: int = Field(default=0, ge=0, description="Per-node delay for live UI")
    nodeTimeoutMs: int | None = Field(
        default=None,
        ge=1,
        description="Per-Skill timeout; None means no timeout",
    )
    runner: RunnerKind = Field(
        default="fake",
        description=(
            "Default / whole-run Skill runner (Phase 23). "
            "Phase 24: Skills may override via settings.runner; "
            "options.runner='cursor' still forces Cursor for every Skill."
        ),
    )
    cursor: CursorRunOptions | None = Field(
        default=None,
        description=(
            "Cursor spawn options when any Skill uses the Cursor runner "
            "(options.runner='cursor' or skill.settings.runner='cursor')"
        ),
    )


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: Workflow
    options: RunOptions = Field(default_factory=RunOptions)


class NodeRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodeId: str
    state: NodeRunState
    output: str | None = None
    mediaType: str | None = None
    error: str | None = None
    attachedRules: list[AttachedRule] = Field(default_factory=list)
    knowledgeChunks: list[CitedChunk] = Field(default_factory=list)
    knowledgeQuery: str | None = None
    # Phase 23 — Cursor process capture (present when runner is Cursor)
    stdout: str | None = None
    stderr: str | None = None
    exitCode: int | None = None
    elapsedMs: int | None = None
    usage: RunnerUsage | None = None


class RunEvent(BaseModel):
    """One SSE / timeline event. ``id`` is the SSE id used for reconnect."""

    model_config = ConfigDict(extra="forbid")

    id: str
    seq: int
    type: RunEventType
    scope: RunEventScope
    runId: str
    nodeId: str | None = None
    message: str | None = None
    output: str | None = None
    mediaType: str | None = None
    error: str | None = None
    attachedRules: list[AttachedRule] = Field(default_factory=list)
    knowledgeChunks: list[CitedChunk] = Field(default_factory=list)
    knowledgeQuery: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exitCode: int | None = None
    elapsedMs: int | None = None
    usage: RunnerUsage | None = None
    timestamp: str


class RunResponse(BaseModel):
    """Run snapshot — may be in-flight (queued/running) or terminal."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: RunStatus
    nodeResults: list[NodeRunResult] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    output: str | None = None
    mediaType: str | None = None
    events: list[RunEvent] = Field(default_factory=list)


class CancelRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: RunStatus
    cancelRequested: bool
