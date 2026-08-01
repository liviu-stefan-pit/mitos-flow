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


class SkillNodeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = ""
    joinPolicy: JoinPolicy = JoinPolicy.WAIT_FOR_ALL


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


class AttachedKnowledgeBase(BaseModel):
    """
    One Knowledge Base node resolved onto a Skill before retrieval (Phase 19+).

    ``order`` is the stable index after deterministic sort by KB node id.
    """

    model_config = ConfigDict(extra="forbid")

    kbNodeId: str = Field(min_length=1)
    label: str
    content: str = ""
    order: int = Field(ge=0)


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


def default_ports_for_kind(kind: NodeKind) -> list[Port]:
    """Canonical ports matching the React Flow handles (Phase 6)."""
    if kind is NodeKind.INPUT:
        return [Port(id="data-out", kind=PortKind.DATA, direction=PortDirection.OUT)]
    if kind is NodeKind.SKILL:
        return [
            Port(id="data-in", kind=PortKind.DATA, direction=PortDirection.IN, name="default"),
            Port(id="data-out", kind=PortKind.DATA, direction=PortDirection.OUT),
            Port(id="resource-in", kind=PortKind.RESOURCE, direction=PortDirection.IN),
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
