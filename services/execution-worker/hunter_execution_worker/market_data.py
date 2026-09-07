"""The SPOT market picture one attempt is allowed to use, behind one interface.

``docs/plans/M3.md`` (joint decision, item 3) fixes the two inputs of a
simulated fill: the **eligible book** and the **last valid SPOT trade**. Both
live in the market-worker's hot state under the spot keys
(``mkt:{exchange}:spot:{symbol}:book`` and ``:trades``,
:mod:`hunter_core.redis`). Nothing else is a fill input — a candle never
supplies a retroactive fill, and a perpetual's book is a different venue.

:class:`SpotMarketData` exists because T3.0b/T3.0c (the spot collector) were in
flight while this worker was written: the interface is what lets the worker be
finished and proved against a **labelled** snapshot source while the real
producer lands, without a single line of "if test" inside the cycles.

**``avg_price`` is not collected yet, and this module refuses to invent it.**
The ``NOTIONAL`` filter of a MARKET order is judged against the exchange's own
``avgPrice`` over ``avgPriceMins`` minutes (T3.0a §5) — never the last trade,
which moves with the very book under suspicion. There is no such key in the hot
state today, so :class:`RedisSpotMarketData` reports it absent with a reason and
the entry is refused (``avg_price_unavailable``): failing closed on a missing
input is the contract's rule, and computing our own average and calling it the
exchange's would be exactly the fabricated number the directive forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Protocol, cast

import msgpack

from hunter_core.domain.enums import MarketType, OrderSide
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_core.domain.types import ensure_utc
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_risk.inputs import MarketIdentity

__all__ = [
    "SPOT_DATA_SOURCE_VERSION",
    "RedisSpotMarketData",
    "SpotMarketData",
    "SpotSnapshot",
    "StaticSpotMarketData",
]

logger = get_logger(__name__)
_codec: Any = msgpack

SPOT_DATA_SOURCE_VERSION = "spot_hot_state_v1"
"""The reader's own version, published next to every attempt it feeds."""

TAPE_WINDOW = 50
"""How many of the newest prints one trigger evaluation reads.

The ring buffer holds 2000 (``hot_state_trades.TRADES_MAXLEN``); a trigger only
ever cares about prints inside the 10 s marking budget, and reading the whole
buffer every cycle would cost 2000 msgpack decodes per market per second.
"""


@dataclass(frozen=True, slots=True)
class SpotSnapshot:
    """One market, as one cycle saw it: a book, a tape, and what is missing."""

    market: MarketIdentity
    book: NormalizedOrderBook | None
    trades: tuple[NormalizedTrade, ...] = ()
    avg_price: Decimal | None = None
    avg_price_source: str = "unavailable"
    """Where the ``NOTIONAL`` reference came from — or why there is none."""
    tape_gap: bool = False
    source: str = SPOT_DATA_SOURCE_VERSION
    unavailable: tuple[str, ...] = field(default_factory=tuple)

    @property
    def last_trade(self) -> NormalizedTrade | None:
        """The newest print. Whether it is *usable* is the adapter's question."""
        return self.trades[-1] if self.trades else None


class SpotMarketData(Protocol):
    """Where one cycle's book and tape come from."""

    source: str

    async def snapshot(self, market: MarketIdentity) -> SpotSnapshot: ...


class StaticSpotMarketData:
    """A **test double**: the snapshots handed to it, and nothing else.

    Labelled as a double on purpose (CLAUDE.md: "mocks/fixtures live only in
    tests and are labelled"). It can return an empty book and a stale tape, which
    is what makes ``pending_degraded`` and the adverse-gap scenarios reachable —
    a double that always fills would prove nothing (spec §12, trap 4).
    """

    source = "static_fixture"

    def __init__(self, snapshots: dict[tuple[str, str], SpotSnapshot]) -> None:
        self._snapshots = snapshots

    async def snapshot(self, market: MarketIdentity) -> SpotSnapshot:
        found = self._snapshots.get((market.exchange, market.symbol))
        if found is not None:
            return found
        return SpotSnapshot(market=market, book=None, unavailable=("no_snapshot",))


def _decimal(raw: object) -> Decimal | None:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return value if value.is_finite() else None


