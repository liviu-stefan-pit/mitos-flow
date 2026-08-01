"""Deterministic Artifact Output selectors (Phase 26).

Non-LLM projections over upstream Skill payloads:
- JSONPath (minimal subset: ``$.a.b``, ``$.a[0]``, ``$['key']``)
- Named text sections (Markdown-style ATX headings)

Selectors never invoke a runner.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from mitos_api.domain.workflow import (
    MissingDataPolicy,
    SelectorKind,
)

# Heading line: ATX Markdown (# … ######) with optional trailing hashes.
_HEADING_RE = re.compile(
    r"^(#{1,6})\s+(.+?)(?:\s+#*)?\s*$",
    re.MULTILINE,
)

# Minimal JSONPath tokens: .name | ['name'] | ["name"] | [index]
_JSONPATH_TOKEN_RE = re.compile(
    r"""
    \.
      (?P<dot>[A-Za-z_][A-Za-z0-9_]*)
    |
    \[\s*
      (?:
        '(?P<sq>(?:\\'|[^'])*)'
        |
        "(?P<dq>(?:\\"|[^"])*)"
        |
        (?P<idx>\d+)
      )
    \s*\]
    """,
    re.VERBOSE,
)


class SelectorError(ValueError):
    """Raised when a selector expression is invalid (not merely unmatched)."""

    def __init__(self, message: str, *, code: str = "selector_error") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SelectorMatch:
    """Successful selector extraction."""

    payload: str
    media_type: str


@dataclass(frozen=True)
class SelectorMiss:
    """Selector ran but matched no data."""

    reason: str


def apply_selector(
    payload: str,
    *,
    kind: SelectorKind,
    expression: str,
    media_type: str | None = None,
) -> SelectorMatch | SelectorMiss:
    """
    Apply a deterministic selector to ``payload``.

    Returns ``SelectorMatch`` on hit, ``SelectorMiss`` when the expression is
    valid but finds nothing. Invalid expressions raise ``SelectorError``.
    """
    del media_type  # reserved for future content-type hints
    expr = (expression or "").strip()
    if not expr:
        raise SelectorError(
            "selectorExpression must be non-empty",
            code="selector_expression_required",
        )

    if kind is SelectorKind.JSON_PATH:
        return _apply_jsonpath(payload, expr)
    if kind is SelectorKind.NAMED_SECTION:
        return _apply_named_section(payload, expr)
    raise SelectorError(  # pragma: no cover - enum exhaustiveness
        f"Unsupported selector kind: {kind}",
        code="selector_kind",
    )


def resolve_missing_payload(
    *,
    policy: MissingDataPolicy,
    kind: SelectorKind,
    expression: str,
    reason: str,
) -> tuple[str | None, str | None]:
    """
    Map a selector miss to deliverable content under ``missingDataPolicy``.

    Returns ``(payload, media_type)`` when the branch should continue with
    content, or ``(None, None)`` when the caller should skip / fail instead
    (``skip`` and ``fail`` return None so the orchestrator handles state).
    """
    if policy is MissingDataPolicy.EMPTY:
        return "", "text/plain"
    if policy is MissingDataPolicy.WARNING:
        warning = (
            f"WARNING: selector {kind.value} '{expression}' matched no data "
            f"({reason})"
        )
        return warning, "text/plain"
    # skip / fail — orchestrator decides node state
    return None, None


def _apply_jsonpath(payload: str, expression: str) -> SelectorMatch | SelectorMiss:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SelectorError(
            f"JSONPath selector requires JSON upstream payload: {exc.msg}",
            code="selector_not_json",
        ) from exc

    try:
        value = _eval_jsonpath(data, expression)
    except SelectorError:
        raise
    except Exception as exc:
        raise SelectorError(
            f"Invalid JSONPath expression '{expression}': {exc}",
            code="selector_jsonpath_invalid",
        ) from exc

    if isinstance(value, _JsonPathMiss):
        return SelectorMiss(reason=f"JSONPath '{expression}' matched nothing")
    return _serialize_json_value(value)


class _JsonPathMiss:
    """Sentinel for a valid path that resolved to a missing key/index."""


def _eval_jsonpath(data: Any, expression: str) -> Any | _JsonPathMiss:
    expr = expression.strip()
    if not expr.startswith("$"):
        raise SelectorError(
            f"JSONPath must start with '$' (got '{expression}')",
            code="selector_jsonpath_invalid",
        )
    rest = expr[1:]
    if rest == "":
        return data

    current: Any = data
    pos = 0
    while pos < len(rest):
        match = _JSONPATH_TOKEN_RE.match(rest, pos)
        if match is None:
            raise SelectorError(
                f"Invalid JSONPath expression '{expression}' "
                f"near '{rest[pos:]}'",
                code="selector_jsonpath_invalid",
            )
        pos = match.end()
        if match.group("dot") is not None:
            key: str | int = match.group("dot")
        elif match.group("sq") is not None:
            key = match.group("sq").replace("\\'", "'")
        elif match.group("dq") is not None:
            key = match.group("dq").replace('\\"', '"')
        else:
            key = int(match.group("idx"))

        if isinstance(current, _JsonPathMiss):
            return current
        if isinstance(key, int):
            if not isinstance(current, list) or key >= len(current) or key < 0:
                return _JsonPathMiss()
            current = current[key]
        else:
            if not isinstance(current, dict) or key not in current:
                return _JsonPathMiss()
            current = current[key]

    if pos != len(rest):
        raise SelectorError(
            f"Invalid JSONPath expression '{expression}'",
            code="selector_jsonpath_invalid",
        )
    return current


def _serialize_json_value(value: object) -> SelectorMatch:
    if value is None:
        return SelectorMatch(payload="null", media_type="application/json")
    if isinstance(value, bool):
        return SelectorMatch(
            payload="true" if value else "false",
            media_type="application/json",
        )
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return SelectorMatch(payload=str(value), media_type="application/json")
    if isinstance(value, str):
        return SelectorMatch(payload=value, media_type="text/plain")
    # objects / arrays — stable JSON with compact separators
    return SelectorMatch(
        payload=json.dumps(value, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
    )


def _normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip()).casefold()


def _apply_named_section(
    payload: str,
    heading: str,
) -> SelectorMatch | SelectorMiss:
    """
    Extract the body under the first Markdown ATX heading matching ``heading``.

    Match is case-insensitive on the heading text (hashes ignored). Body runs
    until the next heading of the same or higher level (fewer or equal #).
    """
    target = _normalize_heading(heading)
    if not target:
        raise SelectorError(
            "namedSection heading must be non-empty",
            code="selector_expression_required",
        )

    matches = list(_HEADING_RE.finditer(payload))
    if not matches:
        return SelectorMiss(reason="upstream payload has no Markdown headings")

    start_idx: int | None = None
    start_level: int | None = None
    body_start = 0

    for index, match in enumerate(matches):
        level = len(match.group(1))
        title = _normalize_heading(match.group(2))
        if title == target:
            start_idx = index
            start_level = level
            body_start = match.end()
            break

    if start_idx is None or start_level is None:
        return SelectorMiss(
            reason=f"named section heading '{heading}' not found"
        )

    body_end = len(payload)
    for match in matches[start_idx + 1 :]:
        level = len(match.group(1))
        if level <= start_level:
            body_end = match.start()
            break

    body = payload[body_start:body_end].strip("\r\n")
    if body == "":
        return SelectorMiss(reason=f"named section '{heading}' is empty")

    return SelectorMatch(payload=body, media_type="text/markdown")
