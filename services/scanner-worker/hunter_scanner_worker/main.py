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
from hunter_scanner_worker.beta import beta_loop
from hunter_scanner_worker.beta_job import BetaHealth
from hunter_scanner_worker.breadth import breadth_loop
from hunter_scanner_worker.breadth_job import BreadthHealth
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
from hunter_scanner_worker.regime_hourly import regime_hourly_loop
from hunter_scanner_worker.regime_job import RegimeHealth
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
    beta = BetaHealth()
    regime_hourly = RegimeHealth()
    breadth = BreadthHealth()
    universe_wake = asyncio.Event()
    checks = readiness_checks(
        scanner, consumers, cycle, outbox_health, config, runtime.redis, progress
    )
    runtime.readiness_checks.extend(checks)
    # A diagnostic, never a verdict: an operator reading a green ``/ready``
    # still has to see "bootstrapping BTCUSDT (37/200)" next to it.
    runtime.status_details["baselines"] = progress.describe
    # Beta is a *status detail*, never a readiness check (T3.7b): a producer
    # that has not run for two hours means the wallet stops opening positions,
    # which an operator has to see -- and means nothing at all to the Radar, the
    # baselines or the regime, which is the whole of what /ready gates.
    runtime.status_details["beta"] = lambda: beta.describe(utcnow())
    # The hourly regime producer is a research series: a hole in it costs a
    # cohort its context split and costs the live path nothing, so it is a
    # status detail for the same reason beta is -- visible, never a gate.
    runtime.status_details["regime_hourly"] = lambda: regime_hourly.describe(utcnow())
    # ``breadth_5m`` (T3.77): same reason again -- a hole makes a *gated* version
    # refuse (``breadth_unavailable``, fail-closed) and costs nobody else anything.
    runtime.status_details["breadth"] = lambda: (
        "stale" if breadth.stale(now=utcnow()) else f"universe {breadth.universe_size}"
    )

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
                "beta": beta_loop(scanner, factory, runtime.redis, runtime, beta),
                "regime_hourly": regime_hourly_loop(
                    scanner, factory, runtime.redis, runtime, regime_hourly
                ),
                "breadth": breadth_loop(
                    factory, runtime.redis, runtime, breadth, exchange=config.exchange
                ),
                "deriv": deriv_loop(scanner, factory, runtime),
                "outbox": run_dispatcher(runtime.redis, factory, outbox_health, db_role=DB_ROLE),
                "heartbeat": _heartbeat_loop(
                    runtime, scanner, cycle, consumers, config, progress, beta, regime_hourly
                ),
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
        runtime.status_details.pop("beta", None)
        # Every detail registered above is removed here, and the symmetry is a
        # test (``test_health.py``): a status detail left behind holds a
        # reference to the health object of a run that is over, and /status
        # would answer with the last numbers of a scanner that stopped.
        runtime.status_details.pop("regime_hourly", None)
        runtime.status_details.pop("breadth", None)
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

    **Perpetual only (T3.0d, notes-T3.0c.md §6).** The scanner has no spot
    universe, no spot baselines and no spot regime -- it evaluates the
    perpetual, full stop. Every symbol on Binance already carries a perpetual
    ticker at ~4 Hz, so a spot tick's payload ``symbol`` (``BTCUSDT``, with no
    market segment) reads as *the same market* to ``ScannerState.touch``, and
    without this filter it would mark the perpetual dirty and could set its
    ``last_input_ts`` from the spot venue's clock -- contaminating
    ``scanner_stream_delay_seconds`` with a different venue's latency, measured
    live while spot ingestion was still off (T3.0c §6). The message is still
    acked with the rest of its batch (``run_batch_consumer``); dropping it here
    is silent because there is nothing to redeliver it *for*.
    """

    async def handle(deliveries: list[tuple[str, EventEnvelope]]) -> None:
        perpetual_only = [
            (message_id, envelope)
            for message_id, envelope in deliveries
            if envelope.payload.get("market_type", "perpetual") == "perpetual"
        ]
        result = coalesce(perpetual_only)
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
    beta: BetaHealth,
    regime_hourly: RegimeHealth,
) -> None:
    while True:
        await write_heartbeat(
            runtime.redis, runtime, scanner, cycle, consumers, progress, beta, regime_hourly
        )
        await asyncio.sleep(config.heartbeat_s)
