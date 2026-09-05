"""Set-based candle/gap reads for gap detection (HIGH-2).

Extracted out of ``recovery.py`` purely to stay under the 350-line budget —
one per-market query for the watermark, one for persisted candles and one
for existing gaps, each covering the whole monitored universe in a single
round trip instead of one query per market.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from hunter_core.db.models.market_data import Candle, IngestionGap
from hunter_core.domain.enums import Timeframe


async def persisted(session: Any, market_id: Any, start: datetime, end: datetime) -> set[datetime]:
    """Persisted final open times for one gap's own coverage check."""
    return set(
        await session.scalars(
            select(Candle.open_time).where(
                Candle.market_id == market_id,
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
                Candle.open_time >= start,
                Candle.open_time <= end,
            )
        )
    )


async def watermarks(session: Any, market_ids: list[Any]) -> dict[Any, datetime | None]:
    """One query for the whole universe instead of one per market."""
    result: dict[Any, datetime | None] = dict.fromkeys(market_ids)
    if not market_ids:
        return result
    rows = (
        await session.execute(
            select(Candle.market_id, func.max(Candle.open_time))
            .where(
                Candle.market_id.in_(market_ids),
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
            )
            .group_by(Candle.market_id)
        )
    ).all()
    result.update({row[0]: row[1] for row in rows})
    return result


async def persisted_by_market(
    session: Any, market_ids: list[Any], start: datetime, end: datetime
) -> dict[Any, set[datetime]]:
    """Persisted open times of every monitored market in the widest window
    needed, one query, grouped in Python."""
    result: dict[Any, set[datetime]] = {mid: set() for mid in market_ids}
    if not market_ids:
        return result
    rows = (
        await session.execute(
            select(Candle.market_id, Candle.open_time).where(
                Candle.market_id.in_(market_ids),
                Candle.timeframe == Timeframe.M1,
                Candle.is_final.is_(True),
                Candle.open_time >= start,
                Candle.open_time <= end,
            )
        )
    ).all()
    for market_id, open_time in rows:
        result[market_id].add(open_time)
    return result


async def gaps_by_market(
    session: Any, market_ids: list[Any], statuses: tuple[str, ...]
) -> dict[Any, list[IngestionGap]]:
    """Every open/failed gap of the monitored universe, one query."""
    result: dict[Any, list[IngestionGap]] = {mid: [] for mid in market_ids}
    if not market_ids:
        return result
    rows = (
        await session.scalars(
            select(IngestionGap).where(
                IngestionGap.market_id.in_(market_ids), IngestionGap.status.in_(statuses)
            )
        )
    ).all()
    for gap in rows:
        result[gap.market_id].append(gap)
    return result


async def count_by_status(session: Any, market_ids: list[Any], status: str) -> int:
    if not market_ids:
        return 0
    return (
        await session.scalar(
            select(func.count())
            .select_from(IngestionGap)
            .where(IngestionGap.market_id.in_(market_ids), IngestionGap.status == status)
        )
        or 0
    )
