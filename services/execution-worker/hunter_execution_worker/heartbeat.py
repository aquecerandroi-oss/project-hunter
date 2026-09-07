"""``hb:execution:paper`` — the wallet's own heartbeat.

The runtime already writes the generic ``hb:{role}:{instance}``. This one is
scoped to the paper wallet and carries what an operator (and Sexta-feira's shift
report) actually needs: the equity that was last written, the kill switch in
force, how many positions are open, and — the one that matters — how long the
oldest fired-but-unfilled protection has been waiting.

"No fills today" is a legitimate result. It is only readable next to the number
of protections that fired and the delay they are sitting on.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, cast

from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_execution_worker.config import HEARTBEAT_KEY

if TYPE_CHECKING:
    from hunter_core.runtime import WorkerRuntime
    from hunter_execution_worker.config import ExecutionConfig
    from hunter_execution_worker.state import CycleHealth

logger = get_logger(__name__)
TTL_S = 60

__all__ = ["run_heartbeat", "write_heartbeat"]


def _stamp(value: object) -> str:
    return "" if value is None else str(value)


async def write_heartbeat(
    runtime: WorkerRuntime, health: CycleHealth, config: ExecutionConfig
) -> None:
    """One ``HSET`` + ``EXPIRE`` of ``hb:execution:paper``."""
    payload = {
        "ts": utcnow().isoformat(),
        "instance": runtime.instance,
        "equity": health.equity,
        "kill_switch": health.kill_switch,
        "open_positions": str(health.open_positions),
        "pending_requests": str(health.pending_requests),
        "unreadable_requests": str(health.unreadable_requests),
        "degraded_protections": str(len(health.degraded_protections)),
        "protection_delay_s": f"{health.protection_delay_s():.1f}",
        "last_mtm": _stamp(health.mtm_written_at),
        "last_protection": _stamp(health.protection_at),
        "last_kill_switch_read": _stamp(health.kill_switch_read_at),
        "errors": str(health.errors),
        "paper_autonomy": str(config.enable_paper_autonomy).lower(),
    }
    await cast("Any", runtime.redis).hset(HEARTBEAT_KEY, mapping=payload)
    await runtime.redis.expire(HEARTBEAT_KEY, TTL_S)


async def run_heartbeat(
    runtime: WorkerRuntime, health: CycleHealth, config: ExecutionConfig
) -> None:
    """Write the heartbeat for ever; a failure is logged, never fatal."""
    while True:
        try:
            await write_heartbeat(runtime, health, config)
        except Exception:
            logger.warning("execution_heartbeat_write_failed")
        await asyncio.sleep(config.heartbeat_interval_s)
