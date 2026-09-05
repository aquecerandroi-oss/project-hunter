"""One TaskGroup owns every long-lived worker task; an exit is fatal."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.logging import get_logger
from hunter_market_worker.config import build_adapter, exchange_code
from hunter_market_worker.funding import run_funding
from hunter_market_worker.heartbeat import HeartbeatState, record_system_event, run_heartbeat
from hunter_market_worker.ingest import TickCoalescer, coalesce_loop
from hunter_market_worker.partitions import PartitionReadiness, assert_writable_partitions
from hunter_market_worker.persist import PersistQueues, drain_loop, oi_poll_loop, snapshot_loop
from hunter_market_worker.publication import publication_sessions
from hunter_market_worker.recovery import run_recovery
from hunter_market_worker.streaming import run_ingest, run_watchdog
from hunter_market_worker.supervision import IngestionHealth, Watchdog, forever
from hunter_market_worker.universe import MonitoredUniverse, run_universe

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime
logger = get_logger(__name__)


async def run_market(runtime: WorkerRuntime) -> None:
    settings = runtime.settings
    factory = create_session_factory(runtime.engine)
    adapter = build_adapter(exchange_code(), settings, runtime.redis)
    universe, queues, state = MonitoredUniverse(), PersistQueues(), HeartbeatState()
    coalescer, health = TickCoalescer(), IngestionHealth()

    async def warning(message: str) -> None:
        runtime.mark_error()
        await record_system_event(
            factory, "connection_watchdog", message, RiskEventSeverity.WARNING
        )

    watchdog = Watchdog(adapter, warning)
    partitions = PartitionReadiness(factory)
    runtime.readiness_checks.extend([health.ingestion, queues.persistence, partitions.ready])
    token = publication_sessions.set(factory)
    logger.info("market_worker_starting", exchange=adapter.code)
    try:
        # Nothing can be persisted without a partition for *now*: fatal, and the
        # supervisor restarts us (HIGH-3). A missing +1 day lookahead only makes
        # ``/ready`` false — today's collection keeps running, but say so.
        await assert_writable_partitions(factory)
        if await partitions.ready():
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
                ),
                "coalescer": coalesce_loop(
                    coalescer, runtime.redis, settings, f"market-worker@{runtime.instance}"
                ),
                "persist": drain_loop(factory, adapter.code, queues, runtime),
                "snapshots": snapshot_loop(
                    factory, runtime.redis, adapter.code, universe, settings, runtime, queues
                ),
                "open-interest": oi_poll_loop(
                    factory, runtime.redis, adapter, universe, settings, runtime, queues
                ),
                "recovery": run_recovery(factory, adapter, universe, state, runtime),
                "heartbeat": run_heartbeat(runtime, adapter, universe, state, factory),
                "watchdog": run_watchdog(watchdog, universe),
            }
            for name, coro in tasks.items():
                group.create_task(forever(name, coro), name=f"market-{name}")
    finally:
        publication_sessions.reset(token)
        runtime.readiness_checks.remove(health.ingestion)
        runtime.readiness_checks.remove(queues.persistence)
        runtime.readiness_checks.remove(partitions.ready)
        await adapter.aclose()
