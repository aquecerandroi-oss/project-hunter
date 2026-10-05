"""The loops. Everything durable happens in the evaluation cycle's transaction.

Five long-lived tasks, and the split between them is by *cadence*, not by
subject: one owner still advances each market (``Scanner.advance``), and the
other loops only feed it or maintain what it reads.

- :func:`evaluation_loop` -- wakes four times a second, evaluates every dirty
  market whose 1 s throttle elapsed, and commits one batch per second. Waking
  faster than the throttle is deliberate: the budget being defended is the age
  of the *input*, and a 1 s sleep would add up to a second of pure waiting to
  every tick before any work started;
- :func:`regime_loop` -- once a minute, the global regime from BTC and the
  breadth of the vectors the cycle already computed;
- :func:`baseline_loop` -- the bootstrap once at startup, then the bucket of
  each hour that closes;
- :func:`watchdog_loop` -- the absence, reported to both state machines;
- :func:`registry_loop` -- the universe, and warm-up/teardown of the markets
  that joined or left.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hunter_core.domain.types import utcnow, uuid7
from hunter_core.events.outbox import build_envelope, event_id_for
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_scanner_worker import publish as projections
from hunter_scanner_worker import rows
from hunter_scanner_worker.checkpoint import load_checkpoint, save_checkpoint
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.cycle_health import CycleHealth
from hunter_scanner_worker.evaluation_cycle import evaluate_due_markets
from hunter_scanner_worker.failure_summary import summarize_exception
from hunter_scanner_worker.flush_lane import BLOCKED_BACKOFF_S, FlushLane
from hunter_scanner_worker.persist import WriteBatch, flush_batch
from hunter_scanner_worker.regime import BTC_SYMBOL, breadth_observation
from hunter_scanner_worker.rehydrate import rehydrate_markets, resync_invalidated
from hunter_scanner_worker.watchdog import sweep_silent_markets

if TYPE_CHECKING:
    from collections.abc import Coroutine

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

__all__ = [
    "evaluation_loop",
    "regime_loop",
    "registry_loop",
    "watchdog_loop",
    "writer_tasks",
]


async def evaluation_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    cycle: CycleHealth,
    lane: FlushLane | None = None,
) -> None:
    """Evaluate the dirty markets and commit one batch. Forever.

    The whole cycle -- from the first mutation to the end of the flush -- runs under
    ``lane.lock`` and appends to ``lane.batch``, which survives any exception: a
    failed flush or a Redis error mid-cycle keeps what was already collected, because
    the collectors have already forgotten it (``flush_lane``).
    """
    config = scanner.config
    lane = lane or FlushLane(factory, redis, cycle)
    last_flush = utcnow()
    while True:
        now = utcnow()
        pause = config.cycle_s
        try:
            async with lane.lock:
                if lane.invalidated:
                    # Before any new mutation: a market whose rows were dropped at
                    # flush time must be back in line with the table first, or the
                    # next episode opens beside one the table still holds open.
                    await resync_invalidated(scanner, factory, lane)
                if lane.blocked:
                    # Fail loud, do not drop and do not grow: the retained batch is
                    # retried, nothing new is collected on top of it.
                    cycle.touch(0)
                    pause = BLOCKED_BACKOFF_S
                else:
                    cycle.touch(await evaluate_due_markets(scanner, redis, lane.batch, now=now))
                due_flush = (now - last_flush).total_seconds() >= config.persist_s
                if lane.blocked or due_flush or lane.batch.acks:
                    if not lane.blocked:  # an ACK never outruns the evaluation it announces
                        lane.batch.add_acks(scanner.state.take_acks())
                    if await lane.flush(now=now):
                        last_flush = now
                        try:  # after a good commit: its failure is not a persistence failure
                            await _save_checkpoints(redis, scanner, evaluated_only=True)
                        except Exception as error:
                            cycle.checkpoint_failed(error)
                    else:
                        pause = max(pause, 1.0)  # the failure is already in ``cycle``
            if cycle.failures:
                runtime.mark_error()
            else:
                runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            runtime.mark_error()
            lane.failed(error)
            pause = 1.0 + config.cycle_s
        await asyncio.sleep(pause)


def writer_tasks(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    cycle: CycleHealth,
) -> dict[str, Coroutine[Any, Any, None]]:
    """The two loops that mutate scanner memory, sharing one batch and one lock."""
    lane = FlushLane(factory, redis, cycle)
    return {
        "evaluation": evaluation_loop(scanner, factory, redis, runtime, cycle, lane),
        "watchdog": watchdog_loop(scanner, factory, redis, runtime, lane),
    }


async def _save_checkpoints(
    redis: redis_asyncio.Redis, scanner: Scanner, *, evaluated_only: bool
) -> None:
    """Persist the warm state of every market that moved this cycle."""
    del evaluated_only
    for market in scanner.state.markets.values():
        if market.last_vector_at is None:
            continue
        try:
            await save_checkpoint(
                redis,
                market.ref.exchange,
                market.ref.symbol,
                market.checkpoint,
                market.ref.market_type,
            )
        except Exception:
            logger.warning("scanner_checkpoint_save_failed", symbol=market.ref.symbol)


async def regime_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
) -> None:
    """One global verdict a minute, with the row it opens or keeps."""
    while True:
        await asyncio.sleep(scanner.config.regime_s)
        try:
            await run_regime_once(scanner, factory, redis)
            runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            runtime.mark_error()
            logger.error("scanner_regime_failed", **summarize_exception(error))


async def run_regime_once(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    *,
    now: datetime | None = None,
) -> None:
    """Classify once and make the transition durable."""
    engine = scanner.regime
    if engine is None or not engine.warmed:
        return
    # The same cut the markets are evaluated at, for the same reason: a regime
    # stamped ahead of an observation is evidence from the future, and
    # ``ScoreContext`` refuses it (operational proof).
    coverage = await read_coverage(redis, scanner.config.exchange)
    clock = now or utcnow()
    proven = coverage.covered_until
    moment = proven if (proven is not None and coverage.fresh(now=clock)) else clock
    moment = min(moment, clock)
    engine.roll_hour(moment)
    btc = scanner.state.get(BTC_SYMBOL)
    observations = [
        breadth_observation(symbol, state.last_vector)
        for symbol, state in scanner.state.markets.items()
        if state.last_vector is not None
    ]
    decision = engine.classify(
        vector=None if btc is None else btc.last_vector,
        as_of=moment,
        breadth_observations=observations,
        universe_size=scanner.registry.size,
    )
    batch = WriteBatch()
    regime_id: UUID | None = None
    if decision.changed or scanner.regime_id is None:
        regime_id = uuid7()
        if scanner.regime_id is not None:
            batch.regime_close = (scanner.regime_id, moment)
        batch.regime_open = rows.regime_row(
            decision, regime_id=regime_id, scope=scanner.regime_scope(), start_time=moment
        )
        batch.events.append(
            build_envelope(
                Streams.REGIME_CHANGED,
                event_id_for(Streams.REGIME_CHANGED, regime_id, decision.observation_ts),
                rows.regime_event_payload(decision, regime_id=regime_id),
                producer=scanner.producer,
                key="global",
                ts=moment,
            )
        )
    else:
        # The pair did not change, but the hysteresis and the evidence did: the
        # checkpoint has to move on every accepted observation or a restart
        # loses the pending confirmations (Astra, T2.5 design review). The row
        # id is known here -- the branch above is the one that has none.
        batch.regime_touch = (
            scanner.regime_id,
            rows.jsonable(
                {
                    **decision.supporting_features(),
                    "state_out": decision.state_out.as_wire(),
                }
            ),
        )
    await flush_batch(factory, redis, batch, now=moment)
    if regime_id is not None:
        # After the commit, never before: an opportunity that names a regime row the
        # table never got is refused by its foreign key, and with a retained batch
        # that refusal would hold the whole lane (Astra, 05/10).
        scanner.regime_id = regime_id
        engine.row_id = regime_id
    await projections.publish_regime_current(redis, decision, regime_id=str(scanner.regime_id))


async def watchdog_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    lane: FlushLane | None = None,
) -> None:
    """Report the minutes nobody saw, so the two expiries are provable.

    Shares the evaluation cycle's ``lane``: it mutates memory too, so it takes the
    same lock and appends to the same batch, and a failed flush of its rows feeds
    ``scanner_persistence`` like any other. A private lane, when none is given, feeds
    nobody -- the worker always passes the shared one.
    """
    lane = lane or FlushLane(factory, redis, CycleHealth())
    while True:
        await asyncio.sleep(scanner.config.watchdog_s)
        try:
            async with lane.lock:
                if lane.invalidated:
                    await resync_invalidated(scanner, factory, lane)
                if lane.blocked:
                    continue  # nothing new on top of a batch that cannot be committed
                sweep_silent_markets(scanner, lane.batch)
                flushed = await lane.flush()
            if flushed:
                runtime.mark_success()
            else:
                runtime.mark_error()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            runtime.mark_error()
            lane.failed(error)  # a failed sweep feeds scanner_persistence too


async def registry_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    wake: asyncio.Event,
) -> None:
    """Keep the evaluated universe equal to ``markets.is_monitored``."""
    while True:
        try:
            await refresh_universe(scanner, factory, redis)
            runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_registry_refresh_failed")
        try:
            await asyncio.wait_for(wake.wait(), scanner.config.registry_refresh_s)
        except TimeoutError:
            pass
        wake.clear()


async def refresh_universe(
    scanner: Scanner, factory: async_sessionmaker[AsyncSession], redis: redis_asyncio.Redis
) -> None:
    """Apply the current universe: warm the new markets, close out the old ones."""
    diff = await scanner.registry.refresh(factory, limit=scanner.config.max_markets)
    now = utcnow()
    for ref in diff.added:
        state = scanner.state.ensure(ref, now=now)
        state.checkpoint = await load_checkpoint(redis, ref.exchange, ref.symbol, ref.market_type)
        state.touch("universe_added")
    for ref in diff.removed:
        # An honest close-out: the market stops being evaluated *and* stops
        # being a Radar row. Leaving the ZSET entry would show a score nobody
        # is refreshing.
        scanner.state.drop(ref.symbol)
        scanner.deriv.drop(ref.market_id)
        await projections.drop_from_radar(redis, ref)
    if diff.changed:
        await rehydrate_markets(scanner, factory, [ref for ref in diff.added])
