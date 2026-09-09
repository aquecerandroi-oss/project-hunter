"""One TaskGroup owns every long-lived worker task; an exit is fatal."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory
from hunter_core.domain.enums import MarketType, RiskEventSeverity
from hunter_core.events.outbox import OutboxHealth
from hunter_core.logging import get_logger
from hunter_market_worker.backfill import run_backfill
from hunter_market_worker.config import build_adapter, build_spot_adapter, exchange_code
from hunter_market_worker.funding import run_funding
from hunter_market_worker.fx import run_fx_collector
from hunter_market_worker.heartbeat import (
    HeartbeatState,
    run_heartbeat,
    safe_record_system_event,
)
from hunter_market_worker.ingest import TickCoalescer, coalesce_loop
from hunter_market_worker.outbox import readiness as outbox_readiness
from hunter_market_worker.outbox import run_outbox
from hunter_market_worker.partitions import PartitionReadiness, assert_writable_partitions
from hunter_market_worker.persist import PersistQueues, drain_loop, oi_poll_loop, snapshot_loop
from hunter_market_worker.publication import publication_sessions
from hunter_market_worker.recovery import run_recovery
from hunter_market_worker.spot import SpotStatus, collects_spot, run_spot
from hunter_market_worker.streaming import run_ingest, run_watchdog
from hunter_market_worker.supervision import (
    IngestionHealth,
    Watchdog,
    forever,
    rest_gate_status,
)
from hunter_market_worker.universe import MonitoredUniverse, run_universe

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_market_worker.coverage import CoverageStampFn
logger = get_logger(__name__)


async def run_market(runtime: WorkerRuntime) -> None:
    settings = runtime.settings
    factory = create_session_factory(runtime.engine)
    role = settings.market_role_effective
    logger.info(
        "market_worker_role_selected",
        role=role,
        market_shard=settings.market_shard,
        spot_enabled=settings.market_spot_enabled,
    )
    if role == "spot":
        # T3.0f: a MARKET_ROLE=spot process never runs a perpetual universe,
        # ingest, heartbeat or backfill task -- see _run_spot_process's
        # docstring for exactly what it does run instead.
        if not settings.market_spot_enabled:
            # Deliberately not a startup error (Settings._validate_market_role's
            # own docstring): a legitimate, if inert, configuration logs and
            # idles forever rather than crash-looping.
            logger.warning("market_spot_role_idle_disabled", exchange=exchange_code())
        await _run_spot_process(runtime, factory)
        return
    adapter = build_adapter(exchange_code(), settings, runtime.redis)
    universe, queues, state = MonitoredUniverse(), PersistQueues(), HeartbeatState()
    coalescer, health = TickCoalescer(), IngestionHealth()
    outbox_health, outbox_wake = OutboxHealth(), asyncio.Event()
    # T3.46g: the perpetual and spot ingest tasks each register their own
    # stamp closure here as they start; the coalescer they share reads it
    # right after flushing a cycle's book/ticker, so a reader who sees that
    # write and re-reads the coverage proof finds a cut that already covers
    # it (docs/PIPELINE.md §1-2, hunter_market_worker.coverage module docstring).
    coverage_stamps: dict[MarketType, CoverageStampFn] = {}
    producer = f"market-worker@{runtime.instance}"

    async def warning(message: str) -> None:
        runtime.mark_error()
        # HIGH-2: a database error while merely *recording* the watchdog's
        # warning must not take the whole watchdog task (and therefore the
        # TaskGroup) down with it.
        await safe_record_system_event(
            factory, "connection_watchdog", message, RiskEventSeverity.WARNING
        )

    watchdog = Watchdog(adapter, warning)
    partition_readiness = PartitionReadiness(factory)

    async def partitions() -> bool:
        """Distinct ``__name__`` from ``PartitionReadiness.ready`` (MEDIUM-1):
        registered under this name in ``/ready``'s ``details``, so the payload
        never gets a key literally called ``ready`` that isn't the verdict."""
        return await partition_readiness.ready()

    outbox = outbox_readiness(outbox_health)
    runtime.readiness_checks.extend([health.ingestion, queues.persistence, partitions, outbox])
    # T2.9: a *detail*, not a check. "suspended" means the shared rate-limit
    # coordination is unreachable and this process admits no REST call; the
    # WebSocket keeps ingesting, so readiness stays green and an operator
    # still sees the degradation on /ready (and in the heartbeat hash).
    runtime.status_details["rest_gate"] = lambda: rest_gate_status(adapter)
    # T3.0c: the spot venue, as a *detail* too. "degraded" says the spot socket
    # is reconnecting while the perpetual one is fine — visible without turning
    # a healthy collector red, and "absent" on every shard that does not run it.
    spot_adapter = build_spot_adapter(exchange_code(), settings, runtime.redis)
    spot_status = SpotStatus()
    runtime.status_details["spot"] = spot_status
    token = publication_sessions.set(factory)
    logger.info("market_worker_starting", exchange=adapter.code)
    try:
        # Nothing can be persisted without a partition for *now*: fatal, and the
        # supervisor restarts us (HIGH-3). A missing +1 day lookahead only makes
        # ``/ready`` false — today's collection keeps running, but say so.
        await assert_writable_partitions(factory)
        if await partition_readiness.ready():
            logger.info("partition_lookahead_ready")
        else:
            logger.warning("partition_lookahead_missing")
        async with asyncio.TaskGroup() as group:
            tasks = {
                "funding": run_funding(
                    factory, adapter, runtime.redis, universe, queues, settings, runtime
                ),
                "universe": run_universe(
                    factory, adapter, runtime.redis, settings, universe, runtime
                ),
                "ingest": run_ingest(
                    adapter,
                    runtime.redis,
                    settings,
                    universe,
                    queues,
                    state,
                    runtime,
                    coalescer,
                    health,
                    watchdog,
                    coverage_stamps=coverage_stamps,
                ),
                "coalescer": coalesce_loop(
                    coalescer,
                    runtime.redis,
                    settings,
                    f"market-worker@{runtime.instance}",
                    coverage_stamps=coverage_stamps,
                ),
                "persist": drain_loop(
                    factory, adapter.code, queues, runtime, outbox_wake, producer
                ),
                "outbox": run_outbox(factory, runtime.redis, outbox_health, outbox_wake),
                "snapshots": snapshot_loop(
                    factory, runtime.redis, adapter.code, universe, settings, runtime, queues
                ),
                "open-interest": oi_poll_loop(
                    factory, runtime.redis, adapter, universe, settings, runtime, queues
                ),
                "recovery": run_recovery(factory, adapter, universe, state, runtime),
                # T2.5-backfill: turns `market.backfill.requested` into gap rows
                # the recovery above drains. It never calls REST itself.
                "backfill": run_backfill(
                    factory, adapter, runtime.redis, universe, settings, runtime
                ),
                "heartbeat": run_heartbeat(runtime, adapter, universe, state, factory),
                "watchdog": run_watchdog(watchdog, universe),
                # T3.11a: one USDTBRL collector per venue, never N — the task
                # itself idles on every shard but shard 0 (fx.run_fx_collector).
                "fx": run_fx_collector(factory, runtime.redis, adapter.code, runtime),
                # T3.0c: the whole SPOT path (its own adapter, universe, queue,
                # coverage, heartbeat and recovery) as one subtree, so a spot
                # failure is a spot failure and never a perpetual one. Idles on
                # every shard but 0, like ``fx`` above.
                "spot": run_spot(
                    factory,
                    spot_adapter,
                    runtime.redis,
                    settings,
                    runtime,
                    coalescer,
                    spot_status,
                    outbox_wake=outbox_wake,
                    coverage_stamps=coverage_stamps,
                ),
            }
            for name, coro in tasks.items():
                group.create_task(forever(name, coro), name=f"market-{name}")
    finally:
        publication_sessions.reset(token)
        runtime.readiness_checks.remove(health.ingestion)
        runtime.readiness_checks.remove(queues.persistence)
        runtime.readiness_checks.remove(partitions)
        runtime.readiness_checks.remove(outbox)
        runtime.status_details.pop("rest_gate", None)
        runtime.status_details.pop("spot", None)
        await adapter.aclose()
        if not collects_spot(settings):
            # ``run_spot`` closes the adapter it actually used; a shard that
            # only idled never opened a socket, but the httpx client built by
            # the factory is real and must not leak.
            await spot_adapter.aclose()


