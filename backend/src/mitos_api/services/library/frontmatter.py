"""Safe Markdown frontmatter parsing for Skill and Rules imports (Phase 17)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

from mitos_api.domain.library import AssetKind
from mitos_api.domain.workflow import ValidationIssue

_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n(.*?\r?\n)---[ \t]*(?:\r?\n|$)",
    re.DOTALL,
)

_SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ParsedDocument:
    frontmatter: dict[str, Any]
    body: str
    has_frontmatter: bool


@dataclass(frozen=True)
class NormalizedPreview:
    kind: AssetKind
    name: str
    description: str
    frontmatter: dict[str, Any]
    body: str
    original_filename: str


def parse_frontmatter(content: str) -> tuple[ParsedDocument | None, list[ValidationIssue]]:
    """
    Parse YAML frontmatter from a Markdown document.

    Malformed frontmatter is reported via ValidationIssue — never raises.
    """
    if content is None:
        return None, [
            ValidationIssue(
                code="empty_content",
                message="File content is empty.",
            )
        ]

    text = content.replace("\ufeff", "")
    if not text.strip():
        return None, [
            ValidationIssue(
                code="empty_content",
                message="File content is empty.",
            )
        ]

    # Opening fence without a matching close → malformed (safe report).
    if text.lstrip().startswith("---"):
        match = _FRONTMATTER_RE.match(text)
        if match is None:
            return None, [
                ValidationIssue(
                    code="malformed_frontmatter",
                    message=(
                        "Malformed frontmatter: opening '---' found but "
                        "closing '---' is missing or invalid."
                    ),
                )
            ]
        raw_yaml = match.group(1)
        body = text[match.end() :]
        try:
            loaded = yaml.safe_load(raw_yaml)
        except yaml.YAMLError as exc:
            return None, [
                ValidationIssue(
                    code="malformed_frontmatter",
                    message=f"Malformed frontmatter YAML: {exc}",
                )
            ]
        if loaded is None:
            frontmatter: dict[str, Any] = {}
        elif not isinstance(loaded, dict):
            return None, [
                ValidationIssue(
                    code="malformed_frontmatter",
                    message=(
                        "Malformed frontmatter: expected a YAML mapping "
                        f"(key/value pairs), got {type(loaded).__name__}."
                    ),
                )
            ]
        else:
            frontmatter = dict(loaded)
        return ParsedDocument(frontmatter=frontmatter, body=body, has_frontmatter=True), []

    # No frontmatter fence — treat entire file as body.
    return ParsedDocument(frontmatter={}, body=text, has_frontmatter=False), []


def _basename(filename: str) -> str:
    # Normalize Windows separators without touching the filesystem.
    normalized = filename.replace("\\", "/")
    return PurePosixPath(normalized).name


def _stem(filename: str) -> str:
    name = _basename(filename)
    if "." in name:
        return name.rsplit(".", 1)[0]
    return name


def infer_asset_kind(
    filename: str,
    frontmatter: dict[str, Any],
    *,
    explicit: AssetKind | None = None,
) -> tuple[AssetKind | None, list[ValidationIssue]]:
    """Infer skill vs rules from filename / frontmatter, or use explicit kind."""
    if explicit is not None:
        return explicit, []

    base = _basename(filename).lower()
    if base == "skill.md":
        return AssetKind.SKILL, []
    if base.endswith(".mdc"):
        return AssetKind.RULES, []

    has_name = isinstance(frontmatter.get("name"), str) and bool(
        str(frontmatter.get("name")).strip()
    )
    has_description = "description" in frontmatter
    has_rules_keys = any(k in frontmatter for k in ("alwaysApply", "globs", "always_apply"))

    if has_name and has_description and not has_rules_keys:
        return AssetKind.SKILL, []
    if has_rules_keys or (has_description and not has_name):
        return AssetKind.RULES, []

    return None, [
        ValidationIssue(
            code="ambiguous_kind",
            message=(
                "Could not determine whether this file is a Skill or Rules asset. "
                "Provide kind explicitly, use SKILL.md / .mdc naming, or include "
                "distinguishing frontmatter."
            ),
        )
    ]


def _normalize_skill(
    parsed: ParsedDocument,
    filename: str,
) -> tuple[NormalizedPreview | None, list[ValidationIssue]]:
    errors: list[ValidationIssue] = []
    if not parsed.has_frontmatter:
        errors.append(
            ValidationIssue(
                code="missing_frontmatter",
                message="Skill files require YAML frontmatter with name and description.",
            )
        )
        return None, errors

    raw_name = parsed.frontmatter.get("name")
    raw_description = parsed.frontmatter.get("description")

    if not isinstance(raw_name, str) or not raw_name.strip():
        errors.append(
            ValidationIssue(
                code="missing_field",
                message="Skill frontmatter is missing required string field 'name'.",
                            )
        )
    elif not _SKILL_NAME_RE.match(raw_name.strip()):
        errors.append(
            ValidationIssue(
                code="invalid_field",
                message=(
                    "Skill 'name' must be lowercase letters, numbers, and hyphens only."
                ),
                            )
        )

    if not isinstance(raw_description, str) or not raw_description.strip():
        errors.append(
            ValidationIssue(
                code="missing_field",
                message="Skill frontmatter is missing required string field 'description'.",
                            )
        )

    if errors:
        return None, errors

    assert isinstance(raw_name, str)
    assert isinstance(raw_description, str)
    return (
        NormalizedPreview(
            kind=AssetKind.SKILL,
            name=raw_name.strip(),
            description=raw_description.strip(),
            frontmatter=dict(parsed.frontmatter),
            body=parsed.body,
            original_filename=_basename(filename),
        ),
        [],
    )


def _normalize_rules(
    parsed: ParsedDocument,
    filename: str,
) -> tuple[NormalizedPreview | None, list[ValidationIssue]]:
    # Rules may omit frontmatter; derive a stable name from the filename.
    name: str
    description = ""
    fm = dict(parsed.frontmatter)

    raw_name = fm.get("name")
    if isinstance(raw_name, str) and raw_name.strip():
        name = raw_name.strip()
    else:
        stem = _stem(filename).strip()
        if not stem:
            return None, [
                ValidationIssue(
                    code="missing_name",
                    message="Could not derive a Rules asset name from the filename.",
                )
            ]
        name = stem

    raw_description = fm.get("description")
    if isinstance(raw_description, str):
        description = raw_description.strip()

    if not parsed.body.strip() and not description:
        return None, [
            ValidationIssue(
                code="empty_rules",
                message="Rules file has no body content and no description.",
            )
        ]

    return (
        NormalizedPreview(
            kind=AssetKind.RULES,
            name=name,
            description=description,
            frontmatter=fm,
            body=parsed.body,
            original_filename=_basename(filename),
        ),
        [],
    )


def normalize_document(
    content: str,
    filename: str,
    *,
    kind: AssetKind | None = None,
) -> tuple[NormalizedPreview | None, list[ValidationIssue]]:
    """Parse + normalize a skill/rules Markdown file for preview or import."""
    parsed, parse_errors = parse_frontmatter(content)
    if parse_errors or parsed is None:
        return None, parse_errors

    inferred, kind_errors = infer_asset_kind(
        filename, parsed.frontmatter, explicit=kind
    )
    if kind_errors or inferred is None:
        return None, kind_errors

    if inferred is AssetKind.SKILL:
        return _normalize_skill(parsed, filename)
    return _normalize_rules(parsed, filename)
