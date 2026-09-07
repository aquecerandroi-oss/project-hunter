"""The market picture one bridge submission is decided against — assembled, never guessed.

``admit`` takes ``MarketLiquidity`` from its caller on purpose: a service that
fetched the price, the volume and the beta itself would be *choosing* them
silently. So the bridge declares its sources here, and each one is either read
or reported absent:

- **price and book** — the last valid SPOT print and the eligible book of the
  hot state, through the same :class:`SpotMarketData` the entry cycle uses;
- **participation volume** — the last complete 1m candle of the **spot** market
  and the median of the last 30, from ``candles``. Incomplete window means
  ``volume_window_complete = False``, which makes the engine's participation
  reference unknown and rejects, exactly as it should: a median over a window
  with holes is a smaller denominator than the market really has;
- **continuity** — an unrecovered ``ingestion_gaps`` row is ``open_gap``
  (R-OPS-3). No row is ``ok``, and that is a claim about *the gap table*, which
  is the artefact whose whole job is to know;
- **universe membership** — ``markets.is_monitored``, written by T3.0c's spot
  refresh (R-OPS-4).

Nothing here has a default that flatters the market. Every unknown arrives at
the engine as ``None`` and the engine refuses, which is the contract's rule and
the reason a paper wallet can be believed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from sqlalchemy import text

from hunter_core.execution.tape import usable_trade
from hunter_core.logging import get_logger
from hunter_execution_worker.positions import load_open_positions
from hunter_execution_worker.reference import load_markets
from hunter_risk.inputs import BookLevel as RiskBookLevel
from hunter_risk.inputs import MarketLiquidity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.execution.tape import MarkingPolicy
    from hunter_execution_worker.bridge_universe import SpotPair
    from hunter_execution_worker.market_data import SpotMarketData, SpotSnapshot
    from hunter_execution_worker.reference import MarketReference
    from hunter_execution_worker.wallet import WalletRef

__all__ = ["WINDOW_MINUTES", "VolumeWindow", "liquidity_for", "marks_for_open_positions"]

logger = get_logger(__name__)

WINDOW_MINUTES = 30
"""Complete minutes behind the participation median (RISK_ENGINE.md v2 §4)."""

_TWO = Decimal(2)


class VolumeWindow:
    """The participation numbers of one market, and whether they are complete."""

    __slots__ = ("complete", "last_minute", "median", "volume_ts")

    def __init__(
        self,
        *,
        last_minute: Decimal | None,
        median: Decimal | None,
        complete: bool,
        volume_ts: datetime | None,
    ) -> None:
        self.last_minute = last_minute
        self.median = median
        self.complete = complete
        self.volume_ts = volume_ts


def _median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / _TWO


async def volume_window(
    session: AsyncSession, *, market_id: uuid.UUID, now: datetime
) -> VolumeWindow:
    """The last complete minute and the median of the last 30, on the spot market."""
    last_open = now.replace(second=0, microsecond=0) - timedelta(minutes=1)
    first_open = last_open - timedelta(minutes=WINDOW_MINUTES - 1)
    rows = (
        await session.execute(
            text(
                "SELECT open_time, quote_volume FROM candles WHERE market_id = :market "
                "AND timeframe = '1m' AND is_final AND open_time BETWEEN :first AND :last "
                "ORDER BY open_time DESC"
            ),
            {"market": market_id, "first": first_open, "last": last_open},
        )
    ).all()
    volumes = [row.quote_volume for row in rows]
    complete = len(rows) == WINDOW_MINUTES and all(value is not None for value in volumes)
    newest = rows[0] if rows else None
    last_minute = (
        newest.quote_volume if newest is not None and newest.open_time == last_open else None
    )
    return VolumeWindow(
        last_minute=None if last_minute is None else Decimal(str(last_minute)),
        median=(
            _median([Decimal(str(value)) for value in volumes if value is not None])
            if complete
            else None
        ),
        complete=complete,
        volume_ts=last_open + timedelta(minutes=1),
    )


async def gap_state(session: AsyncSession, *, market_id: uuid.UUID) -> Literal["ok", "open_gap"]:
    """``open_gap`` while a hole in the 1m series is unrecovered, else ``ok``."""
    found = await session.scalar(
        text(
            "SELECT 1 FROM ingestion_gaps WHERE market_id = :market AND timeframe = '1m' "
            "AND recovered_at IS NULL AND status <> 'recovered' LIMIT 1"
        ),
        {"market": market_id},
    )
    return "open_gap" if found is not None else "ok"


async def liquidity_for(
    session: AsyncSession,
    *,
    spot: SpotPair,
    market: MarketReference,
    snapshot: SpotSnapshot,
    now: datetime,
) -> MarketLiquidity | str:
    """One market's live picture, or the name of the input that is missing."""
    trade = snapshot.last_trade
    if trade is None:
        return "spot_price_unavailable"
    book = snapshot.book
    if book is None or not book.asks or not book.bids:
        return "spot_book_unavailable"
    best_bid = book.bids[0].price
    best_ask = book.asks[0].price
    volumes = await volume_window(session, market_id=spot.market_id, now=now)
    return MarketLiquidity(
        market=market.identity,
        last_price=trade.price,
        mid_price=(best_bid + best_ask) / _TWO,
        best_bid=best_bid,
        best_ask=best_ask,
        price_ts=trade.ts,
        asks=tuple(RiskBookLevel(price=level.price, qty=level.qty) for level in book.asks),
        book_ts=book.received_at,
        quote_volume_24h=spot.volume_24h_usd,
        last_minute_quote_volume=volumes.last_minute,
        median_30m_quote_volume=volumes.median,
        volume_window_complete=volumes.complete,
        volume_ts=volumes.volume_ts,
        gap_state=await gap_state(session, market_id=spot.market_id),
        in_universe=spot.is_monitored,
    )


async def marks_for_open_positions(
    session: AsyncSession,
    *,
    wallet: WalletRef,
    data: SpotMarketData,
    policy: MarkingPolicy,
    now: datetime,
) -> tuple[dict[uuid.UUID, Decimal], int]:
    """A price per open market, from the **last valid SPOT trade** and nothing else.

    A market whose tape has nothing usable is simply absent from the map, and
    the ledger then falls back to the last durable mark and flags the state
    incomplete. Marking at a price we could not validate would be the invented
    number the directive forbids. Returns the marks and how many positions were
    read, so the caller can report the second without a second query.
    """
    positions = await load_open_positions(session, wallet=wallet)
    markets = await load_markets(session, {position.market_id for position in positions})
    marks: dict[uuid.UUID, Decimal] = {}
    for market_id, market in markets.items():
        snapshot = await data.snapshot(market.identity)
        trade, _ = usable_trade(snapshot.last_trade, now=now, policy=policy)
        if trade is not None:
            marks[market_id] = trade.price
    return marks, len(positions)


def prices_with(
    marks: Mapping[uuid.UUID, Decimal], *, market_id: uuid.UUID, price: Decimal
) -> dict[uuid.UUID, Decimal]:
    """The mark map the candidate's own market is added to, without mutating it."""
    return {**marks, market_id: price}
