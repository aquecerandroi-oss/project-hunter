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
    """``true`` in either of two cases, both meaning "do not read this as the
    live regime":

    - the row is **closed** (``end_time`` is not ``null``) and is only being
      shown because the caller asked for "current" and nothing newer exists;
    - the row is **open** (``end_time IS NULL``) but no ``hb:scanner:*``
      heartbeat confirms a live classifier (``routers/regime.py::_scanner_alive``).
      An open row alone proves only that a classifier once started this line,
      not that anything is still watching it — a scanner that died right after
      opening it would otherwise read fresh forever.

    ``false`` therefore means "open line **and** a scanner confirmed alive"."""


class RegimeCurrentOut(BaseModel):
    items: list[RegimeOut]
    as_of: datetime


class RegimeHistoryPage(BaseModel):
    items: list[RegimeOut]
    next_cursor: str | None = None
