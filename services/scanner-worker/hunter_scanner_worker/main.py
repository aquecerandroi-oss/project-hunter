"""``HUNTER_ROLE=scanner`` -- one TaskGroup, and an exit is fatal.

Startup order is a contract, not a convenience:

1. **the policy** (``opportunity_weights``) -- without it there is nothing to
   score with, and inventing thresholds is worse than not starting;
2. **the universe**, with each market's durable state and warm checkpoint;
3. **the baseline cache**, so the first evaluation already knows which buckets
   are usable and which are under construction;
4. **the regime's thirty days**, read once and maintained incrementally;
5. **the outbox reconciliation** -- anything a previous process committed but
   did not publish goes out before this one produces anything new.

Only then do the consumers start. A scanner that consumed before step 5 would
publish a newer opportunity ahead of an older one that was already durable.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import create_session_factory
from hunter_core.domain.types import utcnow
from hunter_core.events.outbox import OutboxHealth, reconcile, run_dispatcher
from hunter_core.events.streams import Streams
from hunter_core.logging import get_logger
from hunter_scanner_worker.backfill import BackfillRequester
from hunter_scanner_worker.baseline_runner import BootstrapProgress, baseline_loop
from hunter_scanner_worker.baselines import BaselineCache
from hunter_scanner_worker.config import build_config
from hunter_scanner_worker.consumers import (
    ConsumerHealth,
    candle_of,
    coalesce,
    observe_delay,
    pending_ack,
    run_batch_consumer,
    run_stream_consumer,
)
from hunter_scanner_worker.deriv import deriv_loop
from hunter_scanner_worker.health import CycleHealth, readiness_checks, write_heartbeat
from hunter_scanner_worker.metrics import scanner_ticks_coalesced_total
from hunter_scanner_worker.persist import DB_ROLE
from hunter_scanner_worker.policy import load_policy
from hunter_scanner_worker.pressure import LivePressure
from hunter_scanner_worker.regime import BTC_SYMBOL, RegimeEngine
from hunter_scanner_worker.registry import MarketRegistry
from hunter_scanner_worker.runners import (
    evaluation_loop,
    refresh_universe,
    regime_loop,
    registry_loop,
    watchdog_loop,
)
from hunter_scanner_worker.scanner import Scanner
from hunter_scanner_worker.supervision import forever
from hunter_scanner_worker.writers import probe_baseline_lock

if TYPE_CHECKING:
    from hunter_core.events.envelope import EventEnvelope
    from hunter_core.runtime import WorkerRuntime
    from hunter_scanner_worker.config import ScannerConfig
    from hunter_scanner_worker.state import PendingAck

logger = get_logger(__name__)

REGIME_HISTORY_DAYS = 30

__all__ = ["run_scanner"]


async def run_scanner(runtime: WorkerRuntime) -> None:
    """Entry point registered for ``HUNTER_ROLE=scanner``."""
    config = build_config()
    factory = create_session_factory(runtime.engine)
    from hunter_core.db.session import role_session

    async with role_session(factory, db_role=DB_ROLE) as session:
        policy = await load_policy(session)
        # Its own transaction, before any batch: a privilege failure aborts the
        # transaction it happens in (writers.probe_baseline_lock).
        await probe_baseline_lock(session)

    scanner = Scanner(
        config=config,
        policy=policy,
        registry=MarketRegistry(exchange=config.exchange),
        producer=f"scanner-worker@{runtime.instance}",
    )
    scanner.cache = BaselineCache(gate=policy.gate)
    scanner.regime = RegimeEngine(thresholds=policy.regime)

    consumers, cycle, outbox_health = ConsumerHealth(), CycleHealth(), OutboxHealth()
    requester = BackfillRequester(scanner.producer)
    progress = BootstrapProgress()
    universe_wake = asyncio.Event()
    checks = readiness_checks(
        scanner, consumers, cycle, outbox_health, config, runtime.redis, progress
    )
    runtime.readiness_checks.extend(checks)
    # A diagnostic, never a verdict: an operator reading a green ``/ready``
    # still has to see "bootstrapping BTCUSDT (37/200)" next to it.
    runtime.status_details["baselines"] = progress.describe

    try:
        await refresh_universe(scanner, factory, runtime.redis)
        await _warm(scanner, factory, runtime, cycle)
        # Publish anything a previous process committed and did not announce,
        # before this one produces a single new event.
        recovered = await reconcile(runtime.redis, factory, db_role=DB_ROLE)
        if recovered:
            logger.info("scanner_outbox_reconciled", published=recovered)

        async with asyncio.TaskGroup() as group:
            tasks: dict[str, Any] = {
                "evaluation": evaluation_loop(scanner, factory, runtime.redis, runtime, cycle),
                "regime": regime_loop(scanner, factory, runtime.redis, runtime),
                "watchdog": watchdog_loop(scanner, factory, runtime.redis, runtime),
                "registry": registry_loop(scanner, factory, runtime.redis, runtime, universe_wake),
                "baselines": baseline_loop(
                    scanner,
                    factory,
                    runtime.engine,
                    runtime.redis,
                    runtime,
                    progress,
                    requester,
                    LivePressure(
                        scanner.state,
                        suspend_s=config.feature_throttle_s,
                        resume_s=config.feature_throttle_s / 2,
                    ),
                ),
                "deriv": deriv_loop(scanner, factory, runtime),
                "outbox": run_dispatcher(runtime.redis, factory, outbox_health, db_role=DB_ROLE),
                "heartbeat": _heartbeat_loop(runtime, scanner, cycle, consumers, config, progress),
            }
            for stream in (
                Streams.MARKET_TICKS,
                Streams.MARKET_DERIVATIVES,
                Streams.MARKET_LIQUIDATIONS,
            ):
                tasks[f"consume:{stream}"] = run_batch_consumer(
                    runtime.redis,
                    runtime,
                    stream,
                    consumers,
                    touch_batch_handler(scanner, stream),
                    block_ms=config.consume_block_ms,
                    batch=config.consume_batch,
                )
            tasks["consume:candles"] = run_stream_consumer(
                runtime.redis,
                runtime,
                Streams.MARKET_CANDLES_CLOSED,
                consumers,
                _candle_handler(scanner),
                block_ms=config.consume_block_ms,
            )
            tasks["consume:universe"] = run_stream_consumer(
                runtime.redis,
                runtime,
                Streams.MARKET_UNIVERSE_CHANGED,
                consumers,
                _universe_handler(universe_wake),
                block_ms=config.consume_block_ms,
            )
            for name, coro in tasks.items():
                group.create_task(forever(name, coro), name=f"scanner-{name}")
    finally:
        runtime.status_details.pop("baselines", None)
        for check in checks:
            if check in runtime.readiness_checks:
                runtime.readiness_checks.remove(check)


def touch_batch_handler(scanner: Scanner, stream: str) -> Any:
    """Ticks, derivatives and liquidations: notifications with no durable effect.

    The evidence is the hot state, not the message, so the ACK is immediate --
    losing one of these costs nothing, because the next evaluation reads the
    same Redis keys either way. And for the same reason the batch is coalesced
    per market before it is applied: 500 ticks over 40 markets are 40 touches,
    not 500 (T2.5d). Every message of the batch is still acked -- coalescence
    absorbs work, never messages.
    """

    async def handle(deliveries: list[tuple[str, EventEnvelope]]) -> None:
        result = coalesce(deliveries)
        observe_delay(stream, result.oldest)
        for symbol, stamp in result.newest.items():
            scanner.state.touch(symbol, stream, input_ts=stamp)
        if result.absorbed:
            scanner_ticks_coalesced_total.labels(stream=stream).inc(result.absorbed)

    return handle


def _candle_handler(scanner: Scanner) -> Any:
    """A closed candle announces a minute that has to be snapshotted.

    Its ACK therefore waits for the transaction that writes the snapshot
    (``persist.flush_batch``): a crash between reading and committing must
    redeliver the minute, not lose it.
    """

    async def handle(message_id: str, envelope: EventEnvelope) -> PendingAck | None:
        candle = candle_of(envelope)
        if candle is None or not candle.is_final:
            return None
        if candle.symbol == BTC_SYMBOL and scanner.regime is not None:
            scanner.regime.observe_candle(candle)
        if not scanner.state.touch(
            candle.symbol, Streams.MARKET_CANDLES_CLOSED, input_ts=candle.close_time
        ):
            return None
        ack = pending_ack(Streams.MARKET_CANDLES_CLOSED, message_id, envelope)
        scanner.state.pending_acks.append(ack)
        return ack

    return handle


def _universe_handler(wake: asyncio.Event) -> Any:
    """The event only asks for a refresh: the database stays the source of truth.

    The payload carries symbols and the scanner is keyed by ``market_id``, so
    trusting the message would mean evaluating a market whose id we guessed.
    """

    async def handle(message_id: str, envelope: EventEnvelope) -> PendingAck | None:
        del message_id, envelope
        wake.set()
        return None

    return handle


async def _warm(scanner: Scanner, factory: Any, runtime: WorkerRuntime, cycle: CycleHealth) -> None:
    """Load the baseline cache, the derivative history and the regime's series."""
    from hunter_scanner_worker.repo import load_candles, load_open_regime

    now = utcnow()
    refs = list(scanner.registry.by_symbol.values())
    async with runtime.engine.begin() as connection:
        loaded = await scanner.cache.refresh(connection, refs, now=now) if scanner.cache else 0
    cycle.baselines_loaded = True
    # Before the first evaluation, not after: a market evaluated without its
    # open-interest history disarms ``OPEN_INTEREST_SPIKE`` for that cycle, and
    # doing that on every restart would be a self-inflicted blind spot.
    observations = await scanner.deriv.refresh(factory, refs, now=now)
    logger.info(
        "scanner_baselines_loaded",
        revisions=loaded,
        markets=len(refs),
        deriv_observations=observations,
    )

    btc = scanner.registry.ref(BTC_SYMBOL)
    if btc is not None and scanner.regime is not None:
        from hunter_core.db.session import role_session

        async with role_session(factory, db_role=DB_ROLE) as session:
            candles = await load_candles(
                session,
                btc.market_id,
                exchange=btc.exchange,
                symbol=btc.symbol,
                since=now - timedelta(days=REGIME_HISTORY_DAYS),
            )
            open_regime = await load_open_regime(session)
        scanner.regime.seed(candles, until=now)
        if open_regime is not None:
            scanner.regime_id = open_regime[0]
            scanner.regime.row_id = open_regime[0]


async def _heartbeat_loop(
    runtime: WorkerRuntime,
    scanner: Scanner,
    cycle: CycleHealth,
    consumers: ConsumerHealth,
    config: ScannerConfig,
    progress: BootstrapProgress,
) -> None:
    while True:
        await write_heartbeat(runtime.redis, runtime, scanner, cycle, consumers, progress)
        await asyncio.sleep(config.heartbeat_s)
