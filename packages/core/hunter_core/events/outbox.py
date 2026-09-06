"""The generic transactional outbox: dispatcher, reconciliation, readiness.

ARCHITECTURE.md §5.1 and the M2 joint decision (T2.9). The producer's
transaction only *queues* the event (:func:`enqueue`, re-exported here); this
module is what puts it on the stream. That split is what makes "published" and
"persisted" impossible to disagree on:

- died **before the commit** — neither the business row nor the event exists,
  and the source message is redelivered;
- died **between the commit and the ``XADD``** — the row is still pending and
  the next sweep (or :func:`reconcile` at startup) publishes it;
- died **after the ``XADD``, before ``dispatched_at``** — the event is
  published a second time. Delivery is at-least-once by construction: Redis 7
  has no idempotent ``XADD``, so physical de-duplication does not exist and is
  not claimed. What is guaranteed is that the *effect* happens once — the
  envelope is byte-for-byte identical (same deterministic ``event_id``), and
  ``hunter_core.events.consume`` filters an already-processed ``event_id``
  before the caller ever sees it, on top of the unique key the durable effect
  itself carries in Postgres.

A lost **stream** (``XTRIM``, flush) is a different failure and needs a
different tool: those rows are marked dispatched, so the pending predicate can
never bring them back. :func:`reconcile` with ``since=`` republishes a window
of retained rows for exactly that case.

Two neighbours carry the rest: :mod:`hunter_core.events.outbox_health` owns the
backlog snapshot and the readiness verdict, and
:mod:`hunter_core.events.outbox_recovery` owns the time-window replay. Both are
re-exported here, so ``from hunter_core.events.outbox import ...`` stays the one
import a worker needs.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.events.outbox_event import (
    build_envelope,
    envelope_from_row,
    event_id_for,
)
from hunter_core.events.outbox_health import (
    STALE_SWEEP_FACTOR,
    OutboxHealth,
    refresh_health,
)
from hunter_core.events.outbox_metrics import (
    outbox_dispatch_failures_total,
    outbox_dispatched_total,
)
from hunter_core.events.outbox_recovery import REPLAY_LIMIT, replay_since
from hunter_core.events.outbox_store import (
    UNPUBLISHABLE_ATTEMPTS,
    PendingRow,
    claim_pending,
    enqueue,
    enqueue_many,
    mark_dispatched,
    prune_dispatched,
    record_failure,
)
from hunter_core.events.produce import publish
from hunter_core.events.streams import DEFAULT_MAXLEN
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = get_logger(__name__)

BATCH = 100
"""Rows one :func:`dispatch_pending` call may publish."""

MICRO_BATCH = 20
"""Rows per transaction. The batch above is a *work* budget, not a promise to
hold 20x Redis round trips in one transaction: the row locks and the pooled
connection are held for the publications of one micro-batch only (Astra,
T2.9 round 1 — ``statement_timeout`` bounds SQL statements, never the wait on
Redis between them, so a stalled Redis could otherwise pin a transaction for
minutes while the persist queue ages out behind it)."""

BUDGET_S = 5.0
"""Wall-clock ceiling for one sweep. Enforced by bounding the publication
itself, not merely by checking the clock before starting one: the Redis client
retries three times on a 5s socket timeout, so an ``XADD`` begun with 100ms of
budget left could otherwise hold the transaction (and its row locks) for ~20s
past the ceiling this constant advertises (Astra, T2.9 round 2)."""

MIN_PUBLISH_S = 0.5
"""Budget below which a publication is not even started — beginning one that
is certain to be cut off would only burn an ``attempts`` increment."""

FALLBACK_MAXLEN = 20_000

__all__ = [
    "BATCH",
    "BUDGET_S",
    "MICRO_BATCH",
    "STALE_SWEEP_FACTOR",
    "UNPUBLISHABLE_ATTEMPTS",
    "OutboxHealth",
    "build_envelope",
    "dispatch_pending",
    "enqueue",
    "enqueue_many",
    "event_id_for",
    "REPLAY_LIMIT",
    "prune_dispatched",
    "reconcile",
    "refresh_health",
    "run_dispatcher",
]


def _maxlen(stream: str) -> int:
    return DEFAULT_MAXLEN.get(stream, FALLBACK_MAXLEN)


async def _fail(
    session: AsyncSession,
    row: PendingRow,
    reason: str,
    health: OutboxHealth,
    *,
    permanent: bool = False,
) -> None:
    await record_failure(session, row.id, reason, permanent=permanent)
    outbox_dispatch_failures_total.labels(stream=row.stream).inc()
    health.failures += 1


async def _publish_micro_batch(
    redis: redis_asyncio.Redis,
    session: AsyncSession,
    rows: list[PendingRow],
    deadline: float,
    health: OutboxHealth,
    skipped: set[int],
) -> tuple[int, bool]:
    """Publish ``rows`` and mark what reached the stream, in one transaction.

    Returns ``(published, stop)``. A transport failure stops the whole sweep
    (a dead Redis will not heal within it) but keeps every publication that
    already succeeded: the marks and the failed row's ``attempts``/
    ``last_error`` commit together. A row this call could not publish is added
    to ``skipped`` so the rest of the sweep steps over it instead of
    re-selecting the same head of the queue forever.
    """
    sent: list[int] = []
    stop = False
    for row in rows:
        remaining = deadline - time.monotonic()
        if remaining < MIN_PUBLISH_S:
            stop = True
            break
        try:
            envelope = envelope_from_row(row.payload)
        except ValueError as exc:
            # Unpublishable as it stands: count the attempt, keep the reason,
            # and step over it — one poisoned row must not block the stream.
            # The row is deliberately *not* marked dispatched; it stays for
            # diagnosis and for a later attempt after the payload is fixed.
            #
            # ``warning``, not ``exception``: the traceback is always the same
            # three frames of pydantic and says nothing the message does not,
            # while a row that stays pending is re-examined once per sweep —
            # every second, forever, until someone fixes it. One line per row
            # per sweep is the budget; a stack trace per row per second is how
            # a single bad payload buries every other log a service emits.
            logger.warning(
                "outbox_row_unreadable",
                event_id=str(row.event_id),
                stream=row.stream,
                error=str(exc),
            )
            await _fail(session, row, "payload is not an envelope", health, permanent=True)
            skipped.add(row.id)
            continue
        try:
            await asyncio.wait_for(
                publish(redis, row.stream, envelope, _maxlen(row.stream)), remaining
            )
        except TimeoutError:
            # The publication may or may not have landed; treating it as
            # unsent is the safe half of at-least-once.
            logger.warning("outbox_publish_budget_exceeded", stream=row.stream)
            await _fail(session, row, f"publication exceeded the {remaining:.1f}s budget", health)
            skipped.add(row.id)
            stop = True
            break
        except Exception as exc:
            logger.warning("outbox_publish_failed", stream=row.stream, event_id=str(row.event_id))
            await _fail(session, row, str(exc), health)
            skipped.add(row.id)
            stop = True
            break
        sent.append(row.id)
        outbox_dispatched_total.labels(stream=row.stream).inc()
    await mark_dispatched(session, sent, at=utcnow())
    health.dispatched += len(sent)
    return len(sent), stop


async def dispatch_pending(
    redis: redis_asyncio.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    batch: int = BATCH,
    micro_batch: int = MICRO_BATCH,
    budget_s: float = BUDGET_S,
    health: OutboxHealth | None = None,
    db_role: str = "hunter_worker",
) -> int:
    """Publish pending rows in ``created_at`` order. Returns how many were sent.

    **``created_at`` order is best-effort enqueue order, and nothing more.** It
    is not commit order and no consumer may depend on it:

    - ``created_at`` defaults to ``now()``, which in Postgres is the start of
      the *transaction*. A long transaction that queues an event last can
      therefore stamp it earlier than an event a short transaction queued and
      committed while the first was still open;
    - the rows only become visible at commit, so a sweep can publish B and then
      publish A behind it on the next pass, with ``A.created_at < B.created_at``;
    - N shards sweep concurrently under ``SKIP LOCKED``, each taking a disjoint
      slice; the interleaving of their ``XADD``s is whatever the network gives;
    - a row that failed to publish is stepped over for the rest of the sweep and
      goes out after rows created later than it.

    Ordering is chosen because draining oldest-first bounds the *age* of the
    backlog, which is what readiness measures — not to give anyone a sequence.
    Consumers order by the business timestamps inside the payload (a candle's
    ``open_time``, a funding ``ts``) and de-duplicate on ``event_id``; per-key
    sequencing, if it is ever needed, has to be built on those, not on this.
    """
    health = health or OutboxHealth()
    deadline = time.monotonic() + budget_s
    published = 0
    skipped: set[int] = set()
    while published < batch and deadline - time.monotonic() >= MIN_PUBLISH_S:
        want = min(micro_batch, batch - published)
        async with role_session(session_factory, db_role=db_role) as session:
            rows = await claim_pending(session, want, exclude_ids=skipped)
            if not rows:
                break
            sent, stop = await _publish_micro_batch(redis, session, rows, deadline, health, skipped)
        published += sent
        if stop or len(rows) < want:
            break
    await refresh_health(session_factory, health, db_role=db_role)
    return published


async def reconcile(
    redis: redis_asyncio.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    since: datetime | None = None,
    limit: int = REPLAY_LIMIT,
    health: OutboxHealth | None = None,
    db_role: str = "hunter_worker",
) -> int:
    """Postgres → stream, at startup and on demand.

    Default (``since=None``): drain everything still ``dispatched_at IS NULL``,
    sweeping until a pass publishes nothing. That is the "died between the
    commit and the ``XADD``" recovery, and it is why a worker can be killed at
    any instant without an event going missing.

    With ``since``: republish retained rows created at or after that instant
    **whether or not they were dispatched** — the recovery for a stream that
    was trimmed or flushed out from under its consumers. Nothing is re-marked;
    consumers de-duplicate on ``event_id`` exactly as they do for a redelivery.
    Bounded by ``limit``: reaching it is a partial recovery and logs
    ``outbox_replay_truncated`` with the ``resume_since`` to continue from
    (:func:`hunter_core.events.outbox_recovery.replay_since`).
    """
    if since is None:
        total = 0
        while True:
            sent = await dispatch_pending(
                redis, session_factory, health=health, db_role=db_role, budget_s=BUDGET_S
            )
            total += sent
            if sent == 0:
                return total
    return await replay_since(redis, session_factory, since, limit, db_role)


async def run_dispatcher(
    redis: redis_asyncio.Redis,
    session_factory: async_sessionmaker[AsyncSession],
    health: OutboxHealth,
    *,
    wake: asyncio.Event | None = None,
    poll_s: float = 1.0,
    error_backoff_s: float = 5.0,
    db_role: str = "hunter_worker",
) -> None:
    """Sweep forever. Postgres or Redis being down is a backoff, never a death.

    ``wake`` lets a producer that just committed ask for an immediate sweep
    instead of waiting out ``poll_s`` — the latency path for closed candles.
    The producer never publishes on its own hot path (a stalled Redis must not
    slow the persist loop down); it only sets the event.
    """
    while True:
        try:
            await dispatch_pending(redis, session_factory, health=health, db_role=db_role)
        except Exception:
            logger.exception("outbox_sweep_failed")
            await asyncio.sleep(error_backoff_s)
            continue
        if wake is None:
            await asyncio.sleep(poll_s)
            continue
        try:
            await asyncio.wait_for(wake.wait(), poll_s)
        except TimeoutError:
            pass
        wake.clear()
