"""How fresh a market's hot state is — the staleness verdict the API and the UI
show as a badge.

Split out of :mod:`hunter_core.domain.market` (T3.0b, 350-line budget): that
module is the normalized *payload* contract, and this is a judgement about how
old a payload is. Nothing in the models depends on it, and every caller reads
it from here or from the re-export ``market.py`` keeps for its historical
importers.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from hunter_core.domain.types import ensure_utc

__all__ = ["DataQuality", "data_quality"]


class DataQuality(StrEnum):
    """Freshness of a market's hot state — ``docs/plans/M1.md`` staleness rule."""

    OK = "ok"
    STALE = "stale"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


def data_quality(
    last_event_at: datetime | None,
    *,
    now: datetime,
    stale_after_s: int,
    has_open_gap: bool,
) -> DataQuality:
    """Classify a market's data freshness for the API/UI staleness badge."""
    if last_event_at is None:
        return DataQuality.UNAVAILABLE
    if has_open_gap:
        return DataQuality.DEGRADED
    age_s = (ensure_utc(now) - ensure_utc(last_event_at)).total_seconds()
    if age_s > stale_after_s:
        return DataQuality.STALE
    return DataQuality.OK
