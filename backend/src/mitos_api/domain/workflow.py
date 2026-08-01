"""Pydantic workflow schema — shared contract for frontend/backend (Phase 9)."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeKind(str, Enum):
    INPUT = "input"
    SKILL = "skill"
    KNOWLEDGE_BASE = "knowledgeBase"
    RULES = "rules"
    ARTIFACT_OUTPUT = "artifactOutput"


class EdgeKind(str, Enum):
    DATA_FLOW = "dataFlow"
    RESOURCE_ATTACHMENT = "resourceAttachment"


class PortKind(str, Enum):
    DATA = "data"
    RESOURCE = "resource"


class PortDirection(str, Enum):
    IN = "in"
    OUT = "out"


class JoinPolicy(str, Enum):
    WAIT_FOR_ALL = "wait_for_all"


class ArtifactOutputMode(str, Enum):
    PASS_THROUGH = "pass-through"
    SELECTOR = "selector"
    PROMPTED = "prompted"


class ArtifactDestinationKind(str, Enum):
    """Where a pass-through Artifact Output delivers its payload (Phase 25)."""

    PREVIEW = "preview"
    MANAGED_FILE = "managedFile"


class ArtifactFileWriteMode(str, Enum):
    """Managed-file write policy under the approved output root."""

    OVERWRITE = "overwrite"
    TIMESTAMPED = "timestamped"


class SelectorKind(str, Enum):
    """Non-LLM Artifact Output selectors (Phase 26)."""

    JSON_PATH = "jsonPath"
    NAMED_SECTION = "namedSection"


class MissingDataPolicy(str, Enum):
    """
    What happens when a selector matches nothing (Phase 26).

    - skip: mark this output branch skipped (run may still complete)
    - empty: deliver an empty artifact
    - warning: deliver a warning-text artifact
    - fail: fail this output branch (and the run)
    """

    SKIP = "skip"
    EMPTY = "empty"
    WARNING = "warning"
    FAIL = "fail"


class InputEnvelope(BaseModel):
    """
    One named input delivered to a Skill (Phase 14+).

    ``order`` records arrival sequence for trace display and does not affect
    wait_for_all join logic or FakeRunner output.
    """

    model_config = ConfigDict(extra="forbid")

    port: str = Field(min_length=1)
    payload: str
    mediaType: str = "text/plain"
    sourceNodeId: str = Field(min_length=1)
    order: int = Field(ge=0)


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class Port(BaseModel):
    """Named port on a node (data or resource, in or out)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: PortKind
    direction: PortDirection
    name: str | None = None


class InputNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mediaType: str = "text/plain"
    content: str = ""


SkillRunnerKind = Literal["fake", "cursor"]

# Phase 24.5: cheapest Composer model — never let a Skill silently fall
# through to the Cursor CLI's expensive `auto` model.
DEFAULT_CURSOR_SKILL_MODEL = "composer-2.5"


class SkillNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = ""
    # Phase 28.5: SKILL.md body applied from the managed library (optional).
    content: str = ""
    libraryAssetId: str | None = None
    joinPolicy: JoinPolicy = JoinPolicy.WAIT_FOR_ALL
    # Phase 24: per-Skill Fake or Cursor runner (default fake).
    runner: SkillRunnerKind = "fake"
    # Phase 24.5: preferred Cursor model for this Skill (meaningful only when
    # runner="cursor"). Always non-empty so Cursor is never spawned without
    # an explicit --model.
    model: str = Field(default=DEFAULT_CURSOR_SKILL_MODEL, min_length=1)


class KnowledgeBaseNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = ""
    content: str = ""
    libraryAssetId: str | None = None


class RulesNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = ""
    content: str = ""
    libraryAssetId: str | None = None


class AttachedRule(BaseModel):
    """
    One Rules node resolved onto a Skill before execution (Phase 18+).

    ``order`` is the stable index after deterministic sort by rules node id.
    """

    model_config = ConfigDict(extra="forbid")

    rulesNodeId: str = Field(min_length=1)
    label: str
    content: str = ""
    order: int = Field(ge=0)


