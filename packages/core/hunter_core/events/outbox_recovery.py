"""Republishing retained rows: the recovery for a *stream* that was lost.

This is the other half of :mod:`hunter_core.events.outbox`, and it is a
different failure with a different tool. The dispatcher's pending predicate
(``dispatched_at IS NULL``) recovers rows that never reached Redis. It can do
nothing for entries that reached Redis and were then dropped — an ``XTRIM``
past the retention window, a ``FLUSHDB``, a Redis restarted without its dump:
those rows are long marked dispatched, so nothing will ever select them again.

Replaying by time window is the answer, and it is deliberately read-only and
unlocked. Nothing is re-marked and no row is claimed: this competes with no
dispatcher, and consumers de-duplicate on ``event_id`` exactly as they do for
an ordinary redelivery.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.events.outbox_event import envelope_from_row
from hunter_core.events.outbox_metrics import outbox_replayed_total
from hunter_core.events.outbox_store import replay_rows
from hunter_core.events.produce import publish
from hunter_core.events.streams import DEFAULT_MAXLEN
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

REPLAY_LIMIT = 5_000
"""Default ceiling on one replay. A bound, not a promise of completeness —
see :func:`replay_since` on what happens when it is reached."""

PAGE = 20
"""Rows per read. Smaller than a dispatcher micro-batch would need to be:
these transactions take no row locks, so the page size is only about memory
and round trips."""

FALLBACK_MAXLEN = 20_000

__all__ = ["PAGE", "REPLAY_LIMIT", "replay_since"]


def _maxlen(stream: str) -> int:
    return DEFAULT_MAXLEN.get(stream, FALLBACK_MAXLEN)


async def replay_since(
    redis: redis_asyncio.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    since: datetime,
    limit: int,
    db_role: str,
) -> int:
    """Republish retained rows created at or after ``since``. Returns how many.

    Reaching ``limit`` is a **partial** recovery, and saying nothing about it
    would be the real defect: ``since`` is the only knob a caller has, so a
    second call with the same ``since`` republishes the same first page and
    the tail stays unreachable forever. When the ceiling is hit this logs
    ``outbox_replay_truncated`` with ``resume_since`` — the ``created_at`` of
    the last row published, which is where a follow-up call must start.

    Resuming at that instant re-publishes the rows that tie on it. That is the
    safe direction: ties are duplicates the consumer already de-duplicates,
    whereas skipping past them would lose events during a recovery.
    """
    republished = 0
    after: tuple[datetime, int] | None = None
    while republished < limit:
        async with role_session(session_factory, db_role=db_role) as session:
            rows = await replay_rows(session, since, min(PAGE, limit - republished), after=after)
        if not rows:
            break
        for row in rows:
            await publish(redis, row.stream, envelope_from_row(row.payload), _maxlen(row.stream))
            outbox_replayed_total.labels(stream=row.stream).inc()
        republished += len(rows)
        after = (rows[-1].created_at, rows[-1].id)
    if republished >= limit and after is not None:
        logger.warning(
            "outbox_replay_truncated",
            since=since.isoformat(),
            limit=limit,
            events=republished,
            resume_since=after[0],
        )
    else:
        logger.info("outbox_replayed", since=since.isoformat(), events=republished)
    return republished
