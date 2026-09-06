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

T2.9: an *idle* stream is a normal state, not a failure. The blocking read is
therefore budgeted strictly under the socket read deadline, and a deadline that
fires anyway is a bounded backoff — see :data:`DEFAULT_BLOCK_MS`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME, ensure_group
from hunter_core.logging import get_logger
from hunter_core.redis import (
    # Deliberate coupling: the block budget must be derived from the client's
    # own read deadline or the two drift apart again (T2.9). ``hunter_core.redis``
    # is owned by another task in flight, so exporting it publicly is a
    # follow-up filed in .claude/state/notes-T2.9.md.
    _SOCKET_TIMEOUT_S,  # pyright: ignore[reportPrivateUsage]
    keys,
)

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

_PROCESSED_TTL_S = 24 * 60 * 60

_BLOCK_FRACTION = 0.4
DEFAULT_BLOCK_MS = int(_SOCKET_TIMEOUT_S * 1000 * _BLOCK_FRACTION)
"""How long ``XREADGROUP`` may block, derived from the client's own read deadline.

The old default was a flat 5000 — exactly ``hunter_core.redis``'s
``socket_timeout`` of 5.0s. On a stream nobody is writing to, the block runs its
whole budget and the socket read deadline expires at the very same instant, so
*every* consumer of a quiet stream raised ``redis.exceptions.TimeoutError``. It
killed the strategy-worker in the S2 operational proof, which worked around it
locally with its own 2000; deriving the value here fixes it for every consumer
and keeps the two numbers from drifting apart again."""

MAX_CONSECUTIVE_TIMEOUTS = 5
"""Read deadlines tolerated in a row before the error is escalated.

Swallowing them forever would turn "Redis accepts connections but answers
nothing" into a consumer that looks alive and makes no progress — precisely the
silent park ``socket_timeout`` exists to expose (Astra, T2.9 round 1). Any
answered read, *including an empty one*, resets the counter: an idle stream is
healthy."""

TIMEOUT_BACKOFF_S = 0.2


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
    block_ms: int = DEFAULT_BLOCK_MS,
    batch: int = 10,
    claim_idle_ms: int = 30_000,
    timeout_backoff_s: float = TIMEOUT_BACKOFF_S,
) -> AsyncGenerator[tuple[str, EventEnvelope], None]:
    """Yield ``(message_id, envelope)`` for every new or reclaimed message.

    Each loop iteration first reclaims messages idle for longer than
    ``claim_idle_ms`` (``XAUTOCLAIM`` — recovers work stuck on a dead
    consumer instance), then reads up to ``batch`` new messages, blocking for
    ``block_ms`` if the stream is empty.

    A read deadline (``redis.exceptions.TimeoutError``) is retried after a short
    backoff up to :data:`MAX_CONSECUTIVE_TIMEOUTS` times and then re-raised;
    every other Redis error — a dropped connection above all — propagates on
    the first occurrence, unchanged.
    """
    if block_ms <= 0:
        raise ValueError("block_ms must be positive; 0 blocks XREADGROUP forever")
    await ensure_group(client, stream, group)
    timeouts = 0
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

        try:
            response: Any = await client.xreadgroup(
                group, consumer, streams={stream: ">"}, count=batch, block=block_ms
            )
        except RedisTimeoutError:
            timeouts += 1
            logger.warning(
                "consume_read_deadline", stream=stream, group=group, consecutive=timeouts
            )
            if timeouts > MAX_CONSECUTIVE_TIMEOUTS:
                raise
            if timeout_backoff_s > 0:
                await asyncio.sleep(timeout_backoff_s)
            continue
        timeouts = 0
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
