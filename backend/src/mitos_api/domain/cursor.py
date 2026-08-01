"""Cursor CLI capability probe models (Phase 21)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CursorCapabilityStatus(str, Enum):
    """High-level probe result for Settings / later adapters."""

    ABSENT = "absent"
    AVAILABLE = "available"
    UNSUPPORTED_VERSION = "unsupported_version"
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
