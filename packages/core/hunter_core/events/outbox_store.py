"""The outbox row: identity, the envelope it stores, and the SQL around it.

The row shape is fixed by ``outbox_events`` (T2.1, ``db/models/system.py``):
``(event_id, stream, payload, created_at, dispatched_at, attempts, last_error)``.
Two decisions are worth stating here because everything else follows from
them.

**The ``payload`` column holds the whole :class:`EventEnvelope`, not just the
business payload.** The event is therefore fully determined at *enqueue*
time — identity, ``ts``, producer and routing key included — so every
publication of a row is the same message rather than a new event that merely
looks alike: publish it twice and the two stream entries are identical bytes,
because both are rendered from the one stored row. The dispatcher becomes a
dumb pipe with no heuristics (the S2 dispatcher had to guess the routing key
from ``payload["symbol"]``). The business payload is one level in:
``payload -> 'payload' ->> 'symbol'``.

Rebuilding always goes through :class:`EventEnvelope` so the envelope's own
fields come back in the model's fixed order (Astra, T2.9 round 1). Note the
narrow limit of that: JSONB does not preserve key order, and the *business*
payload is an opaque dict, so the bytes are not necessarily identical to what
the producer originally serialized — only to every other publication of the
same row. Identity never depends on bytes; it is ``event_id``.

**``event_id`` is deterministic, computed by the producer from the business
row** (:func:`event_id_for`), and the column is ``UNIQUE`` with ``ON CONFLICT
DO NOTHING``: a retried transaction queues the event once, and a redelivery of
the source message is a no-op instead of a second publication.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid5

from sqlalchemy import func, literal, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.system import OutboxEvent
from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

OUTBOX_NAMESPACE = UUID("0d0d5f8e-6f1c-4f2f-9a3b-2b1f5a7c9e40")
"""uuid5 namespace for :func:`event_id_for`. Frozen: changing it renames every
future event and would let an already-published event be published again under
a new identity."""

_ERROR_MAX_CHARS = 500

__all__ = [
    "OUTBOX_NAMESPACE",
    "PendingRow",
    "build_envelope",
    "claim_pending",
    "enqueue",
    "enqueue_many",
    "envelope_from_row",
    "event_id_for",
    "mark_dispatched",
    "outbox_row",
    "pending_stats",
    "record_failure",
    "replay_rows",
]


def _part(value: object) -> str:
    """One component of the canonical string an ``event_id`` hashes.

    Datetimes are normalized to UTC first so the same instant written in
    another offset is the same event; a naive one is rejected outright,
    because "which instant" would then depend on the writer's box.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError(f"event_id parts must be timezone-aware datetimes, got {value!r}")
        return value.astimezone(UTC).isoformat()
    return str(value)


def event_id_for(stream: str, *parts: object) -> UUID:
    """The deterministic identity of the event ``parts`` describe on ``stream``.

    Same business row, same id — forever, on every process. That is what makes
    ``ON CONFLICT (event_id) DO NOTHING`` an idempotent enqueue and what lets a
    consumer recognize a redelivery.
    """
    canonical = "|".join([stream, *(_part(part) for part in parts)])
    return uuid5(OUTBOX_NAMESPACE, canonical)


def build_envelope(
    stream: str,
    event_id: UUID,
    payload: dict[str, Any],
    *,
    producer: str,
    key: str,
    ts: datetime | None = None,
) -> EventEnvelope:
    """The envelope the row stores. ``ts`` is the enqueue instant (UTC)."""
    if ts is not None and ts.tzinfo is None:
        raise ValueError(f"the envelope ts must be timezone-aware, got {ts!r}")
    return EventEnvelope(
        event_id=event_id,
        type=stream,
        ts=(ts.astimezone(UTC) if ts is not None else utcnow()),
        producer=producer,
        key=key,
        payload=payload,
    )


def outbox_row(envelope: EventEnvelope) -> dict[str, Any]:
    """The ``outbox_events`` column values for ``envelope``."""
    return {
        "event_id": envelope.event_id,
        "stream": envelope.type,
        "payload": envelope.model_dump(mode="json"),
    }


def envelope_from_row(payload: dict[str, Any]) -> EventEnvelope:
    """Rebuild the envelope a row stores, in the model's own field order."""
    try:
        return EventEnvelope.model_validate(payload)
    except Exception as exc:
        raise ValueError(f"outbox payload is not an envelope: {exc}") from exc


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
    step over a transaction that took a lower id and committed later.

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


async def record_failure(session: AsyncSession, row_id: int, error: str) -> None:
    """Count one failed publication attempt and keep its reason visible."""
    await session.execute(
        update(OutboxEvent)
        .where(OutboxEvent.id == row_id)
        .values(attempts=OutboxEvent.attempts + 1, last_error=error[:_ERROR_MAX_CHARS])
    )


async def pending_stats(session: AsyncSession) -> tuple[int, datetime | None]:
    """``(pending count, oldest created_at)`` — the readiness inputs."""
    row = (
        await session.execute(
            select(func.count(), func.min(OutboxEvent.created_at)).where(
                OutboxEvent.dispatched_at.is_(None)
            )
        )
    ).one()
    oldest: datetime | None = row[1]
    if oldest is not None and oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    return int(row[0]), oldest
