"""Managed local asset library models (Phase 17)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from mitos_api.domain.workflow import ValidationIssue


class AssetKind(str, Enum):
    SKILL = "skill"
    RULES = "rules"
    KNOWLEDGE_BASE = "knowledgeBase"


class LibraryAssetManifest(BaseModel):
    """Normalized manifest stored alongside the original file bytes."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: AssetKind
    name: str = Field(min_length=1)
    description: str = ""
    originalFilename: str = Field(min_length=1)
    importedAt: str
    frontmatter: dict[str, Any] = Field(default_factory=dict)
    body: str = ""


class LibraryAsset(BaseModel):
    """Full library entry: original content + normalized manifest."""

    model_config = ConfigDict(extra="forbid")

    manifest: LibraryAssetManifest
    originalContent: str


class LibraryAssetSummary(BaseModel):
    """List view of a library asset (no body/original)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: AssetKind
    name: str
    description: str
    originalFilename: str
    importedAt: str


class LibraryPreviewRequest(BaseModel):
    """Preview a Markdown skill/rules file before confirming import."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    content: str
    kind: AssetKind | None = None


class LibraryPreviewResponse(BaseModel):
    """Preview result — does not write to the managed library."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    kind: AssetKind | None = None
    name: str | None = None
    description: str | None = None
    frontmatter: dict[str, Any] | None = None
    body: str | None = None
    originalContent: str | None = None
    originalFilename: str | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)


class LibraryImportRequest(BaseModel):
    """Confirm import of a previously previewed Markdown file."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    content: str
    kind: AssetKind | None = None


class LibraryImportResponse(BaseModel):
    """Result of confirming an import into the managed library."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    asset: LibraryAsset | None = None
    errors: list[ValidationIssue] = Field(default_factory=list)


class LibraryListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assets: list[LibraryAssetSummary] = Field(default_factory=list)


class LibraryBatchImportRequest(BaseModel):
    """Import several files in one request (gate: one Skill + multiple Rules)."""

    model_config = ConfigDict(extra="forbid")

    files: list[LibraryImportRequest] = Field(min_length=1)


class LibraryBatchImportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: list[LibraryImportResponse]
    importedCount: int
    failedCount: int