class RedisSpotMarketData:
    """The real reader: the spot keys of the market-worker's hot state.

    ``mkt:{exchange}:spot:{symbol}:book`` is one msgpack snapshot with a TTL, and
    ``:trades`` is a newest-first list of prints. The spot book carries **no
    exchange clock** (T3.0a §4: ``ts == received_at``), which is why eligibility
    is measured on our receipt and why nothing here invents a ``sequence``: a
    fabricated sequence would defeat the very replay guard that reads it.
    """

    source = SPOT_DATA_SOURCE_VERSION

    def __init__(self, redis: redis_asyncio.Redis, *, window: int = TAPE_WINDOW) -> None:
        self._redis = redis
        self._window = window

    async def snapshot(self, market: MarketIdentity) -> SpotSnapshot:
        missing: list[str] = []
        book = await self._book(market)
        if book is None:
            missing.append("no_book")
        trades = await self._trades(market)
        if not trades:
            missing.append("no_trade")
        # The ``NOTIONAL`` reference is the exchange's ``avgPrice`` and nobody
        # collects it yet (T3.0b): absent, with the reason, never substituted.
        missing.append("avg_price")
        return SpotSnapshot(
            market=market,
            book=book,
            trades=trades,
            avg_price=None,
            avg_price_source="not_collected",
            unavailable=tuple(missing),
        )

    async def _book(self, market: MarketIdentity) -> NormalizedOrderBook | None:
        key = keys.book(market.exchange, market.symbol, MarketType.SPOT)
        raw = cast("bytes | None", await self._redis.get(key))
        if raw is None:
            return None
        try:
            payload = cast("dict[str, Any]", _codec.unpackb(raw, raw=False))
            ts = ensure_utc(datetime.fromisoformat(str(payload["ts"])))
            return NormalizedOrderBook(
                exchange=market.exchange,
                symbol=market.symbol,
                market_type=MarketType.SPOT,
                ts=ts,
                received_at=ts,
                bids=_levels(payload.get("bids", [])),
                asks=_levels(payload.get("asks", [])),
                sequence=None,
                is_snapshot=True,
            )
        except Exception:
            logger.warning("spot_book_unreadable", exchange=market.exchange, symbol=market.symbol)
            return None

    async def _trades(self, market: MarketIdentity) -> tuple[NormalizedTrade, ...]:
        key = keys.trades(market.exchange, market.symbol, MarketType.SPOT)
        rows = cast("list[bytes]", await self._redis.lrange(key, 0, self._window - 1))
        prints: list[NormalizedTrade] = []
        for raw in reversed(rows):  # the list is newest-first; the tape is not
            parsed = self._trade(market, raw)
            if parsed is not None:
                prints.append(parsed)
        return tuple(prints)

    def _trade(self, market: MarketIdentity, raw: bytes) -> NormalizedTrade | None:
        try:
            payload = cast("dict[str, Any]", _codec.unpackb(raw, raw=False))
            price, qty = _decimal(payload["price"]), _decimal(payload["qty"])
            if price is None or qty is None or price <= 0:
                return None
            ts = ensure_utc(datetime.fromisoformat(str(payload["ts"])))
            return NormalizedTrade(
                exchange=market.exchange,
                symbol=market.symbol,
                market_type=MarketType.SPOT,
                ts=ts,
                received_at=ts,
                trade_id=str(payload["trade_id"]),
                price=price,
                qty=qty,
                side=OrderSide(str(payload.get("side", OrderSide.BUY.value))),
            )
        except Exception:
            # One unreadable print never erases the rest of the tape: that is the
            # whole point of ``tape.read_batch`` (notes-T3.4.md §12, blocker 1).
            logger.warning("spot_trade_unreadable", exchange=market.exchange, symbol=market.symbol)
            return None


def _levels(raw: object) -> list[BookLevel]:
    levels: list[BookLevel] = []
    for entry in cast("list[list[str]]", raw):
        price, qty = _decimal(entry[0]), _decimal(entry[1])
        if price is None or qty is None or price <= 0 or qty < 0:
            continue
        levels.append(BookLevel(price=price, qty=qty))
    return levels
