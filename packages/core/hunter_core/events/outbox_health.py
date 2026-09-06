"""How far behind the outbox is — the snapshot ``/ready`` and Prometheus read.

Separate from :mod:`hunter_core.events.outbox` because it answers a different
question. The dispatcher's job is to put rows on a stream; this module's job is
to say, honestly, whether anybody should still trust the process doing it. The
two failure modes that matter here are both about *lying*:

- **green from a snapshot nobody took.** If the backlog query has failed since
  boot (a missing ``GRANT`` on ``outbox_events``, say, with the database health
  check and the producers' inserts still working), a verdict derived from
  "nothing observed yet" would answer green forever. The startup grace is
  therefore bounded (Astra, T2.9 diff review);
- **red for something red cannot fix.** A row whose payload is not an envelope
  will never publish, no matter how healthy the process is. Counting it as
  backlog would pin ``/ready`` red until a human edits a JSONB column, and by
  the second day nobody would read that red as an outage any more. It is
  counted apart, exported as ``hunter_outbox_unpublishable``, and votes on
  nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from hunter_core.db.models.system import OutboxEvent
from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.events.outbox_metrics import (
    outbox_oldest_pending_seconds,
    outbox_pending,
    outbox_unpublishable,
)
from hunter_core.events.outbox_store import UNPUBLISHABLE_ATTEMPTS, UNPUBLISHABLE_MARK

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

STALE_SWEEP_FACTOR = 3.0
"""Multiple of ``max_lag_s`` after which a health snapshot is too old to vote
green: a readiness verdict must not coast on the last successful observation
while the query that produces it keeps failing."""

__all__ = ["STALE_SWEEP_FACTOR", "OutboxHealth", "PendingStats", "pending_stats", "refresh_health"]


@dataclass(frozen=True)
class PendingStats:
    """What the backlog looks like right now — the readiness inputs.

    ``pending`` and ``oldest_pending`` describe work the dispatcher can still
    finish. ``unpublishable`` is counted separately and votes on nothing: those
    rows are reported (metric and log), never dropped, and never allowed to
    make a service look broken for a defect that retrying cannot fix.
    """

    pending: int
    oldest_pending: datetime | None
    unpublishable: int


def _unpublishable(after: int) -> ColumnElement[bool]:
    """Abandoned = declared permanent *and* retried ``after`` times.

    ``coalesce`` and not a bare ``LIKE``: ``last_error`` is nullable and ``NULL
    LIKE 'x%'`` is ``NULL``, so the negation below would be ``NULL`` too and
    every never-failed row would fall out of *both* counts — a backlog that
    reports itself empty.
    """
    return func.coalesce(OutboxEvent.last_error, "").startswith(UNPUBLISHABLE_MARK) & (
        OutboxEvent.attempts >= after
    )


async def pending_stats(
    session: AsyncSession, *, unpublishable_after: int = UNPUBLISHABLE_ATTEMPTS
) -> PendingStats:
    """Split the undispatched rows into "still owed" and "abandoned".

    One statement, three aggregates, so the two counts always describe the same
    instant — reading them separately would let a row be missing from both, or
    counted in both, exactly while a sweep is marking it.
    """
    abandoned = _unpublishable(unpublishable_after)
    row = (
        await session.execute(
            select(
                func.count().filter(~abandoned),
                func.min(OutboxEvent.created_at).filter(~abandoned),
                func.count().filter(abandoned),
            ).where(OutboxEvent.dispatched_at.is_(None))
        )
    ).one()
    oldest: datetime | None = row[1]
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    return PendingStats(pending=int(row[0]), oldest_pending=oldest, unpublishable=int(row[2]))


@dataclass
class OutboxHealth:
    """How far behind the dispatcher is — shared with ``/ready``."""

    pending: int = 0
    oldest_pending: datetime | None = None
    last_sweep_at: datetime | None = None
    dispatched: int = 0
    failures: int = 0
    unpublishable: int = 0
    """Pending rows the dispatcher declared permanently broken. Reported, never
    dropped, and deliberately absent from :meth:`ready` — see this module's
    docstring."""

    unpublishable_after: int = UNPUBLISHABLE_ATTEMPTS
    """How many failed attempts before a permanently-broken row is reclassified.
    A worker with a different tolerance sets it on its own ``OutboxHealth``."""

    started_at: datetime = field(default_factory=utcnow)
    """When this snapshot began waiting for its first observation. Bounds the
    startup grace below, so "not observed yet" cannot mean "green forever"."""

    def lag_s(self, *, now: datetime | None = None) -> float:
        """Age of the oldest undispatched row, in seconds (0 when empty)."""
        if self.oldest_pending is None:
            return 0.0
        return ((now or utcnow()) - self.oldest_pending).total_seconds()

    def ready(self, *, max_pending: int, max_lag_s: float, now: datetime | None = None) -> bool:
        """Red once the backlog is too deep, too old, or no longer observed.

        The first two because they are different failures: a burst the sweep is
        still working through is deep and young, while a Redis that stopped
        accepting writes is shallow and old. The third because a snapshot that
        stopped being refreshed — or was never taken at all — would otherwise
        keep answering green from numbers nobody stands behind.
        """
        if self.pending > max_pending or self.lag_s(now=now) > max_lag_s:
            return False
        # A *bounded* startup grace, not an open one: until the first sweep
        # lands there is no verdict to give, but a process whose backlog query
        # never once succeeded is not healthy — it is blind, and answering
        # green would hide exactly the failure this check exists to surface.
        reference = self.last_sweep_at or self.started_at
        age = ((now or utcnow()) - reference).total_seconds()
        return age <= max_lag_s * STALE_SWEEP_FACTOR


async def refresh_health(
    session_factory: async_sessionmaker[AsyncSession],
    health: OutboxHealth,
    *,
    db_role: str = "hunter_worker",
) -> OutboxHealth:
    """Re-read the pending backlog into ``health`` and the metrics."""
    async with role_session(session_factory, db_role=db_role) as session:
        stats = await pending_stats(session, unpublishable_after=health.unpublishable_after)
    health.pending = stats.pending
    health.oldest_pending = stats.oldest_pending
    health.unpublishable = stats.unpublishable
    health.last_sweep_at = utcnow()
    outbox_pending.set(health.pending)
    outbox_oldest_pending_seconds.set(health.lag_s())
    outbox_unpublishable.set(health.unpublishable)
    return health