class ResourceAttachmentSettings(BaseModel):
    """
    Per resource-attachment edge controls (Phase 20+).

    Meaningful for KB→Skill links: ``topK`` and ``threshold`` scope retrieval
    to that Skill/KB attachment only. Rules attachments ignore these fields.
    """

    model_config = ConfigDict(extra="forbid")

    topK: int = Field(default=5, ge=1)
    threshold: float = Field(default=0.0, ge=0)


class AttachedKnowledgeBase(BaseModel):
    """
    One Knowledge Base node resolved onto a Skill before retrieval (Phase 19+).

    ``order`` is the stable index after deterministic sort by KB node id.
    ``topK`` / ``threshold`` come from the resource-attachment edge (Phase 20).
    """

    model_config = ConfigDict(extra="forbid")

    kbNodeId: str = Field(min_length=1)
    label: str
    content: str = ""
    order: int = Field(ge=0)
    topK: int = Field(default=5, ge=1)
    threshold: float = Field(default=0.0, ge=0)


class CitedChunk(BaseModel):
    """
    One retrieved KB chunk with citation metadata (Phase 19+).

    Produced by deterministic full-text/keyword retrieval — no embeddings.
    ``order`` is the rank within the Skill's retrieval result list.
    """

    model_config = ConfigDict(extra="forbid")

    chunkId: str = Field(min_length=1)
    kbNodeId: str = Field(min_length=1)
    kbLabel: str
    text: str
    score: float = Field(ge=0)
    citation: str = Field(min_length=1)
    order: int = Field(ge=0)


class ArtifactOutputNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ArtifactOutputMode = ArtifactOutputMode.PASS_THROUGH
    # Phase 25 — destinations (preview stays in-memory; managedFile writes to disk)
    destination: ArtifactDestinationKind = ArtifactDestinationKind.PREVIEW
    filePath: str | None = Field(
        default=None,
        description=(
            "Relative path under MITOS_OUTPUT_ROOT when destination is managedFile"
        ),
    )
    writeMode: ArtifactFileWriteMode = ArtifactFileWriteMode.TIMESTAMPED
    # Phase 26 — deterministic selectors (meaningful when mode=selector)
    selectorKind: SelectorKind | None = None
    selectorExpression: str | None = Field(
        default=None,
        description="JSONPath expression or named text section heading",
    )
    missingDataPolicy: MissingDataPolicy = MissingDataPolicy.FAIL
    # Phase 27 — prompted projection (meaningful when mode=prompted).
    # First-class prompt template — never buried inside destination/file save.
    promptTemplate: str | None = Field(
        default=None,
        description="Prompt template for prompted projection (required when mode=prompted)",
    )
    # Phase 27 — own runner/model for the explicit second model call
    runner: SkillRunnerKind = "fake"
    model: str = Field(default=DEFAULT_CURSOR_SKILL_MODEL, min_length=1)

    @model_validator(mode="after")
    def _managed_file_requires_path(self) -> ArtifactOutputNodeSettings:
        if self.destination is ArtifactDestinationKind.MANAGED_FILE:
            path = (self.filePath or "").strip()
            if not path:
                raise ValueError(
                    "filePath is required when destination is managedFile"
                )
            self.filePath = path
        return self

    @model_validator(mode="after")
    def _selector_requires_kind_and_expression(self) -> ArtifactOutputNodeSettings:
        if self.mode is not ArtifactOutputMode.SELECTOR:
            return self
        if self.selectorKind is None:
            raise ValueError(
                "selectorKind is required when mode is selector "
                "(jsonPath or namedSection)"
            )
        expression = (self.selectorExpression or "").strip()
        if not expression:
            raise ValueError(
                "selectorExpression is required when mode is selector"
            )
        self.selectorExpression = expression
        return self

    @model_validator(mode="after")
    def _prompted_requires_template(self) -> ArtifactOutputNodeSettings:
        if self.mode is not ArtifactOutputMode.PROMPTED:
            return self
        template = (self.promptTemplate or "").strip()
        if not template:
            raise ValueError(
                "promptTemplate is required when mode is prompted"
            )
        self.promptTemplate = template
        model = (self.model or "").strip() or DEFAULT_CURSOR_SKILL_MODEL
        self.model = model
        return self


