"""The transactional-outbox dispatcher — SHADOW-LAB.md §6, DATABASE.md §16.4.

The decision transaction only *queues* the event; this loop is what puts it on
``shadow.signals.emitted``. That split is what makes "published" and "persisted"
impossible to disagree on, and it is why a crash anywhere in the sequence is
recoverable:

- died before the commit: nothing happened, the message is redelivered;
- died between the commit and the publication: the row is still pending and the
  next sweep publishes it;
- died after the publication and before ``dispatched_at`` was written: the event
  is published twice, and the consumer de-duplicates on ``event_id`` (which is
  the signal id — one identity end to end).

The pending predicate is ``dispatched_at IS NULL``, never "id > watermark": the
sequence has gaps and its order is not commit order, so a cursor would step
over a transaction that took a lower id and committed later.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select, update

from hunter_core.db.models.agents_shadow import ShadowOutbox
from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import publish
from hunter_core.events.streams import DEFAULT_MAXLEN
from hunter_core.logging import get_logger
from hunter_strategy_worker.config import PRODUCER
from hunter_strategy_worker.metrics import shadow_outbox_dispatched_total, shadow_outbox_pending

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_core.runtime import WorkerRuntime
    from hunter_strategy_worker.config import ShadowConfig

logger = get_logger(__name__)
BATCH = 100

__all__ = ["OutboxHealth", "dispatch_once", "run_outbox"]


@dataclass
class OutboxHealth:
    """Shared readiness view: how far behind the dispatcher is."""

    oldest_pending: datetime | None = None
    pending: int = 0
    last_sweep_at: datetime | None = None

    def lag_s(self, *, now: datetime | None = None) -> float:
        if self.oldest_pending is None:
            return 0.0
        return ((now or utcnow()) - self.oldest_pending).total_seconds()


async def _pending(session: AsyncSession) -> list[Any]:
    return list(
        (
            await session.execute(
                select(
                    ShadowOutbox.id,
                    ShadowOutbox.event_id,
                    ShadowOutbox.stream,
                    ShadowOutbox.payload,
                    ShadowOutbox.created_at,
                )
                .where(ShadowOutbox.dispatched_at.is_(None))
                .order_by(ShadowOutbox.created_at, ShadowOutbox.id)
                .limit(BATCH)
            )
        ).all()
    )


async def dispatch_once(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    health: OutboxHealth,
) -> int:
    """Publish every pending row once. Returns how many reached the stream."""
    async with role_session(factory, db_role="hunter_worker") as session:
        rows = await _pending(session)
    published = 0
    for row in rows:
        envelope = EventEnvelope(
            event_id=row.event_id,
            type=row.stream,
            producer=PRODUCER,
            key=str(row.payload.get("symbol") or row.event_id),
            payload=row.payload,
        )
        try:
            await publish(redis, row.stream, envelope, DEFAULT_MAXLEN.get(row.stream, 20_000))
        except Exception as exc:
            logger.warning("shadow_outbox_publish_failed", event_id=str(row.event_id))
            async with role_session(factory, db_role="hunter_worker") as session:
                await session.execute(
                    update(ShadowOutbox)
                    .where(ShadowOutbox.id == row.id)
                    .values(attempts=ShadowOutbox.attempts + 1, last_error=str(exc)[:500])
                )
            continue
        async with role_session(factory, db_role="hunter_worker") as session:
            await session.execute(
                update(ShadowOutbox)
                .where(ShadowOutbox.id == row.id, ShadowOutbox.dispatched_at.is_(None))
                .values(dispatched_at=utcnow(), attempts=ShadowOutbox.attempts + 1)
            )
        published += 1
        shadow_outbox_dispatched_total.labels(stream=row.stream).inc()
    async with role_session(factory, db_role="hunter_worker") as session:
        summary = (
            await session.execute(
                select(func.min(ShadowOutbox.created_at), func.count()).where(
                    ShadowOutbox.dispatched_at.is_(None)
                )
            )
        ).one()
    health.oldest_pending, health.pending = summary[0], int(summary[1])
    health.last_sweep_at = utcnow()
    shadow_outbox_pending.set(health.pending)
    return published


async def run_outbox(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    runtime: WorkerRuntime,
    config: ShadowConfig,
    health: OutboxHealth,
) -> None:
    """Sweep forever. Postgres or Redis being down is a backoff, never a death."""
    while True:
        try:
            sent = await dispatch_once(factory, redis, health)
            if sent:
                runtime.mark_success()
        except Exception:
            runtime.mark_error()
            logger.exception("shadow_outbox_sweep_failed")
            await asyncio.sleep(min(30.0, config.outbox_poll_s * 10))
            continue
        await asyncio.sleep(config.outbox_poll_s)
