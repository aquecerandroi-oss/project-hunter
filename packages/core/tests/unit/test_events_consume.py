"""``consume()`` must survive an idle stream (T2.9).

The S2 operational proof found the real bug this pins: ``consume()``'s default
``block_ms`` was 5000 and ``hunter_core.redis`` sets ``socket_timeout=5.0``, so
on a quiet stream ``XREADGROUP`` runs its full block budget and the socket read
deadline expires at the same instant — every consumer of an idle stream died
with ``redis.exceptions.TimeoutError``. Fixed at the source here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from hunter_core.events.consume import (
    DEFAULT_BLOCK_MS,
    MAX_CONSECUTIVE_TIMEOUTS,
    PROCESSED_TTL_S,
    ack,
    consume,
)
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME
from hunter_core.redis import (
    _SOCKET_TIMEOUT_S,  # pyright: ignore[reportPrivateUsage]
    keys,
)

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


# --- T2.9b: the processed set is per day, and read across two -------------


class ProcessedRedis:
    """Just the SET/TTL calls the idempotency guard makes."""

    def __init__(self) -> None:
        self.members: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}
        self.acked: list[str] = []
        self.pipelines: list[bool] = []
        self.round_trips = 0

    def sadd(self, key: str, member: str) -> int:
        self.members.setdefault(key, set()).add(member)
        return 1

    def expire(self, key: str, ttl: int) -> bool:
        self.ttls[key] = ttl
        return True

    async def sismember(self, key: str, member: str) -> bool:
        return member in self.members.get(key, set())

    def xack(self, _stream: str, _group: str, message_id: str) -> None:
        self.acked.append(message_id)

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        self.pipelines.append(transaction)
        return _FakePipeline(self)


class _FakePipeline:
    """Buffers the way ``redis.asyncio``'s does: commands return the pipeline
    and nothing reaches the server until ``execute``."""

    def __init__(self, client: ProcessedRedis) -> None:
        self._client = client
        self._queued: list[Callable[[], object]] = []

    async def __aenter__(self) -> _FakePipeline:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def sadd(self, key: str, member: str) -> _FakePipeline:
        self._queued.append(lambda: self._client.sadd(key, member))
        return self

    def expire(self, key: str, ttl: int) -> _FakePipeline:
        self._queued.append(lambda: self._client.expire(key, ttl))
        return self

    def xack(self, stream: str, group: str, message_id: str) -> _FakePipeline:
        self._queued.append(lambda: self._client.xack(stream, group, message_id))
        return self

    async def execute(self) -> list[object]:
        self._client.round_trips += 1
        return [call() for call in self._queued]


_ENVELOPE = EventEnvelope(type="t", producer="p", key="k", payload={})
_LAST_MINUTE = datetime(2026, 9, 6, 23, 59, 30, tzinfo=UTC)


def test_the_processed_set_is_keyed_by_day() -> None:
    """One key per UTC day, so each one stops being written to at midnight and
    can then actually expire. The old single key had its TTL refreshed on every
    ack, so it never expired and grew for the life of the deployment."""
    day = keys.processed("scanner-worker", _LAST_MINUTE.date())
    assert day == "hunter:processed:scanner-worker:20260906"
    assert keys.processed("scanner-worker", (_LAST_MINUTE + timedelta(days=1)).date()) != day


async def test_the_once_only_effect_survives_the_turn_of_the_day() -> None:
    """The regression this exists for.

    An event acked at 23:59:30 and redelivered at 00:00:30 is the same event.
    With a per-day set that only *today* is read from, the redelivery would look
    brand new and the effect would happen a second time — a candle persisted
    twice, a signal acted on twice — at the same instant every night. So the
    guard reads today **and** yesterday, and the TTL outlives that window.
    """
    client = ProcessedRedis()
    await ack(cast("Any", client), "s", "g", "1-1", _ENVELOPE, now=lambda: _LAST_MINUTE)

    just_after_midnight = _LAST_MINUTE + timedelta(minutes=1)
    assert just_after_midnight.date() != _LAST_MINUTE.date()
    assert await _seen(client, just_after_midnight) is True

    # ... and a day later, the window has legitimately closed.
    assert await _seen(client, _LAST_MINUTE + timedelta(days=2)) is False


async def _seen(client: ProcessedRedis, now: datetime) -> bool:
    from hunter_core.events.consume import is_processed

    return await is_processed(cast("Any", client), "g", str(_ENVELOPE.event_id), now=now)


async def test_the_ttl_is_fixed_and_outlives_the_two_day_read_window() -> None:
    """A TTL shorter than the read window would let the guard read a key that
    is already gone; one refreshed per ack (the old behaviour) never expires."""
    client = ProcessedRedis()
    await ack(cast("Any", client), "s", "g", "1-1", _ENVELOPE, now=lambda: _LAST_MINUTE)
    key = keys.processed("g", _LAST_MINUTE.date())
    assert client.ttls == {key: PROCESSED_TTL_S}
    assert PROCESSED_TTL_S >= 2 * 24 * 60 * 60
    assert client.acked == ["1-1"]


async def test_ack_is_one_round_trip() -> None:
    """``SADD`` + ``EXPIRE`` + ``XACK`` are three commands and one trip.

    Awaited one at a time they cost three round trips **per message**, on the
    path every consumer of every stream runs — the market-worker's own volume
    is on the order of 700k events/day. They are pipelined without ``MULTI``:
    the three keys can live in different slots, and atomicity was never what
    made this safe anyway. A crash before ``execute`` marks nothing and acks
    nothing, so the message is redelivered and reprocessed, which the durable
    effect's own unique key already covers (ARCHITECTURE.md §5.1).
    """
    client = ProcessedRedis()
    await ack(cast("Any", client), "s", "g", "1-1", _ENVELOPE, now=lambda: _LAST_MINUTE)

    assert client.round_trips == 1
    assert client.pipelines == [False], "MULTI/EXEC would be cross-slot in a cluster"
    assert client.acked == ["1-1"]
    assert await _seen(client, _LAST_MINUTE) is True
