"""
Deterministic full-text / keyword KB retrieval (Phases 19–20).

No embeddings, no PDF/Office conversion. Chunks are paragraph-based with a
fixed max size; scoring is keyword-overlap count against the Skill query.

Phase 20: top-K and threshold are applied per KB attachment (Skill/KB link).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mitos_api.domain.workflow import AttachedKnowledgeBase, CitedChunk

# Defaults when an attachment omits explicit controls.
DEFAULT_TOP_K = 5
DEFAULT_THRESHOLD = 0.0
_MAX_CHUNK_CHARS = 480

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "with",
    }
)


@dataclass(frozen=True)
class _RawChunk:
    chunk_id: str
    kb_node_id: str
    kb_label: str
    text: str
    index: int


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric tokens with common stopwords removed."""
    tokens = {match.group(0).lower() for match in _TOKEN_RE.finditer(text)}
    return {token for token in tokens if token not in _STOPWORDS and len(token) > 1}


def chunk_document(
    *,
    kb_node_id: str,
    kb_label: str,
    content: str,
) -> list[_RawChunk]:
    """
    Split KB content into deterministic chunks.

    Prefer blank-line paragraphs; oversized paragraphs are split on sentence
    boundaries, then hard-wrapped at ``_MAX_CHUNK_CHARS``.
    """
    text = (content or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    pieces: list[str] = []
    for paragraph in paragraphs:
        pieces.extend(_split_oversized(paragraph))

    chunks: list[_RawChunk] = []
    for index, piece in enumerate(pieces):
        chunks.append(
            _RawChunk(
                chunk_id=f"{kb_node_id}:c{index}",
                kb_node_id=kb_node_id,
                kb_label=kb_label,
                text=piece,
                index=index,
            )
        )
    return chunks


def _split_oversized(paragraph: str) -> list[str]:
    if len(paragraph) <= _MAX_CHUNK_CHARS:
        return [paragraph]

    # Prefer sentence boundaries.
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    buckets: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if not current:
            current = sentence
            continue
        if len(current) + 1 + len(sentence) <= _MAX_CHUNK_CHARS:
            current = f"{current} {sentence}"
        else:
            buckets.extend(_hard_wrap(current))
            current = sentence
    if current:
        buckets.extend(_hard_wrap(current))
    return buckets or [paragraph[:_MAX_CHUNK_CHARS]]


def _hard_wrap(text: str) -> list[str]:
    if len(text) <= _MAX_CHUNK_CHARS:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + _MAX_CHUNK_CHARS, len(text))
        if end < len(text):
            # Prefer breaking on whitespace.
            break_at = text.rfind(" ", start, end)
            if break_at > start + (_MAX_CHUNK_CHARS // 3):
                end = break_at
        piece = text[start:end].strip()
        if piece:
            parts.append(piece)
        start = end if end > start else start + _MAX_CHUNK_CHARS
    return parts


def _retrieve_one_attachment(
    kb: AttachedKnowledgeBase,
    query_tokens: set[str],
) -> list[CitedChunk]:
    """Score and truncate chunks for a single Skill/KB attachment."""
    top_k = kb.topK if kb.topK is not None else DEFAULT_TOP_K
    threshold = kb.threshold if kb.threshold is not None else DEFAULT_THRESHOLD
    if top_k < 1:
        return []

    scored: list[tuple[float, _RawChunk]] = []
    for chunk in chunk_document(
        kb_node_id=kb.kbNodeId,
        kb_label=kb.label,
        content=kb.content,
    ):
        chunk_tokens = tokenize(chunk.text)
        overlap = query_tokens & chunk_tokens
        score = float(len(overlap))
        if score > threshold:
            scored.append((score, chunk))

    scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
    selected = scored[:top_k]

    cited: list[CitedChunk] = []
    for score, chunk in selected:
        cited.append(
            CitedChunk(
                chunkId=chunk.chunk_id,
                kbNodeId=chunk.kb_node_id,
                kbLabel=chunk.kb_label,
                text=chunk.text,
                score=score,
                citation=f"{chunk.kb_label}#{chunk.index}",
                order=0,  # reassigned after merge
            )
        )
    return cited


def retrieve_cited_chunks(
    attached: list[AttachedKnowledgeBase],
    query: str,
    *,
    top_k: int | None = None,
    threshold: float | None = None,
) -> list[CitedChunk]:
    """
    Keyword-overlap retrieval over attached KB documents only.

    Attachment isolation is enforced by only scoring chunks from ``attached``.
    Each attachment applies its own ``topK`` / ``threshold`` (Phase 20).
    Optional ``top_k`` / ``threshold`` kwargs override every attachment
    (legacy test helper); when omitted, per-attachment controls win.
    Results are merged in attachment order; ``order`` is the merged rank.
    """
    if not attached:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # Optional global override for call sites that still pass top_k/threshold.
    effective = attached
    if top_k is not None or threshold is not None:
        effective = [
            kb.model_copy(
                update={
                    "topK": top_k if top_k is not None else kb.topK,
                    "threshold": (
                        threshold if threshold is not None else kb.threshold
                    ),
                }
            )
            for kb in attached
        ]

    cited: list[CitedChunk] = []
    for kb in effective:
        for chunk in _retrieve_one_attachment(kb, query_tokens):
            cited.append(chunk.model_copy(update={"order": len(cited)}))
    return cited


def build_retrieval_query(input_payload: str, inputs: list) -> str:
    """Deterministic query string from Skill inputs (port-sorted when multi-input)."""
    if inputs and len(inputs) > 1:
        parts = [
            f"{envelope.port}={envelope.payload}"
            for envelope in sorted(inputs, key=lambda item: item.port)
        ]
        return " | ".join(parts)
    if inputs:
        return inputs[0].payload
    return input_payload
