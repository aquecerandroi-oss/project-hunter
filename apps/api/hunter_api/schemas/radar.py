"""``GET /api/v1/radar`` payloads — DATABASE.md §17.3, PIPELINE.md §5.

One row per ``opportunities`` episode joined to its market identity — never a
market without one (``repositories/radar.py`` selects ``FROM opportunities``,
not ``FROM markets``, so a market that has no scored opportunity yet simply
does not appear, rather than showing a fabricated zero score).

``in_position``/``risk_blocked`` are the two statuses PIPELINE.md §5 says are
"derived per organization at read time" and therefore never stored on
``opportunities.status`` (``hunter_core.domain.enums.OpportunityStatus``
docstring). They are ``None`` whenever the request carries no ``org_id`` —
absence of an organization context, not a claim about the position/risk
state — and a concrete ``bool`` once one is supplied and validated
(``services/radar_org_derivation.py``). M2 has no Risk Engine yet (that is M3/M4),
so ``risk_blocked`` only ever reflects an active kill switch (system,
organization or portfolio); ``true`` is definitive, ``None`` means "not
evaluated", and ``false`` means only "no ``TRADING_DISABLED``/``EMERGENCY`` kill
switch was found" (``WARNING`` allows entries at half size, ``RISK_ENGINE.md``
§5) — a narrower claim than "this trade clears every future risk check", which
this API cannot evaluate at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

from hunter_core.domain.enums import (
    MarketRegime,
    MarketType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: str(v), return_type=str, when_used="json")
]

RadarSortKey = Literal["score", "change", "volume", "age"]
SortOrder = Literal["asc", "desc"]

MAX_SCORE = 100
"""Upper bound of every ``score``/``severity`` query parameter. The columns are
``NUMERIC(5,2)`` holding a 0–100 score (PIPELINE.md §3, §5), and the bound is
declared so Pydantic rejects ``NaN``/``Infinity`` — both of which parse into a
``Decimal`` happily and then reach Postgres, where they are either an error or
silently match nothing. An ``int`` because ``Query(ge=..., le=...)`` takes a
number, not a ``Decimal``; the comparison against a ``Decimal`` is exact."""

MAX_VOLATILITY = 1000
"""Upper bound of ``volatility_min``/``volatility_max``. ``atr_14_pct`` is a
*fraction* (Wilder-14 ATR over price), so anything above ~1 is already absurd;
``1000`` is a deliberately generous finite ceiling whose only job is to make
the parameter reject non-finite values."""

DERIVED_STATUS_VALUES = frozenset({"IN_POSITION", "RISK_BLOCKED"})
"""Pseudo-statuses accepted by ``?status=`` alongside ``OpportunityStatus``
members — never stored, only ever filtered/derived at read time."""


class RadarStatusFilter(StrEnum):
    """``?status=`` — every ``OpportunityStatus`` member plus the two
    per-organization pseudo-statuses. A plain ``list[OpportunityStatus]``
    would 422 on ``IN_POSITION``/``RISK_BLOCKED`` before the router ever saw
    them; this is the accept-list that lets FastAPI validate the whole set in
    one declaration.
    """

    NORMAL = "NORMAL"
    WATCHING = "WATCHING"
    ANOMALY = "ANOMALY"
    HOT = "HOT"
    ENTRY_CANDIDATE = "ENTRY_CANDIDATE"
    EXTENDED = "EXTENDED"
    EXPIRED = "EXPIRED"
    IN_POSITION = "IN_POSITION"
    RISK_BLOCKED = "RISK_BLOCKED"


class RadarItemOut(BaseModel):
    """One row of the radar table."""

    opportunity_id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    market_type: MarketType
    direction: TradeDirection
    score: DecimalStr
    confidence: DecimalStr
    peak_score: DecimalStr | None = None
    status: OpportunityStatus
    stage: OpportunityStage
    regime: MarketRegime | None = None
    change: DecimalStr | None = None
    """Delta against the last persisted ``opportunity_history`` sample — ``0``
    when this is the first sample of the episode (nothing to compare against
    yet), ``null`` only if that history read itself failed."""
    first_seen_at: datetime
    last_updated_at: datetime
    below_40_since: datetime | None = None
    in_position: bool | None = None
    risk_blocked: bool | None = None
    risk_blocked_reason: str | None = None


class RadarPage(BaseModel):
    items: list[RadarItemOut]
    next_cursor: str | None = None
    as_of: datetime
    org_scoped: bool
    """Whether ``in_position``/``risk_blocked`` were actually evaluated for
    this response (a valid ``org_id`` was supplied and the caller is a member)
    — distinct from every item happening to read ``false``."""
