"""Reading ``market.backfill.requested`` without letting one bad message win.

``hunter_core.events.consume`` deserializes the envelope **before** yielding it,
so a message whose ``data`` field is not a valid envelope raises inside the
generator. Under ``main.py``'s ``TaskGroup`` that exception is fatal to the whole
market-worker, and the restarted process meets exactly the same message again —
``XAUTOCLAIM`` re-fetches it from the pending list on the first iteration of the
loop. A stream anyone can write to is not a place to be that brittle (Astra,
T2.5-backfill design review, must-fix 5).

So this module reads the same two commands (``XAUTOCLAIM`` for what a dead
consumer left behind, then ``XREADGROUP`` for what is new) and hands the caller
``(message_id, envelope_or_None)``: ``None`` means "this cannot be parsed",
which the consumer quarantines with an ``XACK`` and a counted, logged refusal.
Everything else — the block budget derived from the socket read deadline, the
processed-set guard, the ``ack`` that marks before it acknowledges — is reused
from ``hunter_core.events``, unchanged.

**Divergence declared:** the tolerance belongs in ``hunter_core.events.consume``
so every consumer gets it. It is not there because this task may only touch
``hunter_core.events`` for a missing stream name or maxlen; the follow-up is
recorded in ``.claude/state/notes-T2.5.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.events.consume import DEFAULT_BLOCK_MS
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME, ensure_group
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

DEFAULT_BATCH = 20
CLAIM_IDLE_MS = 30_000

__all__ = ["CLAIM_IDLE_MS", "DEFAULT_BATCH", "DEFAULT_BLOCK_MS", "read_batch"]


def _decode_id(message_id: bytes | str) -> str:
    return message_id.decode() if isinstance(message_id, bytes) else message_id


def _parse(fields: dict[Any, Any]) -> EventEnvelope | None:
    raw: Any = fields.get(FIELD_NAME) if FIELD_NAME in fields else fields.get(FIELD_NAME.decode())
    if raw is None:
        return None
    try:
        return EventEnvelope.from_bytes(raw)
    except Exception:
        return None


async def read_batch(
    client: redis_asyncio.Redis,
    stream: str,
    group: str,
    consumer: str,
    *,
    block_ms: int = DEFAULT_BLOCK_MS,
    batch: int = DEFAULT_BATCH,
    claim_idle_ms: int = CLAIM_IDLE_MS,
) -> list[tuple[str, EventEnvelope | None]]:
    """One reclaim pass plus one blocking read. Never raises on a bad payload.

    A ``redis.exceptions.TimeoutError`` on the blocking read is *not* swallowed
    here: the caller's loop decides, and the block budget is already strictly
    under the client's own read deadline (``DEFAULT_BLOCK_MS``), so a deadline
    that fires anyway is a genuine signal.
    """
    await ensure_group(client, stream, group)
    messages: list[tuple[str, EventEnvelope | None]] = []

    cursor: Any = "0-0"
    while True:
        claimed: list[Any] = await client.xautoclaim(
            stream, group, consumer, min_idle_time=claim_idle_ms, start_id=cursor, count=batch
        )
        entries: list[tuple[Any, dict[Any, Any]]] = claimed[1]
        messages.extend((_decode_id(mid), _parse(fields)) for mid, fields in entries)
        cursor = claimed[0]
        if _decode_id(cursor) == "0-0" or not entries or len(messages) >= batch:
            break

    if len(messages) >= batch:
        return messages
    try:
        response: Any = await client.xreadgroup(
            group, consumer, streams={stream: ">"}, count=batch - len(messages), block=block_ms
        )
    except RedisTimeoutError:
        logger.warning("backfill_read_deadline", stream=stream, group=group)
        return messages
    if not response:
        return messages
    for _stream_name, new_entries in response:
        entries = new_entries
        messages.extend((_decode_id(mid), _parse(fields)) for mid, fields in entries)
    return messages
