"""WS ingest: hot state, tick coalescing, and stream publication.

docs/plans/M1.md T1.3 item 2 / PIPELINE.md Â§1.2-Â§1.4. Subscribes
``adapter.stream(monitored, CHANNELS)``, writes every event to Redis hot
state (``hot_state.py``) immediately, coalesces ticks per symbol every
``tick_coalesce_ms`` into one ``market.ticks`` event + ``rt:market:{ex}:{sym}``
publish, and forwards final candles / liquidations to the persist queue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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
from hunter_market_worker.coalesce import (
    BOOK_IMBALANCE_DEPTH as BOOK_IMBALANCE_DEPTH,
)
from hunter_market_worker.coalesce import (
    TickCoalescer as TickCoalescer,
)
from hunter_market_worker.coalesce import (
    build_tick_payload as build_tick_payload,
)
from hunter_market_worker.coalesce import (
    coalesce_loop as coalesce_loop,
)
from hunter_market_worker.coalesce import (
    flush_ticks as flush_ticks,
)
from hunter_market_worker.publication import liquidation_id, publish

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_core.domain.market import NormalizedEvent
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
RECONNECT_BACKOFF_S = 1.0


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
    trade_memory: hot_state.TradeMemory,
) -> bool:
    """Dispatch one normalized event to hot state, the coalescer and/or the persist queue.

    B3: ticker/book acceptance is decided purely by the in-memory
    ``accepted`` gate above — no Redis round trip either way. The actual
    hot-state write for both is deferred to the coalescer's periodic flush
    (:func:`flush_ticks`), which is why ``handle_event`` no longer awaits
    ``hot_state.write_ticker``/``write_book`` here.
    """
    if not accepted.accept(event):
        return False
    if isinstance(event, NormalizedTicker):
        coalescer.on_ticker(event)
    elif isinstance(event, NormalizedTrade):
        if not await hot_state.push_trade(redis, event, trade_memory):
            return False
        coalescer.on_trade(event)
    elif isinstance(event, NormalizedOrderBook):
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
