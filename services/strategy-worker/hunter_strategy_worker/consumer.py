"""The ``market.candles.closed`` consumer and the outcome sweep.

Own consumer group (``strategy-worker.shadow``), ``event_id`` idempotency from
``hunter_core.events.consume``, and the ACK only after the transaction that made
the decision durable committed. A crash between the commit and the ACK just
redelivers the message, and the redelivery is a no-op: the signal id is
deterministic and the slot barrier has already moved past the bar.
"""

from __future__ import annotations

import asyncio
import functools
from datetime import datetime
from typing import TYPE_CHECKING, Any

from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.db.session import role_session
from hunter_core.domain.market import NormalizedCandle, from_wire
from hunter_core.domain.types import utcnow
from hunter_core.events.consume import ack, consume
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_strategy_worker.bar_context import load_bar_bundle
from hunter_strategy_worker.consumer_health import ConsumerHealth
from hunter_strategy_worker.context_cache import load_family_readers
from hunter_strategy_worker.decide import evaluate_slot, versions_for_bar
from hunter_strategy_worker.decision_market_type import DECISION_MARKET_TYPE
from hunter_strategy_worker.dispatch import BarDispatcher, market_key
from hunter_strategy_worker.metrics import (
    shadow_bars_skipped_total,
    shadow_redis_timeouts_total,
    shadow_stage_seconds,
    shadow_version_failed_total,
)
from hunter_strategy_worker.pre_dispatch import refuse_before_dispatch
from hunter_strategy_worker.repo import load_market
from hunter_strategy_worker.shard import consumer_group
from hunter_strategy_worker.universe import UniverseCache
from hunter_strategy_worker.versions import VersionCache

if TYPE_CHECKING:
    from collections.abc import Callable

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
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
]


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
    """Evaluate every active version whose timeframe closed with this candle.

    **One version's failure is that version's failure — unless it is Redis's.**
    The loop below used to have no ``try``: a version whose frozen parameters
    raise — the exact shape a badly derived research variant takes
    (``derive_variant.py``, T3.26) — aborted the whole bar, so every version
    after it in the roster silently stopped evaluating and the message was
    never acked, redelivered forever (review T3.26-risk, A3). Now each version
    is isolated, counted (``hunter_shadow_version_failed_total``) and logged,
    the surviving versions still produce their decisions, and the bar is
    acked: a bar that half the roster could not evaluate is still a bar that
    was processed.

    ``redis.exceptions.TimeoutError`` is deliberately **not** isolated the
    same way (T3.83, VPS: four shards, same ~12s window, a midnight burst
    stalling Redis): it is transient, unlike a broken version, and every other
    due version is at the same risk, so it re-raises — the bar stays un-acked
    and comes back via ``XAUTOCLAIM``, a no-op for whatever already committed
    (module docstring). Swallowing it here would silently drop that one
    (market, version, bar) decision forever instead.

    **One candle read per family, not per version (T3.74b).** Due versions
    sharing a ``strategy_key`` (same code, different frozen parameters) share
    one preloaded candle window (:mod:`hunter_strategy_worker.context_cache`,
    design and honest limits there); each version still reads exactly its own
    ``context_minutes``. A failed preload just means no reader — every member
    falls back to its own query, same as before this existed.

    **One read and one validated context per bar (T3.74g).** The bundle
    (:mod:`hunter_strategy_worker.bar_context`, measurements and limits there)
    widens that to the whole bar and to the context object itself, and falls
    back to the family readers — and so to per-version reads — when it fails.
    """
    candle = _candle(payload)
    if candle is None or not candle.is_final:
        return
    if candle.market_type is not DECISION_MARKET_TYPE:
        # Not in the decision universe at all — refused before the market row is
        # even resolved, so it costs one comparison and not one query per bar.
        shadow_bars_skipped_total.labels(reason=f"market_type:{candle.market_type.value}").inc()
        return
    bar_close = candle.close_time
    backlog_s = (clock() - bar_close).total_seconds()
    if backlog_s > config.late_delay_backlog_max_s:
        # Safety valve, not the fix (T3.74c, ShadowConfig.late_delay_backlog_max_s
        # docstring) — a bar this far behind would almost always end up
        # ``no_entry: late:delay`` even fully evaluated, so during a real
        # backlog this stops paying load_market/context/evaluate for every
        # due version just to reach that same conclusion later and slower.
        shadow_bars_skipped_total.labels(reason="late_delay_backlog").inc()
        logger.warning("shadow_bar_skipped_late_backlog", backlog_s=f"{backlog_s:.0f}")
        return
    due = versions_for_bar(await versions.get(factory), bar_close)
    if not due:
        return
    with shadow_stage_seconds.labels(stage="market_lookup").time():
        async with role_session(factory, db_role="hunter_worker") as session:
            market = await load_market(session, candle.exchange, candle.symbol, candle.market_type)
    if market is None:
        logger.warning("shadow_market_unknown", exchange=candle.exchange, symbol=candle.symbol)
        return
    with shadow_stage_seconds.labels(stage="family_preload").time():
        bundle = await load_bar_bundle(
            factory, redis, due, market=market, bar_close=bar_close, config=config
        )
        family_readers = (
            {}
            if bundle is not None
            else await load_family_readers(
                factory, due, market=market, bar_close=bar_close, config=config
            )
        )
    for version in due:
        try:
            evaluation = await evaluate_slot(
                factory,
                redis,
                version=version,
                market=market,
                bar_close=bar_close,
                config=config,
                clock=clock,
                candles_reader=family_readers.get(version.strategy_key),
                bundle=bundle,
            )
        except asyncio.CancelledError:
            raise
        except RedisTimeoutError:
            shadow_redis_timeouts_total.labels(stage="version_evaluate").inc()
            logger.warning(
                "shadow_version_redis_timeout",
                strategy=version.strategy_key,
                version=version.version,
                market=f"{candle.exchange}:{candle.symbol}",
                bar_close=bar_close.isoformat(),
            )
            raise
        except Exception:
            shadow_version_failed_total.labels(
                strategy_key=version.strategy_key, version=version.version
            ).inc()
            health.errors += 1
            logger.exception(
                "shadow_version_evaluation_failed",
                strategy=version.strategy_key,
                version=version.version,
                market=f"{candle.exchange}:{candle.symbol}",
                bar_close=bar_close.isoformat(),
            )
            continue
        health.evaluated_bars += 1
        health.record(evaluation.state.value)