async def _run_spot_process(
    runtime: WorkerRuntime, factory: async_sessionmaker[AsyncSession]
) -> None:
    """The whole process body for ``MARKET_ROLE=spot`` (T3.0f).

    The spot data path and nothing else: no perpetual universe, ingest,
    coalescer input, persist queue, recovery, backfill, heartbeat, funding,
    open-interest polling or FX collector. Structurally the minimal shell
    ``run_spot`` (``spot.py``) needs to run stand-alone in its own process:

    - a partitions gate, because spot candles land in the same
      ``candles``/``market_snapshots`` partitioned tables the perpetual path
      writes to;
    - the outbox dispatcher, so this process's own durable events
      (``market.candles.closed``/``.backfilled``, ``market.universe.changed``)
      get swept to Redis -- safe to run alongside every other market-worker
      process's own outbox task, all of them sharing the same ``SKIP LOCKED``
      dispatch (``hunter_core.events.outbox``);
    - the tick coalescer's own flush loop, since this process shares it with
      nothing else (unlike ``run_market``'s perpetual path, where the same
      coalescer instance also drains the perpetual ingest).

    ``run_spot`` itself still gates on :func:`collects_spot`: with
    ``MARKET_SPOT_ENABLED=false`` it idles forever (module docstring), and
    this process's ``/ready`` stays green throughout -- ``database``/``redis``/
    ``partitions``/``outbox`` are the only checks it registers.
    """
    settings = runtime.settings
    spot_adapter = build_spot_adapter(exchange_code(), settings, runtime.redis)
    coalescer = TickCoalescer()
    outbox_health, outbox_wake = OutboxHealth(), asyncio.Event()
    coverage_stamps: dict[MarketType, CoverageStampFn] = {}  # T3.46g, same as run_market's
    spot_status = SpotStatus()
    runtime.status_details["spot"] = spot_status
    # This process's only exchange client is the spot one: its own REST gate
    # is what "rest_gate" means here, exactly parallel to how the
    # perpetual/both path reports its own (single) adapter's.
    runtime.status_details["rest_gate"] = lambda: rest_gate_status(spot_adapter)
    partition_readiness = PartitionReadiness(factory)

    async def partitions() -> bool:
        return await partition_readiness.ready()

    outbox = outbox_readiness(outbox_health)
    runtime.readiness_checks.extend([partitions, outbox])
    token = publication_sessions.set(factory)
    logger.info("market_spot_process_starting", exchange=spot_adapter.code)
    try:
        await assert_writable_partitions(factory)
        if await partition_readiness.ready():
            logger.info("partition_lookahead_ready")
        else:
            logger.warning("partition_lookahead_missing")
        async with asyncio.TaskGroup() as group:
            tasks = {
                "coalescer": coalesce_loop(
                    coalescer,
                    runtime.redis,
                    settings,
                    f"market-worker@{runtime.instance}",
                    coverage_stamps=coverage_stamps,
                ),
                "outbox": run_outbox(factory, runtime.redis, outbox_health, outbox_wake),
                "spot": run_spot(
                    factory,
                    spot_adapter,
                    runtime.redis,
                    settings,
                    runtime,
                    coalescer,
                    spot_status,
                    outbox_wake=outbox_wake,
                    coverage_stamps=coverage_stamps,
                ),
            }
            for name, coro in tasks.items():
                group.create_task(forever(name, coro), name=f"market-{name}")
    finally:
        publication_sessions.reset(token)
        runtime.readiness_checks.remove(partitions)
        runtime.readiness_checks.remove(outbox)
        runtime.status_details.pop("rest_gate", None)
        runtime.status_details.pop("spot", None)
        if not collects_spot(settings):
            # Same rule as the perpetual/both path's own finally: run_spot
            # only closes the adapter it actually used.
            await spot_adapter.aclose()
