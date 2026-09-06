"""``hb:strategy:shadow`` — the Lab's own heartbeat.

The runtime already writes the generic ``hb:{role}:{instance}``. This one is
scoped to the experiment and carries what an operator (and Sexta-feira's shift
report) actually needs to see: how many bars were evaluated and with which
outcome per state, how many trackings are open, and how far behind the outbox
is. Zero signals is a valid result — but only readable next to the number of
evaluations that produced it.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

import orjson

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_strategy_worker.config import HEARTBEAT_KEY
from hunter_strategy_worker.tracking_repo import load_open_trackings

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime
    from hunter_strategy_worker.config import ShadowConfig
    from hunter_strategy_worker.consumer import ConsumerHealth
    from hunter_strategy_worker.outbox import OutboxHealth

logger = get_logger(__name__)
INTERVAL_S = 10
TTL_S = 60

__all__ = ["run_heartbeat", "write_heartbeat"]


async def write_heartbeat(
    runtime: WorkerRuntime,
    config: ShadowConfig,
    consumer: ConsumerHealth,
    outbox: OutboxHealth,
    *,
    open_trackings: int | None = None,
) -> None:
    """One ``HSET`` + ``EXPIRE`` of ``hb:strategy:shadow``."""
    payload = {
        "ts": utcnow().isoformat(),
        "instance": runtime.instance,
        "cohort": config.cohort,
        "evaluated_bars": str(consumer.evaluated_bars),
        "evaluations_by_state": orjson.dumps(consumer.states).decode(),
        "errors": str(consumer.errors),
        "outbox_pending": str(outbox.pending),
        "outbox_lag_s": f"{outbox.lag_s():.1f}",
        "open_trackings": "" if open_trackings is None else str(open_trackings),
        "last_iteration": (
            consumer.last_iteration_at.isoformat() if consumer.last_iteration_at else ""
        ),
    }
    await cast("Any", runtime.redis).hset(HEARTBEAT_KEY, mapping=payload)
    await runtime.redis.expire(HEARTBEAT_KEY, TTL_S)


async def run_heartbeat(
    runtime: WorkerRuntime,
    config: ShadowConfig,
    consumer: ConsumerHealth,
    outbox: OutboxHealth,
) -> None:
    """Write the heartbeat forever; a failure is logged, never fatal."""
    factory = None
    while True:
        open_trackings: int | None = None
        try:
            if factory is None:
                from hunter_core.db.session import create_session_factory

                factory = create_session_factory(runtime.engine)
            async with role_session(factory, db_role="hunter_worker") as session:
                open_trackings = len(await load_open_trackings(session, limit=10_000))
        except Exception:
            logger.warning("shadow_heartbeat_count_failed")
        try:
            await write_heartbeat(runtime, config, consumer, outbox, open_trackings=open_trackings)
        except Exception:
            logger.warning("shadow_heartbeat_write_failed")
        await asyncio.sleep(INTERVAL_S)
