"""Tick coalescing: per-symbol accumulation flushed on a fixed interval.

docs/plans/M1.md T1.3 / PIPELINE.md §1.3. Every accepted ticker/trade/book
event lands in a :class:`TickCoalescer`; every ``tick_coalesce_ms`` the loop
flushes each dirty symbol as one ``market.ticks`` event, one ``rt:market:*``
publish and (T1.6b-B3) the pending ticker/book hot-state writes, all in a
single Redis pipeline. Split out of ``ingest.py`` for the 350-line budget.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.domain.market import NormalizedOrderBook, NormalizedTicker, NormalizedTrade
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_market_worker import hot_state
from hunter_market_worker.publication import publish

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_core.settings import Settings

logger = get_logger(__name__)

BOOK_IMBALANCE_DEPTH = 5


def _max_ts(current: datetime | None, candidate: datetime) -> datetime:
    return candidate if current is None or candidate > current else current


@dataclasses.dataclass
class _TickAccum:
    price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume_delta: Decimal = Decimal(0)
    trades_count: int = 0
    book_imbalance_5: Decimal | None = None
    dirty: bool = False
    # B5: kept as ``datetime`` and formatted to ISO only at flush time — the
    # old code ran ``datetime.fromisoformat`` twice per event just to
    # ``max()`` over ISO strings (t16b-profile.md: ingest.py:92-93,102-103,
    # 110-111).
    ts: datetime | None = None
    # H10: price_ts/book_ts track the timestamp of the event kind that owns
    # each value, so a book-only update cannot republish a frozen price under
    # a fresh ``ts`` — the UI can tell a stale price from a live one.
    price_ts: datetime | None = None
    book_ts: datetime | None = None
    # B3: the latest accepted ticker/book snapshot pending a hot-state write
    # in the next flush cycle — cleared once queued. A book from ``@depth20``
    # is a full snapshot, so only the newest one per cycle needs to be kept.
    hot_ticker: NormalizedTicker | None = None
    hot_book: NormalizedOrderBook | None = None


class TickCoalescer:
    """Per-(exchange, symbol) tick accumulator, flushed on a fixed interval."""

    def __init__(self) -> None:
        self._state: dict[tuple[str, str], _TickAccum] = {}

    def _get(self, exchange: str, symbol: str) -> _TickAccum:
        return self._state.setdefault((exchange, symbol), _TickAccum())

    def on_ticker(self, ticker: NormalizedTicker) -> None:
        accum = self._get(ticker.exchange, ticker.symbol)
        accum.price = ticker.last
        accum.bid = ticker.bid
        accum.ask = ticker.ask
        accum.dirty = True
        accum.price_ts = _max_ts(accum.price_ts, ticker.ts)
        accum.ts = _max_ts(accum.ts, ticker.ts)
        accum.hot_ticker = ticker

    def on_trade(self, trade: NormalizedTrade) -> None:
        accum = self._get(trade.exchange, trade.symbol)
        accum.price = trade.price
        accum.volume_delta += trade.qty
        accum.trades_count += 1
        accum.dirty = True
        accum.price_ts = _max_ts(accum.price_ts, trade.ts)
        accum.ts = _max_ts(accum.ts, trade.ts)

    def on_book(self, book: NormalizedOrderBook) -> None:
        accum = self._get(book.exchange, book.symbol)
        accum.book_imbalance_5 = book.imbalance(BOOK_IMBALANCE_DEPTH)
        accum.dirty = True
        accum.book_ts = _max_ts(accum.book_ts, book.ts)
        accum.ts = _max_ts(accum.ts, book.ts)
        accum.hot_book = book

    def dirty_items(self) -> list[tuple[tuple[str, str], _TickAccum]]:
        return [(key, accum) for key, accum in self._state.items() if accum.dirty]

    def reset(self, key: tuple[str, str]) -> None:
        accum = self._state[key]
        accum.volume_delta = Decimal(0)
        accum.trades_count = 0
        accum.dirty = False


def build_tick_payload(exchange: str, symbol: str, accum: _TickAccum, ts: str) -> dict[str, Any]:
    """Pure builder for the ``market.ticks`` / ``rt:market:*`` payload â€” no IO,
    so coalescing can be unit-tested without Redis."""
    return {
        "exchange": exchange,
        "symbol": symbol,
        "price": str(accum.price) if accum.price is not None else None,
        "bid": str(accum.bid) if accum.bid is not None else None,
        "ask": str(accum.ask) if accum.ask is not None else None,
        "volume_delta": str(accum.volume_delta),
        "trades_count": accum.trades_count,
        "book_imbalance_5": (
            str(accum.book_imbalance_5) if accum.book_imbalance_5 is not None else None
        ),
        "ts": ts,
        "price_ts": accum.price_ts.isoformat() if accum.price_ts else None,
        "book_ts": accum.book_ts.isoformat() if accum.book_ts else None,
    }


async def flush_ticks(
    coalescer: TickCoalescer, redis: redis_asyncio.Redis, producer: str
) -> list[str]:
    """Flush every dirty symbol once per cycle (B3): one shared
    ``redis.pipeline(transaction=False)`` carries every symbol's ticker
    hot-state write (the B2 Lua script), book snapshot ``SET``, ``market.ticks``
    ``XADD`` and ``rt:market:*`` ``PUBLISH`` — a single ``pipe.execute()``
    for the whole cycle instead of per-symbol round trips.

    Trades and final candles are *not* here: a trade is not a snapshot (each
    one must survive, never coalesced) and a final candle must never wait on
    this cycle, so both keep their fully immediate, per-event path in
    :func:`handle_event`.
    """
    items = coalescer.dirty_items()
    if not items:
        return []
    sha = await hot_state.ensure_script_sha(redis)
    published: list[str] = []
    async with redis.pipeline(transaction=False) as pipe:
        for (exchange, symbol), accum in items:
            ts = accum.ts.isoformat() if accum.ts else utcnow().isoformat()
            payload = build_tick_payload(exchange, symbol, accum, ts)
            coalescer.reset((exchange, symbol))
            if accum.hot_ticker is not None:
                # KB-0044: this ticker always comes from the WS bookTicker
                # stream (on_ticker) -- must own only its own fields, never
                # the REST 24h-ticker refresh's.
                hot_state.queue_ticker_hash(pipe, sha, accum.hot_ticker, source="ws")
                accum.hot_ticker = None
            if accum.hot_book is not None:
                hot_state.queue_book_set(pipe, accum.hot_book)
                accum.hot_book = None
            envelope = EventEnvelope(
                type=Streams.MARKET_TICKS,
                producer=producer,
                key=f"{exchange}:{symbol}",
                payload=payload,
            )
            await publish(
                pipe, Streams.MARKET_TICKS, envelope, DEFAULT_MAXLEN[Streams.MARKET_TICKS]
            )
            cast(Any, pipe).publish(f"rt:market:{exchange}:{symbol}", orjson.dumps(payload))
            published.append(symbol)
        await pipe.execute()
    return published


async def coalesce_loop(
    coalescer: TickCoalescer, redis: redis_asyncio.Redis, settings: Settings, producer: str
) -> None:
    interval = settings.tick_coalesce_ms / 1000
    try:
        while True:
            await asyncio.sleep(interval)
            await flush_ticks(coalescer, redis, producer)
    finally:
        # B3: a shutdown/cancellation must not silently drop a ticker/book
        # snapshot sitting in the coalescer waiting for the next tick.
        # ``shield`` so a second cancellation racing this cleanup does not
        # cut the flush off mid-pipeline; a failure here is logged, not
        # fatal — hot state is allowed to be lost (ARCHITECTURE.md §5.3).
        try:
            await asyncio.shield(flush_ticks(coalescer, redis, producer))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("market_coalesce_shutdown_flush_failed", exc_info=True)
