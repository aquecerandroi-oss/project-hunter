"""``GET /api/v1/regime`` — DATABASE.md §17, PIPELINE.md §4.

``MarketRegime.UNKNOWN`` is a classification, not an absence: the warm-up
state carries its own reason in ``supporting_features`` rather than a null
regime every consumer would have to invent a default for. ``is_stale`` marks
a regime that must not be read as "this is what the market is doing right
now" — never silently, and never presented as current without the flag.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer

from hunter_core.domain.enums import MarketRegime, RegimeScope

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")
]


class RegimeComponentOut(BaseModel):
    """One line of the hourly engine's decomposition
    (``hunter_indicators.regime.hourly_snapshot.ScoreComponent``), trimmed to
    what the tile shows — ``raw``/``reason`` stay inside
    ``RegimeOut.supporting_features`` for a reader who wants the full picture.
    """

    name: str
    normalized: DecimalStr | None = None
    weight: DecimalStr
    contribution: DecimalStr | None = None


class RegimeOut(BaseModel):
    id: uuid.UUID
    scope: RegimeScope
    regime: MarketRegime
    confidence: DecimalStr | None = None
    start_time: datetime
    end_time: datetime | None = None
    classifier_version: str | None = None
    supporting_features: dict[str, Any]
    is_stale: bool
    """``regime_v0`` (``classifier_version`` not ``regime_hourly_v1…``): ``true``
    in either of two cases, both meaning "do not read this as the live regime":

    - the row is **closed** (``end_time`` is not ``null``) and is only being
      shown because the caller asked for "current" and nothing newer exists;
    - the row is **open** (``end_time IS NULL``) but no ``hb:scanner:*``
      heartbeat confirms a live classifier (``routers/regime.py::_scanner_alive``).
      An open row alone proves only that a classifier once started this line,
      not that anything is still watching it — a scanner that died right after
      opening it would otherwise read fresh forever.

    ``regime_hourly_v1…`` rows are *always* closed by construction
    (``end_time = start_time + 1h``), so the rule above would read them
    permanently stale — honest about the hour having passed, but a defect on a
    tile whose newest row is exactly what a live hourly producer keeps writing
    (T3.43b). For these, ``true`` means the row's own hour is more than two
    hours past its ``end_time`` **or** the producer's ``regime_last_ts``
    heartbeat has not confirmed a write that recently
    (``services/regime.py::HOURLY_STALE_AFTER``)."""
    as_of: datetime | None = None
    """The hour this row governs — the same instant as ``start_time``, under
    its own name because "as of" is the question a reader of the hourly
    decomposition asks, not "when did this transition begin" (``start_time``'s
    meaning for ``regime_v0``). ``None`` for every row that is not
    ``regime_hourly_v1…``."""
    score: DecimalStr | None = None
    """``supporting_features.score_0_100`` (0-100) from the hourly engine's
    weighted decomposition. ``None`` for a non-hourly row, and also ``None``
    for an hourly row the engine itself could not score (too little of the
    component weight was available that hour) — never fabricated."""
    components: list[RegimeComponentOut] = []
    """The hourly engine's five-line decomposition (trend, breadth,
    volatility, drawdown, funding), each with its ``normalized``/``weight``/
    ``contribution``. Empty for every row that is not ``regime_hourly_v1…``."""
    identity: str | None = None
    """The hourly engine's own version string (``regime_hourly_v1`` or a
    ``+<digest>`` threshold-override variant) — the same value as
    ``classifier_version`` for that engine, exposed under its own name so a
    reader can key off "this row carries the hourly decomposition" without
    pattern-matching ``classifier_version``'s prefix itself. ``None`` for
    ``regime_v0``."""


class RegimeCurrentOut(BaseModel):
    items: list[RegimeOut]
    as_of: datetime


class RegimeHistoryPage(BaseModel):
    items: list[RegimeOut]
    next_cursor: str | None = None
