"""WS ingest: hot state, tick coalescing, and stream publication.

docs/plans/M1.md T1.3 item 2 / PIPELINE.md Â§1.2-Â§1.4. Subscribes
``adapter.stream(monitored, CHANNELS)``, writes every event to Redis hot
state (``hot_state.py``) immediately, coalesces ticks per symbol every
``tick_coalesce_ms`` into one ``market.ticks`` event + ``rt:market:{ex}:{sym}``
publish, and forwards final candles / liquidations to the persist queue.
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedFunding,
    NormalizedLiquidation,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
    to_wire,
)
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.streams import DEFAULT_MAXLEN, Streams
from hunter_core.logging import get_logger
from hunter_exchanges.base import StreamChannel
from hunter_market_worker import hot_state
from hunter_market_worker.publication import liquidation_id, publish

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_core.domain.market import NormalizedEvent
    from hunter_core.settings import Settings
    from hunter_market_worker.persist import PersistQueues

logger = get_logger(__name__)

CHANNELS = (
    StreamChannel.TRADES,
    StreamChannel.BOOK_TICKER,
    StreamChannel.BOOK,
    StreamChannel.KLINE_1M,
    StreamChannel.MARK_PRICE,
    StreamChannel.LIQUIDATIONS,
)
BOOK_IMBALANCE_DEPTH = 5
RECONNECT_BACKOFF_S = 1.0


@dataclasses.dataclass
class _TickAccum:
    price: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    volume_delta: Decimal = Decimal(0)
    trades_count: int = 0
    book_imbalance_5: Decimal | None = None
    dirty: bool = False
    ts: str = ""
    # H10: price_ts/book_ts track the timestamp of the event kind that owns
    # each value, so a book-only update cannot republish a frozen price under
    # a fresh ``ts`` — the UI can tell a stale price from a live one.
    price_ts: str = ""
    book_ts: str = ""


class TickCoalescer:
    """Per-(exchange, symbol) tick accumulator, flushed on a fixed interval."""

    def __init__(self) -> None:
        self._state: dict[tuple[str, str], _TickAccum] = {}

    def _get(self, exchange: str, symbol: str) -> _TickAccum:
        return self._state.setdefault((exchange, symbol), _TickAccum())

    def on_ticker(self, ticker: NormalizedTicker) -> None:
        accum = self._get(ticker.exchange, ticker.symbol)
        event_ts = ticker.ts.isoformat()
        accum.price = ticker.last
        accum.bid = ticker.bid
        accum.ask = ticker.ask
        accum.dirty = True
        accum.price_ts = max(filter(None, [accum.price_ts, event_ts]), key=datetime.fromisoformat)
        accum.ts = max(filter(None, [accum.ts, event_ts]), key=datetime.fromisoformat)

    def on_trade(self, trade: NormalizedTrade) -> None:
        accum = self._get(trade.exchange, trade.symbol)
        event_ts = trade.ts.isoformat()
        accum.price = trade.price
        accum.volume_delta += trade.qty
        accum.trades_count += 1
        accum.dirty = True
        accum.price_ts = max(filter(None, [accum.price_ts, event_ts]), key=datetime.fromisoformat)
        accum.ts = max(filter(None, [accum.ts, event_ts]), key=datetime.fromisoformat)

    def on_book(self, book: NormalizedOrderBook) -> None:
        accum = self._get(book.exchange, book.symbol)
        event_ts = book.ts.isoformat()
        accum.book_imbalance_5 = book.imbalance(BOOK_IMBALANCE_DEPTH)
        accum.dirty = True
        accum.book_ts = max(filter(None, [accum.book_ts, event_ts]), key=datetime.fromisoformat)
        accum.ts = max(filter(None, [accum.ts, event_ts]), key=datetime.fromisoformat)

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
        "price_ts": accum.price_ts or None,
        "book_ts": accum.book_ts or None,
    }


async def flush_ticks(
    coalescer: TickCoalescer, redis: redis_asyncio.Redis, producer: str
) -> list[str]:
    """Publish one ``market.ticks`` event (stream + pub/sub) per dirty symbol."""
    published: list[str] = []
    for (exchange, symbol), accum in coalescer.dirty_items():
        payload = build_tick_payload(exchange, symbol, accum, accum.ts)
        coalescer.reset((exchange, symbol))
        envelope = EventEnvelope(
            type=Streams.MARKET_TICKS,
            producer=producer,
            key=f"{exchange}:{symbol}",
            payload=payload,
        )
        await publish(redis, Streams.MARKET_TICKS, envelope, DEFAULT_MAXLEN[Streams.MARKET_TICKS])
        await cast(Any, redis).publish(f"rt:market:{exchange}:{symbol}", orjson.dumps(payload))
        published.append(symbol)
    return published


async def coalesce_loop(
    coalescer: TickCoalescer, redis: redis_asyncio.Redis, settings: Settings, producer: str
) -> None:
    interval = settings.tick_coalesce_ms / 1000
    while True:
        await asyncio.sleep(interval)
        await flush_ticks(coalescer, redis, producer)


class AcceptedEvents:
    """Keep component watermarks across hot-key expiry for this ingest lifetime."""

    def __init__(self) -> None:
        self.latest: dict[tuple[str, str, str], Any] = {}
        self.missing_candle_ts_reported = False

    def accept(self, event: NormalizedEvent) -> bool:
        if isinstance(event, (NormalizedCandle, NormalizedLiquidation, NormalizedTrade)):
            return True
        key = (event.exchange, event.symbol, event.kind)
        previous = self.latest.get(key)
        if previous is not None and event.ts <= previous:
            return False
        self.latest[key] = event.ts
        return True


async def publish_derivatives(
    redis: redis_asyncio.Redis,
    producer: str,
    exchange: str,
    symbol: str,
    *,
    funding: NormalizedFunding | None,
    oi: NormalizedOpenInterest | None,
) -> None:
    source_ts = funding.ts if funding is not None else oi.ts if oi is not None else utcnow()
    payload = {
        "exchange": exchange,
        "symbol": symbol,
        "open_interest": str(oi.open_interest) if oi else None,
        "open_interest_value": str(oi.open_interest_value)
        if oi and oi.open_interest_value is not None
        else None,
        "funding_rate": str(funding.funding_rate) if funding else None,
        "next_funding_time": (
            funding.next_funding_time.isoformat() if funding and funding.next_funding_time else None
        ),
        "mark_price": str(funding.mark_price) if funding else None,
        "index_price": str(funding.index_price)
        if funding and funding.index_price is not None
        else None,
        "ts": source_ts.isoformat(),
    }
    envelope = EventEnvelope(
        type=Streams.MARKET_DERIVATIVES,
        producer=producer,
        key=f"{exchange}:{symbol}",
        payload=payload,
    )
    await publish(
        redis, Streams.MARKET_DERIVATIVES, envelope, DEFAULT_MAXLEN[Streams.MARKET_DERIVATIVES]
    )


async def _publish_candle_closed(
    redis: redis_asyncio.Redis, producer: str, candle: NormalizedCandle
) -> None:
    envelope = EventEnvelope(
        type=Streams.MARKET_CANDLES_CLOSED,
        producer=producer,
        key=f"{candle.exchange}:{candle.symbol}",
        payload=to_wire(candle),
    )
    await publish(
        redis,
        Streams.MARKET_CANDLES_CLOSED,
        envelope,
        DEFAULT_MAXLEN[Streams.MARKET_CANDLES_CLOSED],
    )


async def publish_liquidation(
    redis: redis_asyncio.Redis, producer: str, liq: NormalizedLiquidation
) -> None:
    envelope = EventEnvelope(
        event_id=liquidation_id(liq),
        type=Streams.MARKET_LIQUIDATIONS,
        producer=producer,
        key=f"{liq.exchange}:{liq.symbol}",
        payload=to_wire(liq),
    )
    await publish(
        redis, Streams.MARKET_LIQUIDATIONS, envelope, DEFAULT_MAXLEN[Streams.MARKET_LIQUIDATIONS]
    )


def _enqueue(queues: PersistQueues, item: Any) -> None:
    # BoundedEvents.put_nowait never raises on capacity: it drops the item
    # with a "capacity"/"age" reason internally (queues.py) instead.
    queues.events.put_nowait(item)


async def handle_event(
    event: NormalizedEvent,
    redis: redis_asyncio.Redis,
    producer: str,
    queues: PersistQueues,
    coalescer: TickCoalescer,
    accepted: AcceptedEvents,
) -> bool:
    """Dispatch one normalized event to hot state, the coalescer and/or the persist queue."""
    if not accepted.accept(event):
        return False
    if isinstance(event, NormalizedTicker):
        if not await hot_state.write_ticker(redis, event):
            return False
        coalescer.on_ticker(event)
    elif isinstance(event, NormalizedTrade):
        if not await hot_state.push_trade(redis, event):
            return False
        coalescer.on_trade(event)
    elif isinstance(event, NormalizedOrderBook):
        if not await hot_state.write_book(redis, event, depth=20):
            return False
        coalescer.on_book(event)
    elif isinstance(event, NormalizedCandle):
        if (
            not event.is_final
            and event.event_ts is None
            and not accepted.missing_candle_ts_reported
        ):
            logger.error("market_candle_source_ts_missing", exchange=event.exchange)
            accepted.missing_candle_ts_reported = True
        if not await hot_state.push_candle(redis, event, event_ts=event.event_ts):
            return False
        if event.is_final:
            _enqueue(queues, event)
            await _publish_candle_closed(redis, producer, event)
    elif isinstance(event, NormalizedFunding):
        if not await hot_state.write_funding(redis, event):
            return False
        await publish_derivatives(
            redis, producer, event.exchange, event.symbol, funding=event, oi=None
        )
    elif isinstance(event, NormalizedOpenInterest):
        if not await hot_state.write_open_interest(redis, event):
            return False
        _enqueue(queues, event)
        await publish_derivatives(
            redis, producer, event.exchange, event.symbol, funding=None, oi=event
        )
    else:
        _enqueue(queues, event)
        # Liquidations publish only after the persistence transaction commits.

    return True


__all__ = ["coalesce_loop", "publish_liquidation", "publish_derivatives"]
