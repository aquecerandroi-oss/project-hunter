"""``consume()`` must survive an idle stream (T2.9).

The S2 operational proof found the real bug this pins: ``consume()``'s default
``block_ms`` was 5000 and ``hunter_core.redis`` sets ``socket_timeout=5.0``, so
on a quiet stream ``XREADGROUP`` runs its full block budget and the socket read
deadline expires at the same instant — every consumer of an idle stream died
with ``redis.exceptions.TimeoutError``. Fixed at the source here.
"""

from __future__ import annotations

from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.events.consume import (
    DEFAULT_BLOCK_MS,
    MAX_CONSECUTIVE_TIMEOUTS,
    consume,
)
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME
from hunter_core.redis import _SOCKET_TIMEOUT_S  # pyright: ignore[reportPrivateUsage]

pytestmark = pytest.mark.unit


class FakeRedis:
    """The three calls ``consume()`` makes, scripted per test."""

    def __init__(self, reads: list[Any]) -> None:
        self.reads = list(reads)
        self.read_calls = 0
        self.acked: list[str] = []
        self.block_values: list[int] = []

    async def xgroup_create(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def xautoclaim(self, *args: Any, **kwargs: Any) -> Any:
        return [b"0-0", [], []]

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> Any:
        self.block_values.append(int(kwargs["block"]))
        self.read_calls += 1
        if not self.reads:
            raise AssertionError("consume() read more times than the test scripted")
        outcome = self.reads.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def sismember(self, *args: Any, **kwargs: Any) -> bool:
        return False

    async def xack(self, _stream: str, _group: str, message_id: Any) -> None:
        self.acked.append(str(message_id))


def _message(n: int) -> Any:
    envelope = EventEnvelope(type="t", producer="p", key="k", payload={"n": n})
    return [(b"test.stream", [(f"1-{n}".encode(), {FIELD_NAME: envelope.to_bytes()})])]


def test_the_default_block_is_shorter_than_the_socket_read_deadline() -> None:
    """The regression itself: block budget strictly under the read deadline."""
    assert DEFAULT_BLOCK_MS / 1000 < _SOCKET_TIMEOUT_S
    assert DEFAULT_BLOCK_MS > 0


async def test_consume_uses_the_safe_default_block() -> None:
    client = FakeRedis([_message(1)])
    gen = consume(client, "test.stream", "g", "c")  # type: ignore[arg-type]
    await gen.__anext__()
    await gen.aclose()
    assert client.block_values == [DEFAULT_BLOCK_MS]


async def test_an_idle_stream_timeout_is_a_backoff_not_a_death() -> None:
    """A stream nobody is writing to must not kill its consumer."""
    client = FakeRedis([RedisTimeoutError("idle"), RedisTimeoutError("idle"), _message(1)])
    gen = consume(client, "test.stream", "g", "c", timeout_backoff_s=0)  # type: ignore[arg-type]
    _message_id, envelope = await gen.__anext__()
    await gen.aclose()
    assert envelope.payload == {"n": 1}
    assert client.read_calls == 3


async def test_a_stream_that_answers_resets_the_timeout_budget() -> None:
    """An empty-but-successful read is a healthy idle stream, so the
    consecutive-timeout counter must start over — otherwise a consumer that
    idles for hours eventually trips the give-up threshold for no reason."""
    reads: list[Any] = []
    for _ in range(MAX_CONSECUTIVE_TIMEOUTS - 1):
        reads.extend([RedisTimeoutError("idle"), []])
    reads.append(_message(1))
    client = FakeRedis(reads)
    gen = consume(client, "test.stream", "g", "c", timeout_backoff_s=0)  # type: ignore[arg-type]
    _message_id, envelope = await gen.__anext__()
    await gen.aclose()
    assert envelope.payload == {"n": 1}


async def test_relentless_timeouts_are_escalated_to_the_supervisor() -> None:
    """A Redis that accepts connections but answers nothing must not look
    healthy forever: after ``MAX_CONSECUTIVE_TIMEOUTS`` with no progress the
    error is raised so the worker's supervision sees it."""
    client = FakeRedis([RedisTimeoutError("dead") for _ in range(MAX_CONSECUTIVE_TIMEOUTS + 1)])
    gen = consume(client, "test.stream", "g", "c", timeout_backoff_s=0)  # type: ignore[arg-type]
    with pytest.raises(RedisTimeoutError):
        await gen.__anext__()
    assert client.read_calls == MAX_CONSECUTIVE_TIMEOUTS + 1


async def test_a_connection_error_still_propagates_immediately() -> None:
    """Only the blocking-read deadline is tolerated; a dropped connection is
    a real failure and stays one."""
    client = FakeRedis([RedisConnectionError("gone")])
    gen = consume(client, "test.stream", "g", "c", timeout_backoff_s=0)  # type: ignore[arg-type]
    with pytest.raises(RedisConnectionError):
        await gen.__anext__()
