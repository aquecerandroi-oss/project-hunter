"""The SQL around the outbox queue: write, claim, mark, prune.

The row shape is fixed by ``outbox_events`` (T2.1, ``db/models/system.py``):
``(event_id, stream, payload, created_at, dispatched_at, attempts, last_error)``.
What a row *means* — its identity and the envelope it carries — lives next
door in :mod:`hunter_core.events.outbox_event`; this module never decides what
an event is, only what happens to it in Postgres.

Two predicates carry the whole design, and neither is a watermark over ``id``
(the sequence has gaps and its order is not commit order): **pending** is
``dispatched_at IS NULL``, and **prunable** is ``dispatched_at < older_than``,
the retention job's input (DATABASE.md §1.3). Counting the pending rows — and
splitting off the ones declared permanently broken, :data:`UNPUBLISHABLE_MARK` —
is :mod:`hunter_core.events.outbox_health`, because those numbers exist to be
interpreted as a verdict and that interpretation belongs with them.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import delete, literal, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.system import OutboxEvent
from hunter_core.events.outbox_event import build_envelope, outbox_row

if TYPE_CHECKING:
    from sqlalchemy import CursorResult, Select
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.events.envelope import EventEnvelope

_ERROR_MAX_CHARS = 500

UNPUBLISHABLE_MARK = "unpublishable: "
"""Prefix :func:`record_failure` writes when the failure is a property of the
**row**, not of the transport — today only "this payload is not an envelope".

