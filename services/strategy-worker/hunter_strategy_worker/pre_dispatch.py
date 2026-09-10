"""Refusals before ``BarDispatcher`` ever sees a bar.

Two doors share this shape -- ack without evaluating, count by name, never
touch ``handle_candle``, the dispatcher's semaphore or a per-market lock:

- **shard ownership** (T3.74f): a bar for a symbol this shard does not own
  (:func:`hunter_strategy_worker.shard.owns_market`), counted
  ``hunter_shadow_bars_skipped_total{reason="not_my_shard"}``;
- **the shadow universe** (T3.82): a perpetual bar for a market without
  ``SHADOW_UNIVERSE_MIN_HISTORY_DAYS`` of 1m history
  (:mod:`hunter_strategy_worker.universe` has the full rule and why), counted
  ``hunter_shadow_bars_skipped_total{reason="universe_history"}``.

Split out of ``consumer.py`` for the same reason ``outcome_sweep.py`` was in
T3.74c: a distinct responsibility, and that file's own 350-line budget.
``ack_fn`` is threaded through rather than imported here so ``run_consumer``'s
own (test-monkeypatched) ``ack`` reference is what actually runs the ACK --
this module has no ambient side-effect surface of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hunter_core.domain.enums import MarketType
from hunter_core.domain.types import utcnow
from hunter_core.events.streams import Streams
from hunter_strategy_worker.metrics import shadow_bars_skipped_total
from hunter_strategy_worker.shard import owns_market

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_strategy_worker.consumer_health import ConsumerHealth
    from hunter_strategy_worker.universe import UniverseCache

    AckFn = Callable[[redis_asyncio.Redis, Any, str, str, Any], Awaitable[None]]

__all__ = ["refuse_before_dispatch"]


async def refuse_before_dispatch(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    *,
    message_id: str,
    envelope: Any,
    group: str,
    health: ConsumerHealth,
    universe: UniverseCache | None,
    shard_index: int,
    shard_total: int,
    ack_fn: AckFn,
    clock: Callable[[], datetime] = utcnow,
) -> bool:
    """``True`` when ``envelope`` was acked and must not reach the dispatcher."""
    payload = envelope.payload
    if not owns_market(payload.get("symbol", "?"), shard_index, shard_total):
        shadow_bars_skipped_total.labels(reason="not_my_shard").inc()
        await ack_fn(redis, Streams.MARKET_CANDLES_CLOSED, group, message_id, envelope)
        return True
    if universe is not None and payload.get("market_type") == MarketType.PERPETUAL.value:
        admitted, size, total = await universe.check(
            factory,
            exchange=payload.get("exchange", "?"),
            symbol=payload.get("symbol", "?"),
            shard_index=shard_index,
            shard_total=shard_total,
            clock=clock,
        )
        health.universe_size, health.universe_total = size, total
        if not admitted:
            shadow_bars_skipped_total.labels(reason="universe_history").inc()
            await ack_fn(redis, Streams.MARKET_CANDLES_CLOSED, group, message_id, envelope)
            return True
    return False
