"""Run request/response and live event models (Phases 11–16)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.workflow import (
    AttachedRule,
    CitedChunk,
    ValidationIssue,
    Workflow,
)


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
    """Execution options for live / cancellable fake runs."""

    model_config = ConfigDict(extra="forbid")

    delayMs: int = Field(default=0, ge=0, description="Per-node delay for live UI")
    nodeTimeoutMs: int | None = Field(
        default=None,
        ge=1,
        description="Per-Skill timeout; None means no timeout",
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
