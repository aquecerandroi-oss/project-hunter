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
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.events.outbox import build_envelope, event_id_for
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_scanner_worker import publish as projections
from hunter_scanner_worker import rows
from hunter_scanner_worker.checkpoint import load_checkpoint, save_checkpoint
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.persist import DB_ROLE, WriteBatch, flush_batch
from hunter_scanner_worker.regime import BTC_SYMBOL, breadth_observation
from hunter_scanner_worker.watchdog import sweep_silent_markets

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_scanner_worker.health import CycleHealth
    from hunter_scanner_worker.scanner import Scanner

logger = get_logger(__name__)

__all__ = [
    "evaluation_loop",
    "regime_loop",
    "registry_loop",
    "watchdog_loop",
]


async def evaluation_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    cycle: CycleHealth,
) -> None:
    """Evaluate the dirty markets and commit one batch. Forever."""
    config = scanner.config
    last_flush = utcnow()
    batch = WriteBatch()
    while True:
        now = utcnow()
        try:
            scanner.coverage = await read_coverage(redis, config.exchange, now=now)
            due = scanner.state.due(now, config.feature_throttle_s)
            evaluated = 0
            for market in due[: config.max_markets]:
                evaluation = await scanner.advance(redis, market, batch, now=now)
                if evaluation is None:
                    continue
                evaluated += 1
                await projections.publish_features(redis, scanner.producer, market.ref, evaluation)
                if evaluation.score is not None:
                    await projections.publish_radar(redis, market.ref, evaluation)
            cycle.touch(evaluated)
            if (now - last_flush).total_seconds() >= config.persist_s or batch.acks:
                batch.acks.extend(scanner.state.pending_acks)
                scanner.state.pending_acks = []
                invalidated = await flush_batch(factory, redis, batch, now=now)
                for market_id in invalidated:
                    ref = scanner.registry.ref_by_id(market_id)
                    state = None if ref is None else scanner.state.get(ref.symbol)
                    if state is not None:
                        state.touch("baseline_vanished")
                await _save_checkpoints(redis, scanner, evaluated_only=True)
                batch = WriteBatch()
                last_flush = now
            runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_cycle_failed")
            batch = WriteBatch()
            await asyncio.sleep(1.0)
        await asyncio.sleep(config.cycle_s)


async def _save_checkpoints(
    redis: redis_asyncio.Redis, scanner: Scanner, *, evaluated_only: bool
) -> None:
    """Persist the warm state of every market that moved this cycle."""
    del evaluated_only
    for market in scanner.state.markets.values():
        if market.last_vector_at is None:
            continue
        try:
            await save_checkpoint(redis, market.ref.exchange, market.ref.symbol, market.checkpoint)
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
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_regime_failed")


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
        scanner.regime_id = regime_id
        engine.row_id = regime_id
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
    await projections.publish_regime_current(redis, decision, regime_id=str(scanner.regime_id))


async def watchdog_loop(
    scanner: Scanner,
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
) -> None:
    """Report the minutes nobody saw, so the two expiries are provable."""
    while True:
        await asyncio.sleep(scanner.config.watchdog_s)
        try:
            batch = WriteBatch()
            sweep_silent_markets(scanner, batch)
            await flush_batch(factory, redis, batch)
            runtime.mark_success()
        except asyncio.CancelledError:
            raise
        except Exception:
            runtime.mark_error()
            logger.exception("scanner_watchdog_failed")


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
        state.checkpoint = await load_checkpoint(redis, ref.exchange, ref.symbol)
        state.touch("universe_added")
    for ref in diff.removed:
        # An honest close-out: the market stops being evaluated *and* stops
        # being a Radar row. Leaving the ZSET entry would show a score nobody
        # is refreshing.
        scanner.state.drop(ref.symbol)
        scanner.deriv.drop(ref.market_id)
        await projections.drop_from_radar(redis, ref)
    if diff.changed:
        await _rehydrate(scanner, factory, [ref for ref in diff.added])


async def _rehydrate(
    scanner: Scanner, factory: async_sessionmaker[AsyncSession], refs: list[object]
) -> None:
    """Load the durable state of the markets that just joined."""
    from hunter_scanner_worker.checkpoint import history_mark_from_wire
    from hunter_scanner_worker.registry import MarketRef
    from hunter_scanner_worker.repo import load_open_anomalies, load_open_episodes

    typed = [ref for ref in refs if isinstance(ref, MarketRef)]
    if not typed:
        return
    ids = [ref.market_id for ref in typed]
    since = utcnow() - timedelta(hours=6)
    async with role_session(factory, db_role=DB_ROLE) as session:
        anomalies = await load_open_anomalies(session, ids, since=since)
        episodes = await load_open_episodes(session, ids)
    for ref in typed:
        state = scanner.state.get(ref.symbol)
        if state is None:
            continue
        loaded = anomalies.get(ref.market_id, {})
        state.anomalies = {kind: entry[1] for kind, entry in loaded.items()}
        state.anomaly_ids = {kind: entry[0] for kind, entry in loaded.items() if entry[1].is_open}
        state.closed_anomaly_at = {
            kind: entry[1].observation_ts for kind, entry in loaded.items() if not entry[1].is_open
        }
        episode = episodes.get(ref.market_id)
        if episode is None:
            continue
        state.episode = episode.episode
        state.opportunity_id = episode.opportunity_id
        if episode.history_wire:
            try:
                state.checkpoint = state.checkpoint.__class__(
                    features=state.checkpoint.features,
                    stage=state.checkpoint.stage,
                    history=history_mark_from_wire(episode.history_wire),
                    recovered=True,
                )
            except Exception:
                logger.warning("scanner_history_mark_unreadable", symbol=ref.symbol)
