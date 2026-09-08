"""Which markets a backfill request names — shared by every kind
``request_backfill.py`` publishes (``candles``, ``funding``).

Split out for the 350-line budget (the same reason ``create_partitions.py``
moved its planning to ``partition_plan.py``); imported by
``request_backfill.py``, never the reverse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["REFERENCE_SYMBOL", "Target", "targets_for"]

REFERENCE_SYMBOL = "BTCUSDT"

_SPOT_TWINS = text(
    "SELECT p.id AS market_id, p.symbol AS symbol FROM markets p "
    "JOIN exchanges e ON e.id = p.exchange_id "
    "JOIN markets s ON s.exchange_id = p.exchange_id AND s.market_type = 'spot' "
    "  AND s.base_asset_id = p.base_asset_id AND s.quote_asset_id = p.quote_asset_id "
    "  AND s.status = 'active' AND s.delisted_at IS NULL "
    "WHERE e.code = :exchange AND p.market_type = 'perpetual' AND p.is_monitored "
    "ORDER BY p.symbol"
)
"""The perpetuals the wallet can actually execute (D1: beta on the perpetual, the
wallet executes the spot twin of the same venue and ``base/quote``)."""

_BY_SYMBOL = text(
    "SELECT p.id AS market_id, p.symbol AS symbol FROM markets p "
    "JOIN exchanges e ON e.id = p.exchange_id "
    "WHERE e.code = :exchange AND p.market_type = 'perpetual' "
    "AND p.symbol = ANY(:symbols) ORDER BY p.symbol"
)


@dataclass(frozen=True, slots=True)
class Target:
    market_id: UUID
    symbol: str


async def targets_for(
    session: AsyncSession, exchange: str, symbols: Sequence[str] | None
) -> list[Target]:
    """The markets to ask for: the named ones, or every perpetual with a spot twin.

    The reference market is always included when the list is derived, because a
    beta with no reference series is ``btc_missing`` for the whole universe —
    backfilling everything *but* the BTC would leave every row invalid. A named
    ``--markets`` list (funding included) is used exactly as given.
    """
    if symbols:
        rows = await session.execute(_BY_SYMBOL, {"exchange": exchange, "symbols": list(symbols)})
    else:
        rows = await session.execute(_SPOT_TWINS, {"exchange": exchange})
    found = [Target(market_id=row.market_id, symbol=row.symbol) for row in rows]
    if symbols or any(target.symbol == REFERENCE_SYMBOL for target in found):
        return found
    reference = await session.execute(
        _BY_SYMBOL, {"exchange": exchange, "symbols": [REFERENCE_SYMBOL]}
    )
    return sorted(
        [*found, *(Target(market_id=row.market_id, symbol=row.symbol) for row in reference)],
        key=lambda target: target.symbol,
    )
