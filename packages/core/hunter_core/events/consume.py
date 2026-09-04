"""Idempotent stream consumption: XREADGROUP + XAUTOCLAIM, exactly-once effects.

ARCHITECTURE.md §5.1: "consumidor grava event_id em hunter:processed:{consumer}
(SET, TTL 24h) antes de agir sobre efeitos duraveis." The doc's "{consumer}"
means the logical consuming service, i.e. the consumer *group* here — not the
per-instance consumer name — so that if instance A dies before acking and
instance B claims the pending message via XAUTOCLAIM, B still recognizes the
event as already handled. See the T03 report's CONCERNS for this reading.

``consume()`` is a pre-filter: it skips (and acks away) messages already
marked processed, so a redelivery of a completed message is never re-yielded
to the caller. ``ack()`` is what actually marks an event processed, right
before ``XACK`` — so a crash between "effect applied" and "ack called" simply
means the message gets redelivered and reprocessed once more, which is safe
because the durable effect itself also has a unique key in Postgres
(belt-and-suspenders idempotency, per ARCHITECTURE.md §5.1).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME, ensure_group
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

_PROCESSED_TTL_S = 24 * 60 * 60


def _decode_id(message_id: bytes | str) -> str:
    return message_id.decode() if isinstance(message_id, bytes) else message_id


def _envelope_from_fields(fields: dict[Any, Any]) -> EventEnvelope:
    raw: Any = fields.get(FIELD_NAME) if FIELD_NAME in fields else fields.get(FIELD_NAME.decode())
    if raw is None:
        raise ValueError(f"stream message is missing the {FIELD_NAME!r} field")
    return EventEnvelope.from_bytes(raw)


async def _is_processed(client: redis_asyncio.Redis, group: str, event_id: str) -> bool:
    return bool(await client.sismember(keys.processed(group), event_id))


async def consume(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    block_ms: int = 5_000,
    batch: int = 10,
    claim_idle_ms: int = 30_000,
) -> AsyncIterator[tuple[str, EventEnvelope]]:
    """Yield ``(message_id, envelope)`` for every new or reclaimed message.

    Each loop iteration first reclaims messages idle for longer than
    ``claim_idle_ms`` (``XAUTOCLAIM`` — recovers work stuck on a dead
    consumer instance), then reads up to ``batch`` new messages, blocking for
    ``block_ms`` if the stream is empty.
    """
    await ensure_group(client, stream, group)
    while True:
        cursor: Any = "0-0"
        while True:
            claimed: list[Any] = await client.xautoclaim(
                stream, group, consumer, min_idle_time=claim_idle_ms, start_id=cursor, count=batch
            )
            next_cursor: Any = claimed[0]
            entries: list[tuple[Any, dict[Any, Any]]] = claimed[1]
            for message_id, fields in entries:
                envelope = _envelope_from_fields(fields)
                if await _is_processed(client, group, str(envelope.event_id)):
                    await client.xack(stream, group, message_id)
                    continue
                yield _decode_id(message_id), envelope
            cursor = next_cursor
            if _decode_id(cursor) == "0-0" or not entries:
                break

        response: Any = await client.xreadgroup(
            group, consumer, streams={stream: ">"}, count=batch, block=block_ms
        )
        if not response:
            continue
        for _stream_name, new_entries in response:
            entries = new_entries
            for message_id, fields in entries:
                envelope = _envelope_from_fields(fields)
                if await _is_processed(client, group, str(envelope.event_id)):
                    await client.xack(stream, group, message_id)
                    continue
                yield _decode_id(message_id), envelope


async def ack(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    message_id: str,
    envelope: EventEnvelope,
) -> None:
    """Mark ``envelope.event_id`` processed (24h TTL SET) then ``XACK``."""
    processed_key = keys.processed(group)
    await client.sadd(processed_key, str(envelope.event_id))
    await client.expire(processed_key, _PROCESSED_TTL_S)
    await client.xack(stream, group, message_id)
