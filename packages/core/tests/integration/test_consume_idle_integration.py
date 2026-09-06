"""An idle stream must not kill its consumer (T2.9), against a real Redis.

The S2 operational proof killed the strategy-worker with
``redis.exceptions.TimeoutError`` on a quiet ``market.candles.closed``: the
default ``block_ms`` was exactly the client's ``socket_timeout``. This is the
regression test at the source, with the production client (bounded timeouts,
retry policy — ``hunter_core.redis.create_redis``) and the production default.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from pydantic import SecretStr

from hunter_core.events.consume import consume
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import ensure_group, publish
from hunter_core.redis import (
    _SOCKET_TIMEOUT_S,  # pyright: ignore[reportPrivateUsage]
    create_redis,
)
from hunter_core.settings import Settings

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from testcontainers.community.redis import RedisContainer

pytestmark = pytest.mark.integration

IDLE_S = 30.0
"""Six times the 5s socket read deadline: the old default died on the first."""


@pytest_asyncio.fixture
async def production_redis(
    redis_container: RedisContainer,
) -> AsyncIterator[redis_asyncio.Redis]:
    """The very client the workers build, timeouts and retries included."""
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    client = create_redis(Settings(redis_url=SecretStr(f"redis://{host}:{port}/0")))
    try:
        yield client
    finally:
        await client.aclose()


async def test_a_consumer_survives_thirty_seconds_of_an_idle_stream(
    production_redis: redis_asyncio.Redis,
) -> None:
    stream = f"market.candles.closed.{uuid.uuid4().hex}"
    group = "idle-test"
    await ensure_group(production_redis, stream, group)

    received: list[EventEnvelope] = []
    failure: list[BaseException] = []

    async def reader() -> None:
        try:
            async for _message_id, envelope in consume(production_redis, stream, group, "c1"):
                received.append(envelope)
                return
        except BaseException as exc:
            failure.append(exc)

    task = asyncio.create_task(reader())
    await asyncio.sleep(IDLE_S)

    assert not failure, f"the consumer died on an idle stream: {failure[0]!r}"
    assert not task.done(), "the consumer stopped iterating on an idle stream"

    envelope = EventEnvelope(type=stream, producer="p", key="k", payload={"n": 1})
    await publish(production_redis, stream, envelope, maxlen=1000)
    await asyncio.wait_for(task, timeout=_SOCKET_TIMEOUT_S * 2)

    assert not failure
    assert [e.event_id for e in received] == [envelope.event_id]
    await production_redis.delete(stream)
