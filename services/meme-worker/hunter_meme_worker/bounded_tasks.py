"""A bounded, tracked set of background tasks (T4.91, risk-engine-guardian's
review): the arm's proposal insert leaves the event lane's shared evaluation
loop, so a slow database never delays the next frame — but never unbounded,
never orphaned, never silent.

- :meth:`BoundedTasks.spawn` refuses (and closes the coroutine) when
  ``limit`` tasks are already in flight — counted ``saturated``, never queued
  behind a slow one;
- a task's exception is caught, logged and counted ``failed`` — it never
  reaches the event loop's "exception was never retrieved";
- :meth:`BoundedTasks.aclose` cancels and awaits what is left (the gate's
  shutdown); :meth:`BoundedTasks.join` waits for it (tests, orderly drains).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from hunter_core.logging import get_logger

logger = get_logger(__name__)

__all__ = ["BoundedTasks"]


class BoundedTasks:
    def __init__(self, *, limit: int, name: str) -> None:
        self._tasks: set[asyncio.Task[None]] = set()
        self._limit, self._name = limit, name
        self.saturated = self.failed = 0

    @property
    def in_flight(self) -> int:
        return len(self._tasks)

    def has_room(self) -> bool:
        return len(self._tasks) < self._limit

    def spawn(self, coro: Coroutine[Any, Any, None]) -> bool:
        """``False`` (the coroutine closed, never run) when the pool is full."""
        if not self.has_room():
            coro.close()
            self.saturated += 1
            return False
        task = asyncio.create_task(self._guard(coro), name=self._name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return True

    async def _guard(self, coro: Coroutine[Any, Any, None]) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.failed += 1
            logger.warning(
                "meme_bounded_task_failed",
                pool=self._name,
                error_type=type(exc).__name__,
                error=str(exc),
            )

    async def join(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def heartbeat_fields(self, prefix: str) -> dict[str, str]:
        return {
            f"{prefix}in_flight": str(self.in_flight),
            f"{prefix}saturated_total": str(self.saturated),
            f"{prefix}failed_total": str(self.failed),
        }
