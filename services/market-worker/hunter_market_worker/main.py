"""One TaskGroup owns every long-lived worker task; an exit is fatal."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.db.session import create_session_factory
from hunter_core.domain.enums import RiskEventSeverity
from hunter_core.events.outbox import OutboxHealth
from hunter_core.logging import get_logger
from hunter_market_worker.config import build_adapter, exchange_code
from hunter_market_worker.funding import run_funding
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
from hunter_market_worker.streaming import run_ingest, run_watchdog
from hunter_market_worker.supervision import (
    IngestionHealth,
    Watchdog,
    forever,
    rest_gate_status,
)
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
    outbox_health, outbox_wake = OutboxHealth(), asyncio.Event()
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
                ),
                "coalescer": coalesce_loop(
                    coalescer, runtime.redis, settings, f"market-worker@{runtime.instance}"
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
                "heartbeat": run_heartbeat(runtime, adapter, universe, state, factory),
                "watchdog": run_watchdog(watchdog, universe),
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
        await adapter.aclose()