def default_ports_for_kind(kind: NodeKind) -> list[Port]:
    """Canonical ports matching the React Flow handles (Phase 6)."""
    if kind is NodeKind.INPUT:
        return [Port(id="data-out", kind=PortKind.DATA, direction=PortDirection.OUT)]
    if kind is NodeKind.SKILL:
        return [
            Port(id="data-in", kind=PortKind.DATA, direction=PortDirection.IN, name="default"),
            Port(id="data-out", kind=PortKind.DATA, direction=PortDirection.OUT),
            Port(id="resource-in", kind=PortKind.RESOURCE, direction=PortDirection.IN),
            # Phase 28.5: layout alias — same attachment semantics as resource-in.
            Port(id="resource-in-top", kind=PortKind.RESOURCE, direction=PortDirection.IN),
        ]
    if kind is NodeKind.KNOWLEDGE_BASE:
        return [
            Port(id="resource-out", kind=PortKind.RESOURCE, direction=PortDirection.OUT),
        ]
    if kind is NodeKind.RULES:
        return [
            Port(id="resource-out", kind=PortKind.RESOURCE, direction=PortDirection.OUT),
        ]
    # ARTIFACT_OUTPUT
    return [Port(id="data-in", kind=PortKind.DATA, direction=PortDirection.IN)]


class WorkflowNode(BaseModel):
    """A single workflow node with kind-specific settings."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: NodeKind
    label: str
    position: Position
    ports: list[Port] = Field(default_factory=list)
    settings: (
        InputNodeSettings
        | SkillNodeSettings
        | KnowledgeBaseNodeSettings
        | RulesNodeSettings
        | ArtifactOutputNodeSettings
    )

    @model_validator(mode="before")
    @classmethod
    def _default_ports_and_coerce_settings(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        raw = dict(data)
        kind_raw = raw.get("kind")
        try:
            kind = NodeKind(kind_raw) if kind_raw is not None else None
        except ValueError:
            kind = None

        if kind is not None and ("ports" not in raw or raw["ports"] is None):
            raw["ports"] = [p.model_dump(mode="json") for p in default_ports_for_kind(kind)]

        settings = raw.get("settings")
        if kind is not None and isinstance(settings, dict):
            raw["settings"] = _coerce_settings(kind, settings)
        elif kind is not None and settings is None:
            raw["settings"] = _default_settings(kind)

        return raw

    @model_validator(mode="after")
    def _settings_match_kind(self) -> WorkflowNode:
        expected = _settings_type_for_kind(self.kind)
        if not isinstance(self.settings, expected):
            raise ValueError(
                f"Node '{self.id}' kind '{self.kind.value}' requires "
                f"{expected.__name__} settings."
            )
        return self


def _settings_type_for_kind(
    kind: NodeKind,
) -> type[
    InputNodeSettings
    | SkillNodeSettings
    | KnowledgeBaseNodeSettings
    | RulesNodeSettings
    | ArtifactOutputNodeSettings
]:
    return {
        NodeKind.INPUT: InputNodeSettings,
        NodeKind.SKILL: SkillNodeSettings,
        NodeKind.KNOWLEDGE_BASE: KnowledgeBaseNodeSettings,
        NodeKind.RULES: RulesNodeSettings,
        NodeKind.ARTIFACT_OUTPUT: ArtifactOutputNodeSettings,
    }[kind]


def _default_settings(
    kind: NodeKind,
) -> (
    InputNodeSettings
    | SkillNodeSettings
    | KnowledgeBaseNodeSettings
    | RulesNodeSettings
    | ArtifactOutputNodeSettings
):
    return _settings_type_for_kind(kind)()


def _coerce_settings(kind: NodeKind, settings: dict) -> BaseModel:
    return _settings_type_for_kind(kind).model_validate(settings)


class WorkflowEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: EdgeKind
    sourceNodeId: str = Field(min_length=1)
    targetNodeId: str = Field(min_length=1)
    sourcePortId: str = Field(min_length=1)
    targetPortId: str = Field(min_length=1)
    settings: ResourceAttachmentSettings | None = None


class WorkflowMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "Untitled Workflow"
    schemaVersion: Literal[1] = 1


class Workflow(BaseModel):
    """Versioned shared workflow document."""

    model_config = ConfigDict(extra="forbid")

    metadata: WorkflowMetadata = Field(default_factory=WorkflowMetadata)
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    nodeId: str | None = None
    edgeId: str | None = None


class WorkflowValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    workflow: Workflow | None = None
