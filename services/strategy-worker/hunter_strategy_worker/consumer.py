"""The ``market.candles.closed`` consumer and the outcome sweep.

Own consumer group (``strategy-worker.shadow``), ``event_id`` idempotency from
``hunter_core.events.consume``, and the ACK only after the transaction that made
the decision durable committed. A crash between the commit and the ACK just
redelivers the message, and the redelivery is a no-op: the signal id is
deterministic and the slot barrier has already moved past the bar.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.market import NormalizedCandle, from_wire
from hunter_core.domain.types import utcnow
from hunter_core.events.consume import ack, consume
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_strategy_worker import slots
from hunter_strategy_worker.config import CONSUMER_GROUP
from hunter_strategy_worker.decide import evaluate_slot, versions_for_bar
from hunter_strategy_worker.metrics import shadow_trackings_open, shadow_trackings_unswept
from hunter_strategy_worker.outcomes import advance_tracking
from hunter_strategy_worker.repo import load_market
from hunter_strategy_worker.tracking_repo import (
    count_open_trackings,
    load_open_trackings,
    load_tracking,
)
from hunter_strategy_worker.versions import VersionCache

if TYPE_CHECKING:
    from collections.abc import Callable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_core.settings import Settings
    from hunter_strategy_worker.config import ShadowConfig

logger = get_logger(__name__)

CONSUME_BLOCK_MS = 2_000
"""How long ``XREADGROUP`` may block, in milliseconds.

Deliberately under ``hunter_core.redis``'s 5 s ``socket_timeout`` (HIGH-4).
``consume()``'s own default is 5000, which is exactly the read deadline: on a
quiet stream the block runs its full budget and the socket read times out at the
same instant, so an idle stream raises ``redis.exceptions.TimeoutError``. Found
in the S2 operational proof — the worker died on it once before the loop below
learned to treat it as a backoff.
"""

RESTART_BACKOFF_S = 1.0
RESTART_BACKOFF_MAX_S = 30.0

__all__ = [
    "CONSUME_BLOCK_MS",
    "ConsumerHealth",
    "handle_candle",
    "run_consumer",
    "run_outcomes",
]


@dataclass
class ConsumerHealth:
    """Liveness of the decision loop, read by ``/ready``."""

    last_iteration_at: datetime | None = None
    started_at: datetime | None = None
    """When the loop entered ``consume()`` — a worker that has started but has
    seen no message yet is not stuck, it is idle."""
    evaluated_bars: int = 0
    errors: int = 0
    states: dict[str, int] = field(default_factory=lambda: {})

    def touch(self) -> None:
        self.last_iteration_at = utcnow()

    def record(self, state: str) -> None:
        self.states[state] = self.states.get(state, 0) + 1


def _candle(payload: dict[str, Any]) -> NormalizedCandle | None:
    data = dict(payload)
    data.pop("ts", None)
    try:
        return from_wire(NormalizedCandle, data)
    except Exception:
        logger.warning("shadow_candle_payload_unreadable")
        return None


async def handle_candle(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    *,
    payload: dict[str, Any],
    versions: VersionCache,
    config: ShadowConfig,
    health: ConsumerHealth,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Evaluate every active version whose timeframe closed with this candle."""
    candle = _candle(payload)
    if candle is None or not candle.is_final:
        return
    bar_close = candle.close_time
    due = versions_for_bar(await versions.get(factory), bar_close)
    if not due:
        return
    async with role_session(factory, db_role="hunter_worker") as session:
        market = await load_market(session, candle.exchange, candle.symbol)
    if market is None:
        logger.warning("shadow_market_unknown", exchange=candle.exchange, symbol=candle.symbol)
        return
    for version in due:
        evaluation = await evaluate_slot(
            factory,
            redis,
            version=version,
            market=market,
            bar_close=bar_close,
            config=config,
            clock=clock,
        )
        health.evaluated_bars += 1
        health.record(evaluation.state.value)


