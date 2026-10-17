"""Supervision of the on-chain fallback's child tasks (H-037, code review R2).

Without it an exception in a child task would end the fallback silently while the stream looked alive.
:func:`supervise` runs a body forever: a crash (or an unexpected end, for a body that must not end) is
reported through ``on_crash`` — the caller counts it, names the gap and marks the fallback degraded so
the REST recovery runs — and the body restarts after a capped exponential backoff.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from hunter_core.logging import get_logger

logger = get_logger(__name__)

BACKOFF_MAX_S = 30.0

__all__ = ["supervise"]


async def supervise(
    name: str,
    body: Callable[[], Awaitable[None]],
    *,
    restart_on_return: bool,
    on_crash: Callable[[str], None],
    sleep: Callable[[float], Awaitable[None]],
) -> None:
    attempt = 0
    while True:
        try:
            await body()
            if not restart_on_return:
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the class only: never the text
            logger.error("leader_chain_task_crashed", task=name, error=type(exc).__name__)
        on_crash(name)
        await sleep(min(1.0 * 2 ** min(attempt, 30), BACKOFF_MAX_S))
        attempt += 1
