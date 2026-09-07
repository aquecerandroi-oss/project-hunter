"""``symbol -> markets.id`` for one venue and one market type.

Split out of :mod:`.persist_rows` (T3.0b, 350-line budget) because it stopped
being a detail of the upserts the moment it had to discriminate: ``markets``
is unique on ``(exchange_id, symbol, market_type)``, so a lookup keyed by
symbol alone silently keeps whichever of the two rows the scan returned last
— and every ``upsert_*`` in ``persist_rows`` would then write the perpetual's
candle onto the spot pair's ``market_id``, or the reverse. Nothing detects
that afterwards: both rows are valid.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import MarketType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["load_market_ids"]


async def load_market_ids(
    session: AsyncSession,
    exchange_code: str,
    symbols: set[str],
    market_type: MarketType = MarketType.PERPETUAL,
) -> dict[str, Any]:
    """``{symbol: market_id}`` for ``symbols`` on ``exchange_code``.

    ``PERPETUAL`` by default: every caller today collects USDS-M perpetuals,
    and the query it produces returns exactly what it returned before the
    ``market_type`` predicate existed (there are no spot rows yet).
    """
    if not symbols:
        return {}
    rows = (
        await session.execute(
            select(Market.id, Market.symbol)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == exchange_code)
            .where(Market.symbol.in_(symbols))
            .where(Market.market_type == market_type)
        )
    ).all()
    return {row.symbol: row.id for row in rows}
