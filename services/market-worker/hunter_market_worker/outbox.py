"""The market-worker's outbox task: reconcile on boot, sweep forever, report.

All the machinery is generic (:mod:`hunter_core.events.outbox`); what lives
here is this worker's policy — how deep and how old a backlog may get before
``/ready`` goes red, and how the dispatcher is woken by a flush that just
committed.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.events.outbox import OutboxHealth, reconcile, run_dispatcher
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

MAX_PENDING = 500
"""A steady-state backlog: one flush per second, a few hundred markets. Deeper
than this and the dispatcher is not keeping up with the collector."""

MAX_LAG_S = 30.0
"""How old the oldest unpublished event may get. Comfortably above one sweep
(``poll_s`` 1s plus a 5s publication budget) and far under the ``candle closed
-> agent signal`` target of 3s being *chronically* missed, so this trips on a
real stall, not on a hiccup."""

POLL_S = 1.0
"""Backstop cadence. The latency path is the wake event a committed flush sets;
this only covers a lost notification and rows another shard committed."""

__all__ = ["MAX_LAG_S", "MAX_PENDING", "OutboxHealth", "run_outbox", "readiness"]


def readiness(health: OutboxHealth):
    """A ``/ready`` check closing over ``health``.

    Named ``outbox`` in the readiness payload so the red verdict says which
    subsystem is behind.
    """

    async def outbox() -> bool:
        return health.ready(max_pending=MAX_PENDING, max_lag_s=MAX_LAG_S)

    return outbox


async def run_outbox(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    health: OutboxHealth,
    wake: asyncio.Event,
) -> None:
    """Drain whatever the previous process left behind, then sweep forever.

    The reconciliation is what makes a crash between the commit and the
    ``XADD`` invisible to consumers: every event the dead process owed its
    stream is still ``dispatched_at IS NULL`` and goes out now, in
    ``created_at`` order, before this instance publishes anything new.
    """
    try:
        recovered = await reconcile(redis, factory, health=health)
    except Exception:
        # Not fatal: the sweep below picks up exactly the same rows. Losing
        # the boot-time drain only costs latency, and dying here would put the
        # worker in a restart loop while Redis is down.
        logger.exception("market_outbox_reconcile_failed")
    else:
        if recovered:
            logger.info("market_outbox_reconciled", events=recovered)
    await run_dispatcher(redis, factory, health, wake=wake, poll_s=POLL_S)