async def run_consumer(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    config: ShadowConfig,
    health: ConsumerHealth,
    *,
    shard_index: int = 0,
    shard_total: int = 1,
    clock: Callable[[], datetime] = utcnow,
) -> None:
    """Consume closed candles forever.

    **Bounded concurrency across markets, serial within one (T3.74c).** Up to
    ``config.worker_concurrency`` bars run at once, one per distinct market
    (:mod:`hunter_strategy_worker.dispatch`, docstring there for the measured
    burst this answers) — the read loop itself only blocks on the semaphore,
    never on a bar's own handling, so a slow bar no longer holds up reading
    the next one for a *different* market off the stream. ``claim_idle_ms``
    (``config.claim_idle_ms``) is passed through to ``consume()`` instead of
    its own default -- see ``ShadowConfig.claim_idle_ms`` for the arithmetic
    and why a dispatcher-aware value matters here (T3.74d).

    **Refusals before the dispatcher.** :func:`hunter_strategy_worker.
    pre_dispatch.refuse_before_dispatch` acks and counts by name, before the
    semaphore or any stage timer runs, a bar this shard does not own (T3.74f)
    or -- unless ``config.universe_min_history_days`` is ``0`` -- outside the
    shadow universe (T3.82); that module has the mechanics, :mod:`.shard`/
    :mod:`.universe` the reasoning behind each.

    Two independent failure budgets, because they are different failures: one
    unreadable message is skipped (it must not block the stream), while an error
    from the *iteration itself* — Redis restarting, a dropped connection, the
    idle-block timeout — backs off and re-enters ``consume()``. Neither is
    allowed to leave this coroutine, because returning is fatal (``forever``).

    ``clock`` is forwarded to ``handle_candle`` unchanged (default ``utcnow``,
    real production behaviour) -- a test seam so a sharding-equivalence proof
    can run the real consumer loop against fixed, historical bar timestamps
    without every one of them reading as hours or years late.
    """
    versions = VersionCache(config.version_refresh_s)
    min_days = config.universe_min_history_days
    universe = UniverseCache(min_days) if min_days > 0 else None
    group = consumer_group(shard_index, shard_total)
    consumer = f"strategy-worker@{runtime.instance}"
    dispatcher = BarDispatcher(config.worker_concurrency)
    backoff = RESTART_BACKOFF_S
    health.started_at = utcnow()

    async def _handle_and_ack(message_id: str, envelope: Any) -> None:
        try:
            await handle_candle(
                factory,
                redis,
                payload=envelope.payload,
                versions=versions,
                config=config,
                health=health,
                clock=clock,
            )
        except Exception:
            health.errors += 1
            runtime.mark_error()
            logger.exception("shadow_candle_handling_failed", event_id=str(envelope.event_id))
            return
        await ack(redis, Streams.MARKET_CANDLES_CLOSED, group, message_id, envelope)
        runtime.mark_success()

    while True:
        try:
            async for message_id, envelope in consume(
                redis,
                Streams.MARKET_CANDLES_CLOSED,
                group,
                consumer,
                block_ms=CONSUME_BLOCK_MS,
                claim_idle_ms=config.claim_idle_ms,
            ):
                health.touch()
                backoff = RESTART_BACKOFF_S
                if await refuse_before_dispatch(
                    factory,
                    redis,
                    message_id=message_id,
                    envelope=envelope,
                    group=group,
                    health=health,
                    universe=universe,
                    shard_index=shard_index,
                    shard_total=shard_total,
                    ack_fn=ack,
                    clock=clock,
                ):
                    continue
                shadow_stage_seconds.labels(stage="queue_wait").observe(
                    max(0.0, (utcnow() - envelope.ts).total_seconds())
                )
                await dispatcher.submit(
                    market_key(envelope.payload),
                    message_id,
                    functools.partial(_handle_and_ack, message_id, envelope),
                )
            # ``consume()`` is an infinite generator; reaching here means it
            # stopped without raising. Every bar already accepted gets to
            # finish before the backoff sleep, not just abandoned mid-flight.
            await dispatcher.drain()
            logger.warning("shadow_consumer_stream_ended", backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)
        except asyncio.CancelledError:
            await dispatcher.cancel_all()
            raise
        except Exception as error:
            if isinstance(error, RedisTimeoutError):
                shadow_redis_timeouts_total.labels(stage="consumer_loop").inc()
            runtime.mark_error()
            logger.exception("shadow_consumer_restarting", backoff_s=backoff)
            await asyncio.sleep(backoff)
            backoff = min(RESTART_BACKOFF_MAX_S, backoff * 2)


# ``sweep_outcomes``/``run_outcomes`` moved to :mod:`hunter_strategy_worker.outcome_sweep`
# in T3.74c — a separate responsibility (advancing already-open trackings on
# their own timer) from consuming the candle stream, split out when the
# bar-dispatch work above grew past this file's own budget.