Inferring it from ``attempts`` instead would misread a Redis outage, which
fails the same row on every sweep, as N individual defects, and take the whole
backlog out of the readiness verdict exactly when it matters (PIPELINE.md
§10b). A permanent defect is *declared*, and only a declaration counts."""

UNPUBLISHABLE_ATTEMPTS = 5
"""Failed attempts before a row marked permanently broken stops voting on
readiness. Not zero on purpose: the first failures are still reported as a
backlog, so a bug that suddenly makes every payload unreadable is visible as an
outage before it is reclassified as N individual defects."""

PRUNE_BATCH = 5_000
"""Rows one :func:`prune_dispatched` statement may delete. A ceiling on the
lock footprint and the WAL of a single transaction, not on the retention job:
the job calls this in a loop until it returns less than it asked for."""

__all__ = [
    "PRUNE_BATCH",
    "UNPUBLISHABLE_ATTEMPTS",
    "UNPUBLISHABLE_MARK",
    "PendingRow",
    "claim_pending",
    "enqueue",
    "enqueue_many",
    "mark_dispatched",
    "permanent_failure",
    "prunable_ids",
    "prune_dispatched",
    "record_failure",
    "transient_failure",
    "replay_rows",
]


def permanent_failure(reason: str) -> str:
    """Tag ``reason`` as a defect of the row itself (see :data:`UNPUBLISHABLE_MARK`)."""
    return f"{UNPUBLISHABLE_MARK}{transient_failure(reason)}"


def transient_failure(reason: str) -> str:
    """Strip the mark from a reason nobody declared permanent.

    The mark is a *classification*, so it has to be reserved: ``last_error``
    otherwise holds whatever a driver said, and an exception whose text happened
    to start with it would take its own row out of the readiness verdict
    (Astra, T2.9b review). Stripping is a loop because one removal would leave
    ``"unpublishable: unpublishable: x"`` still imitating it.
    """
    while reason.startswith(UNPUBLISHABLE_MARK):
        reason = reason.removeprefix(UNPUBLISHABLE_MARK)
    return reason


async def enqueue(
    session: AsyncSession,
    stream: str,
    event_id: UUID,
    payload: dict[str, Any],
    *,
    producer: str,
    key: str,
    ts: datetime | None = None,
) -> EventEnvelope:
    """Queue one event **inside the caller's transaction**.

    No commit and no flush of its own: the row lands (or does not) exactly
    with the business row it describes. That single fact is what removes
    "published but not persisted" and "persisted but not published" from the
    set of reachable states.

    Prefer :func:`enqueue_many` whenever a transaction queues more than one
    event: this issues a statement per call.
    """
    envelope = build_envelope(stream, event_id, payload, producer=producer, key=key, ts=ts)
    await enqueue_many(session, [envelope])
    return envelope


async def enqueue_many(session: AsyncSession, envelopes: Sequence[EventEnvelope]) -> int:
    """Queue every envelope in **one** statement, in the caller's transaction.

    One multi-row ``INSERT ... ON CONFLICT DO NOTHING`` per flush, exactly like
    the market-data upserts next to it (``persist_rows`` module docstring,
    CRITICAL-1/H6). A statement per event was measured costing the market-worker
    ~200 extra round trips at every minute boundary — inside the flush
    transaction, on the drain's hot path, where it pushed the persistence
    readiness check red.

    Duplicates inside one batch are collapsed first: a single-statement ``DO
    NOTHING`` keeps the *first* occurrence, and the identity is deterministic,
    so which one survives is irrelevant — but sending it twice is not.
    """
    if not envelopes:
        return 0
    rows = {envelope.event_id: outbox_row(envelope) for envelope in envelopes}
    await session.execute(
        pg_insert(OutboxEvent)
        .values(list(rows.values()))
        .on_conflict_do_nothing(index_elements=["event_id"])
    )
    return len(rows)


@dataclass(frozen=True)
class PendingRow:
    """One claimed row, detached from the ORM so it can outlive the session."""

    id: int
    event_id: UUID
    stream: str
    payload: dict[str, Any]
    created_at: datetime


def _rows(result: Any) -> list[PendingRow]:
    return [
        PendingRow(
            id=row.id,
            event_id=row.event_id,
            stream=row.stream,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in result.all()
    ]


_COLUMNS = (
    OutboxEvent.id,
    OutboxEvent.event_id,
    OutboxEvent.stream,
    OutboxEvent.payload,
    OutboxEvent.created_at,
)


async def claim_pending(
    session: AsyncSession, limit: int, *, exclude_ids: Collection[int] = ()
) -> list[PendingRow]:
    """Lock and return up to ``limit`` undispatched rows, oldest first.

    ``FOR UPDATE ... SKIP LOCKED`` is what makes N dispatchers (one per shard)
    safe without a leader election: each transaction takes a disjoint slice,
    and a dispatcher that dies simply releases its rows for the next sweep. A
    leader lock with a TTL cannot do that — it can expire while the previous
    holder is still publishing.

    The predicate is ``dispatched_at IS NULL``, never ``id > watermark``: the
    sequence has gaps and its order is not commit order, so a cursor would
    step over a transaction that took a lower id and committed later. Rows
    already declared unpublishable are **not** excluded here: a payload that
    someone repairs has to go out on the next sweep without an operator
    remembering a second step. They are excluded from the *verdict*, not from
    the work.

    ``exclude_ids`` is how one sweep steps *over* rows it already examined and
    could not publish (an unreadable payload stays pending on purpose). Without
    it, a micro-batch of unpublishable rows is re-selected by every following
    transaction of the same sweep and a valid row behind them never goes out —
    the poison-pill head-of-line block (Astra, T2.9 round 2).
    """
    statement = select(*_COLUMNS).where(OutboxEvent.dispatched_at.is_(None))
    if exclude_ids:
        statement = statement.where(OutboxEvent.id.notin_(exclude_ids))
    return _rows(
        await session.execute(
            statement.order_by(OutboxEvent.created_at, OutboxEvent.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )


async def replay_rows(
    session: AsyncSession,
    since: datetime,
    limit: int,
    *,
    after: tuple[datetime, int] | None = None,
) -> list[PendingRow]:
    """Rows created at or after ``since``, **dispatched or not**, oldest first.

    The recovery path for a stream that was lost rather than a row that was
    never sent: an ``XTRIM``/flush drops entries whose rows are long marked
    ``dispatched_at``, so the pending predicate can never bring them back.
    Read-only and unlocked — this republishes, it does not re-mark.

    ``after`` is the **whole** sort key of the last row of the previous page,
    not just its id. ``id`` alone is not a cursor for this ordering: a
    transaction that started earlier can commit later and take a higher id, so
    a page can legitimately end on a high id and the next row still have a
    lower one — ``id > after_id`` silently skipped it (Astra, T2.9 round 2).
    """
    if since.tzinfo is None:
        raise ValueError(f"replay since must be timezone-aware, got {since!r}")
    statement = select(*_COLUMNS).where(OutboxEvent.created_at >= since)
    if after is not None:
        # ``literal`` with the column's own type, not the bare Python values:
        # ``tuple_`` takes column expressions, and typing the binds is what
        # makes the row-value comparison and the driver agree on tz-aware
        # datetimes instead of leaning on SQLAlchemy's runtime coercion.
        cursor = tuple_(
            literal(after[0], OutboxEvent.created_at.type),
            literal(after[1], OutboxEvent.id.type),
        )
        statement = statement.where(tuple_(OutboxEvent.created_at, OutboxEvent.id) > cursor)
    return _rows(
        await session.execute(
            statement.order_by(OutboxEvent.created_at, OutboxEvent.id).limit(limit)
        )
    )


async def mark_dispatched(session: AsyncSession, ids: list[int], *, at: datetime) -> None:
    """Stamp ``dispatched_at`` on rows that reached the stream in this sweep."""
    if not ids:
        return
    await session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id.in_(ids), OutboxEvent.dispatched_at.is_(None))
        .values(dispatched_at=at, attempts=OutboxEvent.attempts + 1)
    )


async def record_failure(
    session: AsyncSession, row_id: int, error: str, *, permanent: bool = False
) -> None:
    """Count one failed publication attempt and keep its reason visible.

    ``permanent=True`` says the row can never be published as it stands (its
    payload is not an envelope), as opposed to a transport failure that the
    next sweep may well survive. Only the former is ever classified
    unpublishable — see :data:`UNPUBLISHABLE_MARK` for why the difference has
    to be recorded rather than inferred from ``attempts``.
    """
    reason = permanent_failure(error) if permanent else transient_failure(error)
    await session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id == row_id)
        .values(attempts=OutboxEvent.attempts + 1, last_error=reason[:_ERROR_MAX_CHARS])
    )


async def prune_dispatched(
    session: AsyncSession, older_than: datetime, batch: int = PRUNE_BATCH
) -> int:
    """Delete up to ``batch`` rows dispatched before ``older_than``. Returns how many.

    Retention for ``outbox_events`` (DATABASE.md §1.3, which owns the policy).
    Two invariants live in the ``WHERE`` rather than in the caller: a row with
    ``dispatched_at IS NULL`` is an obligation and is never prunable at any
    age, and ``older_than`` is the *ceiling* of the replay window, because
    ``reconcile(since=)`` can only reach rows still in the table.

    Bounded so the job can loop: one long ``DELETE`` over a day of rows would
    hold locks and produce WAL for as long as it ran, on a table the dispatcher
    is writing to at the same time. Which rows a batch takes is
    :func:`prunable_ids`.
    """
    if older_than.tzinfo is None:
        raise ValueError(f"prune older_than must be timezone-aware, got {older_than!r}")
    # ``session.execute`` is typed ``Result``; only the cursor result carries a
    # row count, and a DML statement always produces one.
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(OutboxEvent).where(
                OutboxEvent.id.in_(prunable_ids(older_than, batch).scalar_subquery())
            )
        ),
    )
    return result.rowcount


def prunable_ids(older_than: datetime, batch: int) -> Select[tuple[int]]:
    """The ids one :func:`prune_dispatched` batch deletes, **in ``id`` order**.

    Not ``dispatched_at`` order, which is what this said and what DATABASE.md
    §1.3 used to promise (Astra, T2.9b review). ``dispatched_at`` carries no
    index, so ordering by it made every batch a Seq Scan of the whole table
    plus a sort — once per loop of the retention job, on the table the
    dispatcher is writing to. And it gets no index: that one would be
    maintained on every ``mark_dispatched``, i.e. on the dispatcher's hot path,
    and would hold an entry for every dispatched row the seven-day retention
    still keeps (order of 5M at 700k rows/day), all to serve a job that runs
    once a day.

    ``id`` is a ``BIGSERIAL``, so it is insertion order, and a batch is a
    *bounded slice* of the prunable set rather than a ranking: every row it
    returns already satisfies the retention predicate, so which goes first
    changes nothing. It uses the primary key index that already exists and
    stops after ``batch`` rows. The one cost, stated: pending rows at the head
    of the key are re-scanned by every batch, never qualifying — a set bounded
    by the readiness alarm (500 pending).
    """
    return (
        select(OutboxEvent.id)
        .where(OutboxEvent.dispatched_at.is_not(None), OutboxEvent.dispatched_at < older_than)
        .order_by(OutboxEvent.id)
        .limit(batch)
    )
