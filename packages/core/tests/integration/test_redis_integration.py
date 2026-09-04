"""Integration tests for hunter_core.events and hunter_core.redis against real Redis.

Uses the ``redis:7-alpine`` testcontainer from ``tests/conftest.py``; skips
(with reason printed) if Docker is unreachable.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

import pytest

from hunter_core.events import EventEnvelope, ack, consume, ensure_group, publish
from hunter_core.events.produce import FIELD_NAME
from hunter_core.redis import acquire_lock

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

pytestmark = pytest.mark.integration


def _stream_name() -> str:
    return f"test.events.{uuid.uuid4().hex}"


async def test_ack_marks_processed_and_clears_pending(redis_client: redis_asyncio.Redis) -> None:
    stream = _stream_name()
    group = "workers"
    await ensure_group(redis_client, stream, group)
    envelope = EventEnvelope(type="t", producer="p", key="k", payload={"n": 1})
    await publish(redis_client, stream, envelope, maxlen=1000)

    gen = consume(
        redis_client, stream, group, "consumer-1", block_ms=200, batch=10, claim_idle_ms=50_000
    )
    message_id, received = await asyncio.wait_for(gen.__anext__(), timeout=5)
    assert received.event_id == envelope.event_id

    await ack(redis_client, stream, group, message_id, received)

    is_processed = await redis_client.sismember(  # type: ignore[reportUnknownMemberType]
        f"hunter:processed:{group}", str(envelope.event_id)
    )
    assert is_processed
    pending = await redis_client.xpending(stream, group)  # type: ignore[reportUnknownMemberType]
    assert pending["pending"] == 0


async def test_consume_redelivers_an_unacked_message_past_claim_idle_ms(
    redis_client: redis_asyncio.Redis,
) -> None:
    stream = _stream_name()
    group = "workers"
    await ensure_group(redis_client, stream, group)
    envelope = EventEnvelope(type="t", producer="p", key="k", payload={"n": 1})
    await publish(redis_client, stream, envelope, maxlen=1000)

    gen = consume(
        redis_client, stream, group, "consumer-1", block_ms=200, batch=10, claim_idle_ms=100
    )
    first_id, first_envelope = await asyncio.wait_for(gen.__anext__(), timeout=5)

    # do NOT ack; wait past claim_idle_ms so the pending entry becomes reclaimable
    await asyncio.sleep(0.3)

    second_id, second_envelope = await asyncio.wait_for(gen.__anext__(), timeout=5)
    assert second_id == first_id
    assert second_envelope.event_id == first_envelope.event_id

    await ack(redis_client, stream, group, second_id, second_envelope)


async def test_a_duplicate_stream_entry_for_an_already_acked_event_is_never_yielded_twice(
    redis_client: redis_asyncio.Redis,
) -> None:
    stream = _stream_name()
    group = "workers"
    await ensure_group(redis_client, stream, group)

    duplicate = EventEnvelope(type="t", producer="p", key="k", payload={"n": 1})
    other = EventEnvelope(type="t", producer="p", key="k", payload={"n": 2})

    # First delivery of `duplicate`, processed and acked immediately (as a real
    # consumer would do right after applying its durable, uniquely-keyed effect).
    gen = consume(
        redis_client, stream, group, "consumer-1", block_ms=200, batch=10, claim_idle_ms=50_000
    )
    await publish(redis_client, stream, duplicate, maxlen=1000)
    first_id, first_envelope = await asyncio.wait_for(gen.__anext__(), timeout=5)
    await ack(redis_client, stream, group, first_id, first_envelope)

    # A producer retry re-publishes the SAME event_id under a brand new stream
    # message id, immediately followed by a genuinely new event.
    await redis_client.xadd(  # type: ignore[reportUnknownMemberType]
        stream, {FIELD_NAME: duplicate.to_bytes()}
    )
    await publish(redis_client, stream, other, maxlen=1000)

    next_id, next_envelope = await asyncio.wait_for(gen.__anext__(), timeout=5)

    # the duplicate must be skipped (already processed) — the next thing the
    # caller ever sees is the genuinely new event, not a second delivery of `duplicate`.
    assert next_envelope.event_id == other.event_id
    assert next_id != first_id
    await ack(redis_client, stream, group, next_id, next_envelope)


async def test_acquire_lock_mutual_exclusion(redis_client: redis_asyncio.Redis) -> None:
    lock_name = f"test-lock-{uuid.uuid4().hex}"
    results: list[bool] = []

    async def contender() -> None:
        async with acquire_lock(redis_client, lock_name, ttl_ms=2_000) as acquired:
            results.append(acquired)
            if acquired:
                await asyncio.sleep(0.3)

    await asyncio.gather(contender(), contender())

    assert sorted(results) == [False, True]
