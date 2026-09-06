"""The ``event_id`` guard and the acks that write it — one message or a batch.

Split out of :mod:`hunter_core.events.consume` in T2.5d, by responsibility: this
module answers "has this group already applied this event?" and "record that it
has", and knows nothing about reading a stream; the other one reads streams and
knows nothing about how the mark is stored. The split is also what keeps both
files inside the 350-line budget now that each question has a per-message and a
per-batch shape.

ARCHITECTURE.md §5.1: "consumidor grava event_id em hunter:processed:{consumer}
(SET, TTL 24h) antes de agir sobre efeitos duraveis." The doc's "{consumer}"
means the logical consuming service, i.e. the consumer *group* here — not the
per-instance consumer name — so that if instance A dies before acking and
instance B claims the pending message via XAUTOCLAIM, B still recognizes the
event as already handled.

T2.9b: the processed set is **one key per UTC day**, read across the last two.
The single key it replaces had its TTL renewed by every ``ack``, so it never
expired and grew for as long as the deployment lived; and had it ever expired,
it would have dropped every event id it held in one instant. Daily keys expire
on their own because nothing writes to them after midnight, and reading two of
them is what keeps the effect-once guarantee from having a seam at 00:00 — see
:data:`PROCESSED_TTL_S` and :func:`is_processed`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from hunter_core.domain.types import utcnow
from hunter_core.events.envelope import EventEnvelope
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

__all__ = [
    "PROCESSED_DAYS",
    "PROCESSED_TTL_S",
    "ack",
    "ack_many",
    "is_processed",
    "processed_many",
]

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


async def processed_many(
    client: redis_asyncio.Redis,
    group: str,
    event_ids: Sequence[str],
    *,
    now: datetime,
) -> set[str]:
    """Which of ``event_ids`` this group already applied, in one round trip.

    Same two-day window as :func:`is_processed` and the same answer; what
    changes is the shape — ``SMISMEMBER`` asks for the whole batch in one
    command, and the two days go out in one pipeline. 500 messages therefore
    cost two commands and one round trip instead of 1 000 round trips, which is
    the difference the scanner's tick consumer was dying on (T2.5c proof, §3).
    """
    members = list(event_ids)
    if not members:
        return set()
    async with client.pipeline(transaction=False) as pipe:
        # ``smismember``'s ``values`` is untyped in redis-py's own annotations
        # (``List[Unknown]``), the same narrowing the ledger uses for ``hgetall``.
        queue: Any = pipe
        for age in range(PROCESSED_DAYS):
            queue.smismember(keys.processed(group, (now - timedelta(days=age)).date()), members)
        answers: list[Any] = await pipe.execute()
    return {
        event_id
        for flags in answers
        for event_id, flag in zip(members, flags or [], strict=False)
        if flag
    }


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


async def ack_many(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    items: Sequence[tuple[str, EventEnvelope]],
    *,
    now: Callable[[], datetime] = utcnow,
) -> None:
    """:func:`ack` for a whole batch: same order, same guarantees, one round trip.

    ``SADD`` takes every event id at once and ``XACK`` every message id at once,
    still marked before acked and still without ``MULTI`` — for the reasons
    written in :func:`ack`.

    **Every entry the batch absorbed belongs here**, not only the ones that
    produced a distinct effect: 500 ticks coalesced into one evaluation are 500
    finished messages, and acking only the representative would leave 499
    pending for ``XAUTOCLAIM`` to bring back forever (Astra, T2.5d design
    review, must-fix 3).
    """
    if not items:
        return
    processed_key = keys.processed(group, now().date())
    async with client.pipeline(transaction=False) as pipe:
        pipe.sadd(processed_key, *[str(envelope.event_id) for _id, envelope in items])
        pipe.expire(processed_key, PROCESSED_TTL_S)
        pipe.xack(stream, group, *[message_id for message_id, _envelope in items])
        await pipe.execute()
