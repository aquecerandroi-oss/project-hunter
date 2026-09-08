"""The series the hourly regime is measured on, aggregated **in the database**.

Same contract as ``beta_repo.bar_closes`` and, deliberately, the same clauses
written out again rather than a shared helper with two callers and three
parameters: what makes an hour exist is a *rule*, and a rule that is stated once
per query is a rule a reviewer can check against the query that used it.

- ``is_final`` only. The minute still printing is not evidence — the one property
  that makes a snapshot computed at 12:00:30 identical to the same snapshot
  recomputed from history a month later;
- ``open_time < cut``, never ``<= now``: the hour that starts at the cut has not
  closed, so none of its minutes may enter, including the ones that already exist
  because the collector is ahead of the job;
- **an hour is complete or it does not exist**: sixty final minutes present *and*
  the newest of them exactly at ``bucket + 59 min``. A 47-minute hour is a hole,
  not a cheap sample;
- the bucket is ``date_bin`` from the epoch, so the hours line up with the ones
  ``floor_hour`` produces on the Python side.

Nothing here interprets: an empty result is a market with no usable hour, and
``hunter_indicators.regime.hourly`` is what turns that into ``trend_warmup`` or
into a market excluded from the breadth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import bindparam, text

from hunter_core.domain.enums import Timeframe

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["MARKET_BATCH", "funding_settlements", "hourly_closes"]

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
"""The origin the hour buckets are counted from. A bound value, never a literal
concatenated into the statement."""

MARKET_BATCH = 25
"""Markets per query. Two hundred markets of a month of minutes in one hash
aggregate is one plan the planner has to get right; twenty-five at a time is
eight plans it cannot get wrong, and the job is not latency-bound."""

_HOURLY_CLOSES = text(
    "WITH bars AS ("
    "  SELECT market_id,"
    "         date_bin(INTERVAL '1 hour', open_time, :origin) AS bucket,"
    "         count(*) AS minutes,"
    "         max(open_time) AS last_minute,"
    "         (array_agg(close ORDER BY open_time DESC))[1] AS close"
    "    FROM candles"
    "   WHERE market_id IN :markets"
    "     AND timeframe = CAST(:timeframe AS candle_timeframe)"
    "     AND is_final"
    "     AND open_time >= :first_minute"
    "     AND open_time < :cut"
    "   GROUP BY 1, 2"
    ") "
    "SELECT market_id, bucket, close FROM bars "
    " WHERE minutes = 60"
    "   AND last_minute = bucket + INTERVAL '59 minutes' "
    " ORDER BY market_id, bucket"
).bindparams(bindparam("markets", expanding=True))
"""Complete hours of each market inside ``[first_minute, cut)``."""

_FUNDING = text(
    "SELECT market_id, funding_time, rate FROM funding_rates "
    " WHERE market_id IN :markets AND funding_time > :start AND funding_time <= :cut "
    " ORDER BY market_id, funding_time"
).bindparams(bindparam("markets", expanding=True))
"""Every settlement of the window. Small enough to resolve in Python: a month of
the universe is a few thousand rows, and the per-hour "latest settlement of each
market" is a bisect, not eight hundred correlated subqueries."""


async def hourly_closes(
    session: AsyncSession,
    market_ids: Sequence[UUID],
    *,
    start: datetime,
    cut: datetime,
) -> dict[UUID, dict[datetime, Decimal]]:
    """``market -> {hour start: close}`` for every complete hour in the window."""
    out: dict[UUID, dict[datetime, Decimal]] = {market_id: {} for market_id in market_ids}
    for index in range(0, len(market_ids), MARKET_BATCH):
        batch = list(market_ids[index : index + MARKET_BATCH])
        if not batch:  # pragma: no cover - range() cannot produce an empty slice
            continue
        rows = await session.execute(
            _HOURLY_CLOSES,
            {
                "origin": _EPOCH,
                "markets": batch,
                "timeframe": Timeframe.M1.value,
                "first_minute": start,
                "cut": cut,
            },
        )
        for row in rows:
            out[row.market_id][row.bucket] = row.close
    return out


async def funding_settlements(
    session: AsyncSession,
    market_ids: Sequence[UUID],
    *,
    start: datetime,
    cut: datetime,
) -> dict[UUID, list[tuple[datetime, Decimal]]]:
    """``market -> [(settlement time, rate)]``, oldest first, inside the window."""
    out: dict[UUID, list[tuple[datetime, Decimal]]] = {market_id: [] for market_id in market_ids}
    for index in range(0, len(market_ids), MARKET_BATCH):
        batch = list(market_ids[index : index + MARKET_BATCH])
        if not batch:  # pragma: no cover
            continue
        rows = await session.execute(_FUNDING, {"markets": batch, "start": start, "cut": cut})
        for row in rows:
            out[row.market_id].append((row.funding_time, row.rate))
    return out
