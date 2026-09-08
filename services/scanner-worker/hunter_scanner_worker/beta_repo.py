"""The bars beta is measured on, aggregated **in the database**.

One market's thirty-day window is 43 200 one-minute candles, and the job runs
over the whole universe every closed hour. Shipping 8.6 million rows into Python
once an hour to compute 720 divisions is not an option, so the sixty minutes of
each bar are folded server-side and only the bar closes travel — 721 rows per
market instead of 43 201.

Folding in SQL means restating the contract of
:func:`hunter_indicators.beta.returns.hourly_closes` as a query, so it is
restated **literally**, clause by clause, and the arithmetic that follows is the
indicator's own (:func:`~hunter_indicators.beta.returns.returns_from_closes`):

- ``is_final`` only. The minute still printing is not evidence, which is the one
  property that makes a beta computed at 12:00:30 identical to the same beta
  recomputed from history a month later;
- ``open_time < window_end``, never ``<= now``. The bar that starts at the cut
  has not closed, so not one of its minutes may enter — including the ones that
  already exist because the collector is ahead of the job;
- **a bar is complete or it does not exist**: sixty minutes present *and* the
  newest of them sitting exactly at ``bucket + bar - 1min``. The count alone
  would be enough while ``(market_id, timeframe, open_time)`` stays the primary
  key, and the second half is cheap, so it is written down rather than inferred
  from a constraint somebody could change;
- the bucket is ``date_bin`` from the **epoch**, which is what
  :func:`~hunter_indicators.beta.returns.floor_bar` does, so a spec whose bar is
  not an hour buckets the same way on both sides.

Nothing here interprets: an empty result is a market with no usable bar, and the
estimator is what turns that into ``insufficient_history`` with a reason.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import text

from hunter_core.domain.enums import Timeframe
from hunter_indicators.beta import BetaSpec, window_bounds

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["bar_closes"]

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
"""The origin ``floor_bar`` counts bars from. A bound value, not a literal, so
the statement is a constant of this module and nothing is ever concatenated."""

_BAR_CLOSES = text(
    "WITH bars AS ("
    "  SELECT date_bin(CAST(:bar AS interval), open_time, :origin) AS bucket,"
    "         count(*) AS minutes,"
    "         max(open_time) AS last_minute,"
    "         (array_agg(close ORDER BY open_time DESC))[1] AS close"
    "    FROM candles"
    "   WHERE market_id = :market"
    "     AND timeframe = CAST(:timeframe AS candle_timeframe)"
    "     AND is_final"
    "     AND open_time >= :first_minute"
    "     AND open_time < :cut"
    "   GROUP BY 1"
    ") "
    "SELECT bucket, close FROM bars "
    " WHERE minutes = :bar_minutes"
    "   AND last_minute = bucket + CAST(:bar AS interval) - INTERVAL '1 minute' "
    " ORDER BY bucket"
)
"""Complete bars of one market inside ``[window_start - 1 bar, window_end)``."""


async def bar_closes(
    session: AsyncSession, market_id: UUID, *, as_of: datetime, spec: BetaSpec
) -> dict[datetime, Decimal]:
    """Bar start -> close, for every complete bar the window (plus its anchor) has.

    Exactly what :func:`hunter_indicators.beta.returns.hourly_closes` returns for
    the same candles, and the two are held together by
    ``test_beta_job.test_a_minute_that_is_not_final_does_not_complete_its_bar``.
    """
    start, end = window_bounds(as_of, spec)
    rows = await session.execute(
        _BAR_CLOSES,
        {
            "bar": spec.bar,
            "origin": _EPOCH,
            "market": market_id,
            "timeframe": Timeframe.M1.value,
            "first_minute": start - spec.bar,
            "cut": end,
            "bar_minutes": spec.bar_minutes,
        },
    )
    return {row.bucket: row.close for row in rows}
