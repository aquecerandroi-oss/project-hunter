"""One transaction per cycle: rows and the events that describe them, together.

Everything the scanner concluded in a cycle -- minute snapshots, anomaly
lifecycle, episodes, preserved history samples, the regime, new baseline
revisions -- commits in a single transaction as ``hunter_worker``, with the
outbox rows that announce it (``enqueue_many``). That is what removes "published
but not persisted" and "persisted but not published" from the set of reachable
states, and it is why the dispatcher is a dumb pipe.

Three rules this module exists to enforce:

**ACK after the effect.** The consumers hand over the messages they read; the
ACK happens here, after the commit. A crash between the two redelivers the
message, and the redelivery is a no-op because every effect has a unique key
(the snapshot's ``(market_id, ts)``, the outbox's ``event_id``).

**The baseline lock before the envelope.** ``docs/DATABASE.md`` section 17.2 makes
the writer take ``FOR SHARE`` on every ``baseline_id`` it is about to reference
and re-check that the rows are still there -- a cached baseline may have been
deleted by retention since it was read. Taken once per batch over the union of
the ids, and only for the samples that will actually be stored. A sample whose
baseline vanished is **not** written with the id stripped out: the number was
computed against evidence that is gone, so the market is re-evaluated instead.

**Episode identity is an update, never an insert.** Closing an episode sets
``expired_at`` on the row that owns it; inserting a pre-expired row would not
even collide with the partial unique index, and the Radar would show two.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.outbox import enqueue_many
from hunter_core.logging import get_logger
from hunter_scanner_worker import writers
from hunter_scanner_worker.metrics import scanner_persist_batch_seconds

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_indicators.baselines import BaselineRevision
    from hunter_scanner_worker.state import PendingAck

logger = get_logger(__name__)

DB_ROLE = "hunter_worker"

__all__ = ["WriteBatch", "flush_batch"]


@dataclass
class WriteBatch:
    """Everything one cycle wants to make durable, and what to do afterwards."""

    snapshots: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    anomalies: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    opportunities: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    episode_touches: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    """Counter-only updates from the watchdog: the expiry run broke, and nothing
    that was *observed* changed. A partial row cannot ride in ``opportunities``
    -- that is an upsert of the full column set, and half a row would either be
    rejected or overwrite evidence with defaults."""

    history: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    regime_open: dict[str, Any] | None = None
    regime_close: tuple[UUID, datetime] | None = None
    regime_touch: tuple[UUID, dict[str, Any]] | None = None
    revisions: list[BaselineRevision] = field(default_factory=list["BaselineRevision"])
    events: list[EventEnvelope] = field(default_factory=list[EventEnvelope])
    acks: list[PendingAck] = field(default_factory=list["PendingAck"])
    baseline_ids: set[UUID] = field(default_factory=set[UUID])
    """The union of every ``baseline_id`` the envelopes in this batch name."""

    referenced_by: dict[UUID, set[UUID]] = field(default_factory=dict[UUID, set[UUID]])
    """``market_id -> baseline ids it referenced``, so one vanished baseline
    invalidates exactly the markets that used it."""

    event_market: dict[UUID, UUID] = field(default_factory=dict[UUID, UUID])
    """``event_id -> market_id``. An event is an *announcement of a row*; when the
    row is dropped the announcement has to go with it, or a consumer is told
    about a change nobody persisted."""

    after_commit: list[tuple[UUID | None, Callable[[], None]]] = field(
        default_factory=list["tuple[UUID | None, Callable[[], None]]"]
    )
    """``(market_id, callback)``. The market is what lets an invalidated
    evaluation take its own post-commit promotions down with it -- advancing the
    history mark or the snapshot minute for a sample that was not written would
    make the next cycle skip re-creating it."""

    @property
    def empty(self) -> bool:
        return not (
            self.snapshots
            or self.anomalies
            or self.opportunities
            or self.episode_touches
            or self.history
            or self.regime_open
            or self.regime_close
            or self.regime_touch
            or self.revisions
            or self.events
        )

    def reference(self, market_id: UUID, ids: Sequence[UUID]) -> None:
        if not ids:
            return
        self.baseline_ids.update(ids)
        self.referenced_by.setdefault(market_id, set()).update(ids)


def _drop_invalidated(batch: WriteBatch, missing: set[UUID]) -> set[UUID]:
    """Remove **every** effect of the evaluations whose evidence is gone.

    Not just the opportunity row: the anomaly rows scored beside it, the events
    that announce both, and the post-commit promotions that would tell the next
    cycle the work was done. Dropping only the opportunity would publish
    ``opportunities.updated`` for a row nobody wrote and advance the history mark
    (and the snapshot minute) past a sample that does not exist -- Astra, T2.5
    diff review.
    """
    affected = {market_id for market_id, used in batch.referenced_by.items() if used & missing}
    if not affected:
        return affected
    dropped_ids = {row["id"] for row in batch.opportunities if row["market_id"] in affected}
    batch.opportunities = [row for row in batch.opportunities if row["market_id"] not in affected]
    batch.history = [row for row in batch.history if row["opportunity_id"] not in dropped_ids]
    batch.anomalies = [row for row in batch.anomalies if row["market_id"] not in affected]
    batch.events = [
        event for event in batch.events if batch.event_market.get(event.event_id) not in affected
    ]
    batch.after_commit = [entry for entry in batch.after_commit if entry[0] not in affected]
    logger.warning(
        "scanner_baseline_vanished_before_write",
        markets=len(affected),
        baselines=len(missing),
        dropped_opportunities=len(dropped_ids),
    )
    return affected


async def flush_batch(
    factory: async_sessionmaker[AsyncSession],
    redis: redis_asyncio.Redis,
    batch: WriteBatch,
    *,
    now: datetime | None = None,
) -> set[UUID]:
    """Commit one batch, then ACK. Returns the markets that must be re-evaluated."""
    if batch.empty and not batch.acks:
        return set()
    moment = now or utcnow()
    invalidated: set[UUID] = set()
    with scanner_persist_batch_seconds.time():
        async with role_session(factory, db_role=DB_ROLE) as session:
            surviving = await writers.surviving_baselines(session, batch.baseline_ids)
            missing = batch.baseline_ids - surviving
            if missing:
                invalidated = _drop_invalidated(batch, missing)
            await writers.write_snapshots(session, batch.snapshots)
            await writers.write_anomalies(session, batch.anomalies)
            await writers.write_regime(session, batch)
            await writers.write_opportunities(session, batch.opportunities)
            await writers.touch_episodes(session, batch.episode_touches)
            await writers.write_history(session, batch.history)
            await writers.write_revisions(session, batch.revisions)
            if batch.events:
                await enqueue_many(session, batch.events)
    for _market_id, callback in batch.after_commit:
        callback()
    await _ack_all(redis, batch.acks)
    logger.debug(
        "scanner_batch_committed",
        snapshots=len(batch.snapshots),
        anomalies=len(batch.anomalies),
        opportunities=len(batch.opportunities),
        history=len(batch.history),
        events=len(batch.events),
        acked=len(batch.acks),
        at=moment.isoformat(),
    )
    return invalidated


async def _ack_all(redis: redis_asyncio.Redis, acks: Sequence[PendingAck]) -> None:
    """ACK every message whose effect is now durable.

    Failing to ACK is survivable (the message is redelivered and reprocessed
    into a no-op); failing to *commit* is not, which is why this happens after.
    """
    from hunter_core.events.consume import ack as ack_message

    for pending in acks:
        try:
            await ack_message(
                redis,
                pending.stream,
                pending.group,
                pending.message_id,
                EventEnvelope(
                    event_id=UUID(pending.event_id),
                    type=pending.stream,
                    producer="scanner-worker",
                    key="",
                    payload={},
                ),
            )
        except Exception:
            logger.warning("scanner_ack_failed", stream=pending.stream, id=pending.message_id)
