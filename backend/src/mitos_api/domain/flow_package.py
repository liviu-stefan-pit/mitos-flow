"""Versioned .flow package models (Phases 29–30).

Packaging modes:
- ``reference`` — manifests only (no ``original.*`` source docs)
- ``snapshot`` — Skill/Rules originals + all manifests (KB still reference)
- ``embedded`` — full embed including KB source docs
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.library import AssetKind
from mitos_api.domain.workflow import ValidationIssue, Workflow

PackagingMode = Literal["reference", "snapshot", "embedded"]


class ReferencedAssetStatus(str, Enum):
    """Status of a library asset after import (or during export inventory)."""

    RESTORED = "restored"
    ALREADY_PRESENT = "alreadyPresent"
    MISSING = "missing"
    EXPORTED = "exported"


class FlowFormatInfo(BaseModel):
    """Root ``format.json`` for a ``.flow`` archive."""

    model_config = ConfigDict(extra="forbid")

    formatVersion: int = Field(ge=1)
    packagingMode: PackagingMode = "reference"
    createdAt: str
    app: str = "mitos-flow"


class FlowExportRequest(BaseModel):
    """Request body for ``POST /api/workflows/export`` and export preview."""

    model_config = ConfigDict(extra="forbid")

    workflow: Workflow
    packagingMode: PackagingMode = "reference"


class ReferencedAssetInfo(BaseModel):
    """One library asset referenced by the workflow graph."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: AssetKind
    name: str
    status: ReferencedAssetStatus


class FlowPackageInventoryItem(BaseModel):
    """One asset entry in an export inventory preview (Phase 30)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: AssetKind
    name: str
    status: ReferencedAssetStatus
    includesOriginal: bool = False
    originalFilename: str | None = None
    manifestBytes: int = Field(ge=0, default=0)
    originalBytes: int = Field(ge=0, default=0)
    memberPaths: list[str] = Field(default_factory=list)


class FlowExportPreviewResponse(BaseModel):
    """Inventory preview for a planned ``.flow`` export (Phase 30)."""

    model_config = ConfigDict(extra="forbid")

    packagingMode: PackagingMode
    formatVersion: int
    assets: list[FlowPackageInventoryItem] = Field(default_factory=list)
    memberPaths: list[str] = Field(default_factory=list)
    estimatedUncompressedBytes: int = Field(ge=0, default=0)
    warnings: list[ValidationIssue] = Field(default_factory=list)


class FlowImportResponse(BaseModel):
    """Result of importing a ``.flow`` archive."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    formatVersion: int | None = None
    packagingMode: PackagingMode | None = None
    workflow: Workflow | None = None
    referencedAssets: list[ReferencedAssetInfo] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    errors: list[ValidationIssue] = Field(default_factory=list)
