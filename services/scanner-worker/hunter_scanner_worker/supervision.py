"""A long-lived task must never return; if it does, that is fatal."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Awaitable

__all__ = ["forever"]


async def forever(name: str, coro: Awaitable[None]) -> None:
    """Run ``coro`` and refuse to let a silent exit look like health.

    A task that returned has stopped doing its job while the process keeps
    reporting itself alive, which is strictly worse than a restart: the
    supervisor cannot act on something that did not die.
    """
    await coro
    raise RuntimeError(f"task {name} exited unexpectedly")
