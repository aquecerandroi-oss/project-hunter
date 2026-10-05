"""Decoding and guarding what ``consume``'s read loop hands over.

Split out of ``consume.py`` for the 350-line budget; the names are the same helpers,
unchanged, without the leading underscore.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.processed import processed_many
from hunter_core.events.produce import FIELD_NAME
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime

    import redis.asyncio as redis_asyncio

logger = get_logger("hunter_core.events.consume")

__all__ = ["decode_id", "deadline", "envelope_from_fields", "unprocessed"]


def decode_id(message_id: bytes | str) -> str:
    return message_id.decode() if isinstance(message_id, bytes) else message_id


def deadline(stream: str, group: str, op: str, count: int) -> None:
    """One log line for any read-path timeout, ``op``-labelled (T3.83): shared
    by ``_read_loop``'s two calls and ``consume()``'s own guard so a shared
    counter is never required across operations that fail independently."""
    logger.warning("consume_read_deadline", stream=stream, group=group, op=op, consecutive=count)


def envelope_from_fields(fields: dict[Any, Any]) -> EventEnvelope:
    raw: Any = fields.get(FIELD_NAME) if FIELD_NAME in fields else fields.get(FIELD_NAME.decode())
    if raw is None:
        raise ValueError(f"stream message is missing the {FIELD_NAME!r} field")
    return EventEnvelope.from_bytes(raw)


async def unprocessed(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    entries: list[tuple[Any, dict[Any, Any]]],
    *,
    now: datetime,
    track: bool = True,
) -> list[tuple[str, EventEnvelope]]:
    """Decode a raw batch and drop what this group already applied.

    An entry whose envelope does not decode is left **pending**: acking it would
    hide it, and raising would cost the rest of the batch its progress. It comes
    back on the next ``XAUTOCLAIM``, is skipped again in microseconds, and is
    visible in the log every time (Astra, T2.5d design review, must-fix 5).
    ``track=False`` (T3.85) skips the guard: no durable effect, nothing to remember.
    """
    decoded: list[tuple[str, EventEnvelope]] = []
    for message_id, fields in entries:
        try:
            envelope = envelope_from_fields(fields)
        except Exception as error:
            logger.warning(
                "consume_message_unreadable",
                stream=stream,
                group=group,
                message_id=decode_id(message_id),
                error=str(error),
            )
            continue
        decoded.append((decode_id(message_id), envelope))
    if not decoded or not track:
        return decoded
    seen = await processed_many(
        client, group, [str(envelope.event_id) for _id, envelope in decoded], now=now
    )
    if not seen:
        return decoded
    stale = [message_id for message_id, envelope in decoded if str(envelope.event_id) in seen]
    if stale:
        await client.xack(stream, group, *stale)
    return [(item, envelope) for item, envelope in decoded if str(envelope.event_id) not in seen]
