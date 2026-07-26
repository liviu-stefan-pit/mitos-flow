"""Run request/response models — Phase 11 synchronous execution."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.workflow import ValidationIssue, Workflow


class NodeRunState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow: Workflow


class NodeRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodeId: str
    state: NodeRunState
    output: str | None = None
    mediaType: str | None = None
    error: str | None = None


class RunResponse(BaseModel):
    """Synchronous run result (Phase 11 — no SSE yet)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: Literal["completed", "failed", "rejected"]
    nodeResults: list[NodeRunResult] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
    output: str | None = None
    mediaType: str | None = None
