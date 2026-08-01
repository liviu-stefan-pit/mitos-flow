"""Versioned local model rate table for estimated cost (Phase 28).

Rates are approximate USD per million tokens from public Cursor pricing
snapshots. They are **not** live billing rates — UI must label estimates
as estimates, never as exact charges.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump when rates change so summaries can cite which table was used.
RATE_TABLE_VERSION = 1


@dataclass(frozen=True, slots=True)
class RateEntry:
    """USD per 1_000_000 tokens for one model id."""

    model: str
    inputPerMillionUsd: float
    outputPerMillionUsd: float


# Approximate public rates (Composer 2.5 standard / fast). Fake runner is $0
# so local demos still show an estimated total without implying real spend.
_RATES: dict[str, RateEntry] = {
    "composer-2.5": RateEntry(
        model="composer-2.5",
        inputPerMillionUsd=0.50,
        outputPerMillionUsd=2.50,
    ),
    "composer-2.5-fast": RateEntry(
        model="composer-2.5-fast",
        inputPerMillionUsd=3.00,
        outputPerMillionUsd=15.00,
    ),
    "fake": RateEntry(
        model="fake",
        inputPerMillionUsd=0.0,
        outputPerMillionUsd=0.0,
    ),
}


def get_rate(model: str | None) -> RateEntry | None:
    """Look up a rate by model id; returns None when pricing is unavailable."""
    if model is None:
        return None
    key = model.strip().lower()
    if not key:
        return None
    return _RATES.get(key)


def list_rate_models() -> list[str]:
    """Sorted model ids present in the local rate table."""
    return sorted(_RATES.keys())
