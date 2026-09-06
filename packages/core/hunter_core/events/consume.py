"""Reading a stream, idempotently: XREADGROUP + XAUTOCLAIM, one message or a batch.

Where the mark lives and how it is written is :mod:`hunter_core.events.processed`;
what this module owns is the reading loop and the two shapes a consumer can ask
for.

``consume()`` is a pre-filter: it skips (and acks away) messages already marked
processed, so a redelivery of a completed message is never re-yielded to the
caller. ``ack()`` is what actually marks an event processed, right before
``XACK`` — so a crash between "effect applied" and "ack called" simply means the
message gets redelivered and reprocessed once more, which is safe because the
durable effect itself also has a unique key in Postgres (belt-and-suspenders
idempotency, per ARCHITECTURE.md §5.1).

``consume_batches()`` (T2.5d) is the same reading with the guard and the ack
paid **per batch** instead of per message. It exists because the scanner's
``market.ticks`` consumer sustained 71 msg/s against 151 produced and sat ~95 000
messages behind, spending three round trips on every message whose whole
handling is a dict touch (``.claude/state/t25-proof.md``, T2.5c §3).

T2.9: an *idle* stream is a normal state, not a failure. The blocking read is
therefore budgeted strictly under the socket read deadline, and a deadline that
fires anyway is a bounded backoff — see :data:`DEFAULT_BLOCK_MS`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.processed import (
    PROCESSED_DAYS,
    PROCESSED_TTL_S,
    ack,
    ack_many,
    is_processed,
    processed_many,
)
from hunter_core.events.produce import FIELD_NAME, ensure_group
from hunter_core.logging import get_logger
from hunter_core.redis import (
    # Deliberate coupling: the block budget must be derived from the client's
    # own read deadline or the two drift apart again (T2.9). ``hunter_core.redis``
    # is owned by another task in flight, so exporting it publicly is a
    # follow-up filed in .claude/state/notes-T2.9.md.
    _SOCKET_TIMEOUT_S,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

__all__ = [
    "DEFAULT_BLOCK_MS",
    "MAX_CONSECUTIVE_TIMEOUTS",
    "PROCESSED_DAYS",
    "PROCESSED_TTL_S",
    "TIMEOUT_BACKOFF_S",
    "ack",
    "ack_many",
    "consume",
    "consume_batches",
    "is_processed",
    "processed_many",
]
"""Re-exported from :mod:`hunter_core.events.processed`: ``ack``,
``is_processed`` and the TTL constants were part of this module's public surface
before the T2.5d split, and every worker imports them from here."""

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


async def _unprocessed(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    entries: list[tuple[Any, dict[Any, Any]]],
    *,
    now: datetime,
) -> list[tuple[str, EventEnvelope]]:
    """Decode a raw batch and drop what this group already applied.

    An entry whose envelope does not decode is left **pending**: acking it would
    hide it, and raising would cost the rest of the batch its progress. It comes
    back on the next ``XAUTOCLAIM``, is skipped again in microseconds, and is
    visible in the log every time (Astra, T2.5d design review, must-fix 5).
    """
    decoded: list[tuple[str, EventEnvelope]] = []
    for message_id, fields in entries:
        try:
            envelope = _envelope_from_fields(fields)
        except Exception as error:
            logger.warning(
                "consume_message_unreadable",
                stream=stream,
                group=group,
                message_id=_decode_id(message_id),
                error=str(error),
            )
            continue
        decoded.append((_decode_id(message_id), envelope))
    if not decoded:
        return []
    seen = await processed_many(
        client, group, [str(envelope.event_id) for _id, envelope in decoded], now=now
    )
    if not seen:
        return decoded
    stale = [message_id for message_id, envelope in decoded if str(envelope.event_id) in seen]
    if stale:
        await client.xack(stream, group, *stale)
    return [(item, envelope) for item, envelope in decoded if str(envelope.event_id) not in seen]


async def _read_loop(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    block_ms: int,
    batch: int,
    claim_idle_ms: int,
    timeout_backoff_s: float,
) -> AsyncGenerator[list[tuple[Any, dict[Any, Any]]], None]:
    """Yield raw entry lists forever: reclaimed first, then newly read.

    The reading itself — and only the reading — lives here, so the per-message
    and the batched consumers below cannot drift apart on reclaiming, on the
    block budget or on how a read deadline is tolerated.
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
            if entries:
                yield entries
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
            if new_entries:
                yield new_entries


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
    now: Callable[[], datetime] = utcnow,
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

    **The guard stays per message here, deliberately** (Astra, T2.5d design
    review): it is evaluated immediately before the message is yielded, i.e.
    after the caller has finished the previous ones. Checking a whole batch up
    front is what :func:`consume_batches` does, and it widens the window in
    which another consumer of the same group finishes the same ``event_id``
    first — worth it for a stream that is 95 000 messages behind, not for every
    consumer in the system.
    """
    async for entries in _read_loop(
        client,
        stream,
        group,
        consumer,
        block_ms=block_ms,
        batch=batch,
        claim_idle_ms=claim_idle_ms,
        timeout_backoff_s=timeout_backoff_s,
    ):
        for message_id, fields in entries:
            envelope = _envelope_from_fields(fields)
            if await is_processed(client, group, str(envelope.event_id), now=now()):
                await client.xack(stream, group, message_id)
                continue
            yield _decode_id(message_id), envelope


async def consume_batches(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    block_ms: int = DEFAULT_BLOCK_MS,
    batch: int = 10,
    claim_idle_ms: int = 30_000,
    timeout_backoff_s: float = TIMEOUT_BACKOFF_S,
    now: Callable[[], datetime] = utcnow,
) -> AsyncGenerator[list[tuple[str, EventEnvelope]], None]:
    """Yield whole read batches, already filtered by the ``event_id`` guard.

    Same reading as :func:`consume`; what changes is the *cost per message* and
    who gets to see the batch. The guard becomes one pipelined ``SMISMEMBER``
    per day read — one round trip for the whole batch instead of two per
    message — and completing the work is :func:`ack_many`, one more round trip
    for the whole batch. That is the difference between 71 msg/s and a consumer
    that keeps up (``.claude/state/t25-proof.md``, T2.5c section 3).

    Three properties the caller can rely on:

    - **every unprocessed entry is delivered, repeats included.** Two deliveries
      of one ``event_id`` are two entries here: collapsing them would ack a
      message whose effect may have failed on the first try (Astra, T2.5d design
      review, must-fix 1). Coalescing is the caller's decision, and the caller
      must still pass *every* absorbed entry to :func:`ack_many`;
    - **an unreadable message is skipped, not fatal.** One garbage entry in a
      batch of 500 must not cost the other 499 their progress, so it is logged
      and left pending rather than raised (which is what :func:`consume` still
      does, one message at a time);
    - **an empty list is a real yield.** It means the whole batch was already
      processed or unreadable — the caller's liveness clock should tick.
    """
    async for entries in _read_loop(
        client,
        stream,
        group,
        consumer,
        block_ms=block_ms,
        batch=batch,
        claim_idle_ms=claim_idle_ms,
        timeout_backoff_s=timeout_backoff_s,
    ):
        yield await _unprocessed(client, stream, group, entries, now=now())
