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

T2.9b: the processed set is **one key per UTC day**, read across the last two.
The single key it replaces had its TTL renewed by every ``ack``, so it never
expired and grew for as long as the deployment lived; and had it ever expired,
it would have dropped every event id it held in one instant. Daily keys expire
on their own because nothing writes to them after midnight, and reading two of
them is what keeps the effect-once guarantee from having a seam at 00:00 — see
:data:`PROCESSED_TTL_S` and :func:`is_processed`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.domain.types import utcnow
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

PROCESSED_TTL_S = 3 * 24 * 60 * 60
"""Lifetime of one day's processed set, fixed and never extended.

Strictly longer than the two-day read window of :func:`is_processed`, so a key
the guard still consults cannot already be gone: yesterday's set is read until
the end of today, i.e. up to 48h after it was created, and the third day is the
margin for a clock skew or a very late redelivery. It is a ceiling on memory,
not a promise about de-duplication beyond it — an event redelivered after this
has no guard here, only the unique key its durable effect carries in Postgres.

**The memory that ceiling buys.** One member is a 36-char uuid string; in a
Redis set that is not intset-encodable this costs on the order of 80-110 bytes
once the hashtable entry, the SDS header and the allocator's rounding are
counted. At the market-worker's own volume — order of 700k events a day
(DATABASE.md §1.3) — one group's daily key is therefore roughly **50-80 MB**,
and with this TTL up to four of them are alive at once (three full days plus
the one being written), so **~200-320 MB per consumer group** at steady state.
That is the number to check against the Redis instance before adding a group or
raising the TTL: the guard is a memory budget, and it is the reason the key is
per day rather than one key whose TTL every ack pushed forward.
"""

PROCESSED_DAYS = 2
"""Daily sets the guard reads: today and yesterday. One would break the
effect-once guarantee at every midnight; more only costs round trips."""

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


async def is_processed(
    client: redis_asyncio.Redis,
    group: str,
    event_id: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Has ``group`` already applied ``event_id``, today or yesterday?

    Today first: a redelivery of something just handled is the common case, and
    it costs one round trip. Yesterday is what makes the guard continuous — an
    event acked at 23:59:30 and redelivered at 00:00:30 is the same event, and
    reading only today's set would let it through at the same instant every
    night.
    """
    at = now or utcnow()
    for age in range(PROCESSED_DAYS):
        key = keys.processed(group, (at - timedelta(days=age)).date())
        if bool(await client.sismember(key, event_id)):
            return True
    return False


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
                if await is_processed(client, group, str(envelope.event_id), now=now()):
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
                if await is_processed(client, group, str(envelope.event_id), now=now()):
                    await client.xack(stream, group, message_id)
                    continue
                yield _decode_id(message_id), envelope


async def ack(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    message_id: str,
    envelope: EventEnvelope,
    *,
    now: Callable[[], datetime] = utcnow,
) -> None:
    """Mark ``envelope.event_id`` processed in **today's** set, then ``XACK``.

    The ``EXPIRE`` is idempotent and always the same fixed value, which is the
    point: the key stops receiving members at midnight, so from then on its TTL
    counts down for real instead of being pushed forward by the next ack.

    **One round trip, not three.** This runs once per message on every stream,
    so awaiting the three commands in turn spent three round trips per event
    where one does. ``transaction=False``: without ``MULTI`` the three keys may
    live in different cluster slots, and atomicity was never what made this
    safe — a crash before ``execute`` marks nothing and acks nothing, so the
    message is redelivered and handled again, which the durable effect's own
    unique key already covers (ARCHITECTURE.md §5.1). Order inside the pipeline
    is still the order written, so the mark never lands after its ``XACK``.
    """
    processed_key = keys.processed(group, now().date())
    async with client.pipeline(transaction=False) as pipe:
        pipe.sadd(processed_key, str(envelope.event_id))
        pipe.expire(processed_key, PROCESSED_TTL_S)
        pipe.xack(stream, group, message_id)
        await pipe.execute()
