"""Cursor CLI capability probe, dry-run, execute, and models (Phases 21–24.5)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.workflow import (
    AttachedRule,
    CitedChunk,
    DEFAULT_CURSOR_SKILL_MODEL,
    InputEnvelope,
)

DEFAULT_CURSOR_TIMEOUT_MS = 120_000


class CursorCapabilityStatus(str, Enum):
    """High-level probe result for Settings / later adapters."""

    ABSENT = "absent"
    AVAILABLE = "available"
    UNSUPPORTED_VERSION = "unsupported_version"
    ERROR = "error"


class CursorModelsStatus(str, Enum):
    """Result of ``agent --list-models`` (Phase 24.5)."""

    AVAILABLE = "available"
    ABSENT = "absent"
    ERROR = "error"


class CursorFeatureFlags(BaseModel):
    """
    Features discovered from ``--help`` output only.

    Do not assume flags exist without seeing them in help text
    (Phase 21: no concept-doc assumptions).
    """

    model_config = ConfigDict(extra="forbid")

    printMode: bool = False
    outputFormat: bool = False
    workspace: bool = False
    force: bool = False
    model: bool = False
    listModels: bool = False
    trust: bool = False
    apiKey: bool = False
    streamPartialOutput: bool = False


class RunnerUsage(BaseModel):
    """Optional usage metadata captured from a Cursor CLI process (Phase 23)."""

    model_config = ConfigDict(extra="forbid")

    inputTokens: int | None = None
    outputTokens: int | None = None
    totalTokens: int | None = None
    source: str | None = None


class CursorCapabilityReport(BaseModel):
    """Read-only Cursor CLI capability probe result."""

    model_config = ConfigDict(extra="forbid")

    status: CursorCapabilityStatus
    message: str
    executable: str | None = None
    version: str | None = None
    versionRaw: str | None = None
    minimumVersion: str
    helpExcerpt: str | None = None
    features: CursorFeatureFlags = Field(default_factory=CursorFeatureFlags)


class CursorModelInfo(BaseModel):
    """One model from ``agent --list-models`` (Phase 24.5)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)


class CursorModelsReport(BaseModel):
    """
    Live model catalog for the Skill inspector (Phase 24.5).

    ``auto`` is never included. ``defaultModel`` is always ``composer-2.5``.
    When the CLI is absent or listing fails, ``models`` still contains at least
    the default so the inspector stays editable.
    """

    model_config = ConfigDict(extra="forbid")

    status: CursorModelsStatus
    models: list[CursorModelInfo] = Field(default_factory=list)
    defaultModel: str = DEFAULT_CURSOR_SKILL_MODEL
    message: str | None = None
    executable: str | None = None


class CursorSkillPayload(BaseModel):
    """
    Skill execution fields used for Cursor command building (Phase 22).

    Mirrors ``SkillExecutionRequest`` without importing the runner layer into
    the domain package.
    """

    model_config = ConfigDict(extra="forbid")

    skillNodeId: str = Field(min_length=1)
    skillLabel: str
    description: str = ""
    # Phase 28.5: SKILL.md body (optional).
    content: str = ""
    inputPayload: str = ""
    inputMediaType: str = "text/plain"
    inputs: list[InputEnvelope] = Field(default_factory=list)
    rules: list[AttachedRule] = Field(default_factory=list)
    knowledgeChunks: list[CitedChunk] = Field(default_factory=list)
    # Phase 27: prompted Artifact Output projection template (optional).
    promptTemplate: str | None = None


class CursorDryRunOptions(BaseModel):
    """Options for building a Cursor CLI command without spawning (Phase 22)."""

    model_config = ConfigDict(extra="forbid")

    executable: str | None = None
    workspace: str | None = None
    features: CursorFeatureFlags | None = None
    model: str | None = None
    apiKey: str | None = None
    timeoutMs: int = Field(default=DEFAULT_CURSOR_TIMEOUT_MS, gt=0)
    force: bool = False
    trust: bool = True
    outputFormat: str = "text"
    confirmed: bool = False


class CursorRunOptions(BaseModel):
    """
    Options for spawning Cursor as the Skill runner (Phase 23).

    ``confirmed`` must be true before a real spawn (Phase 22 preview gate).
    ``model`` is a run-level fallback; per-Skill ``settings.model`` wins
    (Phase 24.5).
    """

    model_config = ConfigDict(extra="forbid")

    executable: str | None = None
    workspace: str | None = None
    features: CursorFeatureFlags | None = None
    model: str | None = None
    apiKey: str | None = None
    timeoutMs: int = Field(default=DEFAULT_CURSOR_TIMEOUT_MS, gt=0)
    force: bool = False
    trust: bool = True
    outputFormat: str = "text"
    confirmed: bool = False


class CursorDryRunRequest(BaseModel):
    """POST /api/cursor/dry-run body."""

    model_config = ConfigDict(extra="forbid")

    request: CursorSkillPayload
    options: CursorDryRunOptions = Field(default_factory=CursorDryRunOptions)


class CursorCommandPreview(BaseModel):
    """Redacted command preview returned by dry-run (no spawn)."""

    model_config = ConfigDict(extra="forbid")

    argv: list[str]
    commandDisplay: str
    stdin: str
    stdinPreview: str
    timeoutMs: int = Field(gt=0)
    workspace: str
    executable: str


class CursorDryRunResponse(BaseModel):
    """Dry-run result: preview only; ``spawned`` is always false."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    errors: list[str] = Field(default_factory=list)
    preview: CursorCommandPreview | None = None
    confirmationRequired: bool = True
    confirmed: bool = False
    message: str
    spawned: bool = False