async def run_consumer(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    config: ShadowConfig,
    health: ConsumerHealth,
) -> None:
    """Consume closed candles forever.

    Two independent failure budgets, because they are different failures: one
    unreadable message is skipped (it must not block the stream), while an error
    from the *iteration itself* — Redis restarting, a dropped connection, the
    idle-block timeout — backs off and re-enters ``consume()``. Neither is
    allowed to leave this coroutine, because returning is fatal (``forever``).
    """
    versions = VersionCache(config.version_refresh_s)
    consumer = f"strategy-worker@{runtime.instance}"
    backoff = RESTART_BACKOFF_S
    health.started_at = utcnow()
    while True:
        try:
            async for message_id, envelope in consume(
                redis,
                Streams.MARKET_CANDLES_CLOSED,
                CONSUMER_GROUP,
                consumer,
                block_ms=CONSUME_BLOCK_MS,
            ):
                health.touch()
                backoff = RESTART_BACKOFF_S
                try:
                    await handle_candle(
                        factory,
                        redis,
                        payload=envelope.payload,
                        versions=versions,
                        config=config,
                        health=health,
                    )
                except Exception:
                    health.errors += 1
                    runtime.mark_error()
                    logger.exception(
                        "shadow_candle_handling_failed", event_id=str(envelope.event_id)
                    )
                    continue
                await ack(
                    redis, Streams.MARKET_CANDLES_CLOSED, CONSUMER_GROUP, message_id, envelope
                )
                runtime.mark_success()
            # ``consume()`` is an infinite generator; reaching here means it
            # stopped without raising. Back off rather than spin, and say so.
            logger.warning("shadow_consumer_stream_ended", backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("shadow_consumer_restarting", backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)


async def sweep_outcomes(
    factory: async_sessionmaker[AsyncSession],
    config: ShadowConfig,
    *,
    blocked: frozenset[str] = frozenset(),
    now: datetime | None = None,
) -> int:
    """Advance up to ``SWEEP_LIMIT`` open trackings once.

    Returns how many of the ones it *visited* are still open. The pass is
    bounded (``tracking_repo.SWEEP_LIMIT``), and the rows past the bound would
    otherwise be indistinguishable from a quiet market, so the backlog is
    published as ``hunter_shadow_trackings_unswept`` rather than left invisible.
    """
    async with role_session(factory, db_role="hunter_worker") as session:
        pending = await load_open_trackings(session)
        total_open = await count_open_trackings(session)
    unswept = max(0, total_open - len(pending))
    shadow_trackings_unswept.set(unswept)
    if unswept:
        logger.warning("shadow_sweep_incomplete", visited=len(pending), unswept=unswept)
    still_open = 0
    for tracking in pending:
        async with role_session(factory, db_role="hunter_worker") as session:
            await slots.lock_slot(
                session,
                strategy_version_id=tracking.strategy_version_id,
                market_id=tracking.market_id,
                cohort=str(tracking.meta.get("cohort") or config.cohort),
            )
            fresh = await load_tracking(session, tracking.signal_id)
            if fresh is None:
                continue
            result = await advance_tracking(session, fresh, config=config, blocked=blocked, now=now)
            if not result.finished:
                still_open += 1
    shadow_trackings_open.set(still_open)
    return still_open


async def run_outcomes(
    factory: async_sessionmaker[AsyncSession],
    runtime: WorkerRuntime,
    config: ShadowConfig,
    settings: Settings,
) -> None:
    """The outcome sweep loop. Postgres down is a backoff, never a death."""
    blocked = frozenset(s.upper() for s in settings.market_universe_blocklist)
    while True:
        try:
            await sweep_outcomes(factory, config, blocked=blocked)
            runtime.mark_success()
        except Exception:
            runtime.mark_error()
            logger.exception("shadow_outcome_sweep_failed")
            await asyncio.sleep(min(60.0, config.outcome_poll_s * 6))
            continue
        await asyncio.sleep(config.outcome_poll_s)
