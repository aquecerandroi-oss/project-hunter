"""Reading the durable equity curve, for the two questions the kill switch asks.

``portfolio_equity_snapshots`` is partitioned ``LIST (resolution)``: the 1m curve
is the operational one, and the 1h/1d rows are **aggregations of it** kept for
longer (DATABASE.md §1.3). Both questions here are about a measurement at an
instant, so both pin ``resolution = '1m'``. Astra's review of this diff is why it
is spelled out: with the resolution unpinned, an hourly aggregate sharing a
timestamp with the minute row could win the ``ORDER BY ts`` and answer with a
number that describes an hour rather than a moment — and the composite primary
key allows both rows to exist.

Both also refuse a timestamp in the future. A row stamped tomorrow sorts first
and has a negative age, so every "is it fresh enough" test passes it; the only
honest reading of a point that has not happened yet is that it is not evidence.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from hunter_core.db.models.portfolios import PortfolioEquitySnapshot
from hunter_core.domain.enums import Timeframe
from hunter_core.risk.daily import EquityObservation

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["OPERATIONAL_RESOLUTION", "day_opening_observation", "latest_observation"]

OPERATIONAL_RESOLUTION = Timeframe.M1
"""The curve the wallet is actually marked on. The coarser ones are summaries."""


async def latest_observation(
    session: AsyncSession, portfolio_id: uuid.UUID, *, not_after: datetime
) -> EquityObservation | None:
    """The newest 1m point at or before ``not_after``, or ``None``."""
    row = (
        await session.execute(
            select(
                PortfolioEquitySnapshot.equity,
                PortfolioEquitySnapshot.ts,
                PortfolioEquitySnapshot.cash,
            )
            .where(
                PortfolioEquitySnapshot.portfolio_id == portfolio_id,
                PortfolioEquitySnapshot.resolution == OPERATIONAL_RESOLUTION,
                PortfolioEquitySnapshot.ts <= not_after,
            )
            .order_by(desc(PortfolioEquitySnapshot.ts))
            .limit(1)
        )
    ).one_or_none()
    if row is None:
        return None
    return EquityObservation(equity=row.equity, observed_at=row.ts, cash=row.cash)


async def day_opening_observation(
    session: AsyncSession, portfolio_id: uuid.UUID, day_start_utc: datetime
) -> EquityObservation | None:
    """The last equity observed **at or before** the São Paulo turn.

    This is what anchors the day, and the only thing that may: the equity half a
    minute *after* midnight is not the equity of midnight, however close it looks
    (:mod:`hunter_core.risk.daily`).
    """
    return await latest_observation(session, portfolio_id, not_after=day_start_utc)
