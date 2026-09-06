"""What an outbox row *is*: its identity and the envelope it stores.

Split out of :mod:`hunter_core.events.outbox_store`, which owns the SQL around
the queue. The boundary is real rather than a line count: everything here is
pure and knows nothing about a session, a table or a transaction, and it is
what a producer needs in order to *describe* an event — the store is what
writes, claims, marks and prunes one.

Two decisions are worth stating here because everything else follows from them.

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

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope

OUTBOX_NAMESPACE = UUID("0d0d5f8e-6f1c-4f2f-9a3b-2b1f5a7c9e40")
"""uuid5 namespace for :func:`event_id_for`. Frozen: changing it renames every
future event and would let an already-published event be published again under
a new identity."""

__all__ = [
    "OUTBOX_NAMESPACE",
    "build_envelope",
    "envelope_from_row",
    "event_id_for",
    "outbox_row",
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
