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

**``avg_price`` is the exchange's own, or it is absent — never ours.** The
``NOTIONAL`` filter of a MARKET order is judged against the exchange's
``avgPrice`` over ``avgPriceMins`` minutes (T3.0a §5) — never the last trade,
which moves with the very book under suspicion. There is no such key in the hot
state (the spot collector publishes none), so since T3.29
:class:`RedisSpotMarketData` takes an optional
:class:`~hunter_execution_worker.avg_price.AvgPriceReader` that asks the exchange
itself (``GET /api/v3/avgPrice``, cached and bounded — that module says why that
endpoint and not a ``fapi`` one). Without a reader, or when the reader has
nothing honest to report, the value stays absent **with its reason** and the
entry is deferred: failing closed on a missing input is the contract's rule, and
computing our own average and calling it the exchange's would be exactly the
fabricated number the directive forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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

    from hunter_execution_worker.avg_price import AvgPriceQuote, AvgPriceReader
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
    avg_price_ts: datetime | None = None
    """**When we received** that reference. Every input carries a stamp
    (RISK_ENGINE.md §7, R-OPS-2), and this one is what
    :func:`hunter_execution_worker.entry_inputs.missing_inputs` measures the
    entry's own age bound against — a price with no stamp is not a reference."""
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

    def __init__(
        self,
        snapshots: dict[tuple[str, str], SpotSnapshot],
        *,
        stamp_avg_price: bool = True,
    ) -> None:
        self._snapshots = snapshots
        self._stamp_avg_price = stamp_avg_price
        """Whether an undated ``avg_price`` gets the picture's own instant.

        ``True`` is the fixture's convenience (see :func:`_dated`). ``False`` is
        the **opt-out** a test asks for when the absence of a stamp *is* the
        scenario: without it ``avg_price_undated`` (RISK_ENGINE.md §7 — a price
        with no age is not a reference) was unreachable through this double, so
        the rule could only be exercised against a hand-built snapshot and never
        end to end (T3.29b, finding 4)."""

    async def snapshot(self, market: MarketIdentity) -> SpotSnapshot:
        found = self._snapshots.get((market.exchange, market.symbol))
        if found is not None:
            return _dated(found) if self._stamp_avg_price else found
        return SpotSnapshot(market=market, book=None, unavailable=("no_snapshot",))


def _dated(snapshot: SpotSnapshot) -> SpotSnapshot:
    """A double's reference is as old as the picture it came with.

    ``avg_price_ts`` is what :func:`hunter_execution_worker.entry_inputs
    .stale_average` bounds the entry against, and a price with no stamp is
    refused (``avg_price_undated``) — the real reader always stamps. A fixture
    that hands one snapshot means one instant, so the double declares that
    instant to be the book's own receipt (else the newest print). A test that
    wants a **stale** reference says so by setting ``avg_price_ts`` itself: this
    only ever fills an absence, it never overwrites a stamp. A test that wants no
    stamp at all builds the double with ``stamp_avg_price=False``, which is the
    only way ``avg_price_undated`` is reachable through a fixture (T3.29b).
    """
    if snapshot.avg_price is None or snapshot.avg_price_ts is not None:
        return snapshot
    observed = snapshot.book.received_at if snapshot.book is not None else None
    if observed is None and snapshot.last_trade is not None:
        observed = snapshot.last_trade.ts
    if observed is None:
        return snapshot
    return replace(snapshot, avg_price_ts=observed)


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

    def __init__(
        self,
        redis: redis_asyncio.Redis,
        *,
        window: int = TAPE_WINDOW,
        avg_price: AvgPriceReader | None = None,
    ) -> None:
        self._redis = redis
        self._window = window
        self._avg_price = avg_price
        """The ``NOTIONAL`` reference reader, or ``None`` — in which case every
        market whose MARKET filter needs an average defers by name
        (``avg_price_not_collected``), exactly as it did before T3.29."""

    async def snapshot(self, market: MarketIdentity) -> SpotSnapshot:
        missing: list[str] = []
        book, book_unread = await self._book(market)
        if book is None:
            missing.append("no_book")
        trades, tape_unread = await self._trades(market)
        if not trades:
            missing.append("no_trade")
        if book_unread or tape_unread:
            # V6 step 4: Redis went away *during* the decision. The picture is
            # not "empty", it is "unread", and the difference has to survive
            # into the snapshot — but the answer is the same, and it is the safe
            # one: the entry defers, the protection stays degraded, nothing is
            # written and no absence ever produces a fill.
            missing.append("hot_state_unreachable")
        # The ``NOTIONAL`` reference is the exchange's own ``avgPrice``. With no
        # reader wired there is nothing to report; with one, a failed or expired
        # quote is still nothing — never the last trade wearing its name.
        quote = None if self._avg_price is None else await self._avg_price.read(market)
        if quote is None:
            missing.append("avg_price")
        return SpotSnapshot(
            market=market,
            book=book,
            trades=trades,
            avg_price=None if quote is None else quote.price,
            avg_price_source=self._avg_price_source(quote),
            avg_price_ts=None if quote is None else quote.observed_at,
            unavailable=tuple(missing),
        )

    def _avg_price_source(self, quote: AvgPriceQuote | None) -> str:
        if quote is not None:
            return quote.source
        return "not_collected" if self._avg_price is None else "unavailable"

    async def _book(self, market: MarketIdentity) -> tuple[NormalizedOrderBook | None, bool]:
        """The book, and whether Redis itself could not be read."""
        key = keys.book(market.exchange, market.symbol, MarketType.SPOT)
        try:
            raw = cast("bytes | None", await self._redis.get(key))
        except Exception as exc:
            # A Redis outage is **not** a fatal cycle. Raising here aborted the
            # whole pass — every other wallet's protection included — over one
            # unreachable key; RISK_ENGINE.md's rule 3 ("entry latches may not
            # stop protective exits") is why that is not acceptable.
            logger.warning("spot_hot_state_unreachable", key=key, error=str(exc))
            return None, True
        if raw is None:
            return None, False
        try:
            payload = cast("dict[str, Any]", _codec.unpackb(raw, raw=False))
            ts = ensure_utc(datetime.fromisoformat(str(payload["ts"])))
            return (
                NormalizedOrderBook(
                    exchange=market.exchange,
                    symbol=market.symbol,
                    market_type=MarketType.SPOT,
                    ts=ts,
                    received_at=ts,
                    bids=_levels(payload.get("bids", [])),
                    asks=_levels(payload.get("asks", [])),
                    sequence=None,
                    is_snapshot=True,
                ),
                False,
            )
        except Exception:
            logger.warning("spot_book_unreadable", exchange=market.exchange, symbol=market.symbol)
            return None, False

    async def _trades(self, market: MarketIdentity) -> tuple[tuple[NormalizedTrade, ...], bool]:
        """The tape, and whether Redis itself could not be read."""
        key = keys.trades(market.exchange, market.symbol, MarketType.SPOT)
        try:
            rows = cast("list[bytes]", await self._redis.lrange(key, 0, self._window - 1))
        except Exception as exc:
            logger.warning("spot_hot_state_unreachable", key=key, error=str(exc))
            return (), True
        prints: list[NormalizedTrade] = []
        for raw in reversed(rows):  # the list is newest-first; the tape is not
            parsed = self._trade(market, raw)
            if parsed is not None:
                prints.append(parsed)
        return tuple(prints), False

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
