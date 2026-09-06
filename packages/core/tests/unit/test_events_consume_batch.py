"""``consume_batches()``: one round trip per batch, not three per message (T2.5d).

The measurement that forced this (``.claude/state/t25-proof.md``, T2.5c section 3):
the scanner's ``market.ticks`` consumer sustained ~71 msg/s against 151 produced
and sat ~95 000 messages behind, on a stream whose whole handling is a dict
touch. The cost was never the handling -- it was three sequential round trips per
message: ``SISMEMBER`` today, ``SISMEMBER`` yesterday, then a pipelined ``ack``.

So the batch path collapses the guard into one pipelined ``SMISMEMBER`` per day
and the completion into one pipelined ``SADD``/``EXPIRE``/``XACK``. What it does
**not** do is change ``consume()``: the per-message guard is evaluated as late as
it is today, because anticipating it for a whole batch widens the window in which
another consumer of the same group can finish the same ``event_id`` first (Astra,
T2.5d design review, must-fix 2).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from hunter_core.events.consume import (
    DEFAULT_BLOCK_MS,
    PROCESSED_TTL_S,
    ack_many,
    consume,
    consume_batches,
)
from hunter_core.events.envelope import EventEnvelope
from hunter_core.events.produce import FIELD_NAME
from hunter_core.redis import keys

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


class BatchRedis:
    """Every call the batch path makes, counted so round trips can be asserted."""

    def __init__(self, reads: list[Any], *, claims: list[Any] | None = None) -> None:
        self.reads = list(reads)
        self.claims = list(claims or [])
        self.members: dict[str, set[str]] = {}
        self.ttls: dict[str, int] = {}
        self.acked: list[str] = []
        self.round_trips = 0
        self.sismember_calls = 0
        self.smismember_calls = 0
        self.read_counts: list[int] = []
        self.block_values: list[int] = []

    # --- server calls -----------------------------------------------------
    async def xgroup_create(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def xautoclaim(self, *args: Any, **kwargs: Any) -> Any:
        if self.claims:
            return self.claims.pop(0)
        return [b"0-0", [], []]

    async def xreadgroup(self, *args: Any, **kwargs: Any) -> Any:
        self.read_counts.append(int(kwargs["count"]))
        self.block_values.append(int(kwargs["block"]))
        if not self.reads:
            raise AssertionError("the generator read more times than the test scripted")
        outcome = self.reads.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def sismember(self, key: str, member: str) -> bool:
        self.sismember_calls += 1
        self.round_trips += 1
        return member in self.members.get(key, set())

    async def xack(self, _stream: str, _group: str, *message_ids: Any) -> int:
        self.round_trips += 1
        self.acked.extend(str(item) for item in message_ids)
        return len(message_ids)

    def pipeline(self, transaction: bool = True) -> _Pipeline:
        assert transaction is False, "MULTI/EXEC would be cross-slot in a cluster"
        return _Pipeline(self)

    # --- helpers ----------------------------------------------------------
    def mark(self, group: str, event_id: str, *, day: datetime = NOW) -> None:
        self.members.setdefault(keys.processed(group, day.date()), set()).add(event_id)


class _Pipeline:
    """Buffers like the real asyncio pipeline: nothing leaves until ``execute``."""

    def __init__(self, client: BatchRedis) -> None:
        self._client = client
        self._queued: list[Callable[[], object]] = []

    async def __aenter__(self) -> _Pipeline:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def smismember(self, key: str, members: list[str]) -> _Pipeline:
        self._client.smismember_calls += 1

        def run() -> list[bool]:
            held = self._client.members.get(key, set())
            return [member in held for member in members]

        self._queued.append(run)
        return self

    def sadd(self, key: str, *members: str) -> _Pipeline:
        self._queued.append(lambda: self._client.members.setdefault(key, set()).update(members))
        return self

    def expire(self, key: str, ttl: int) -> _Pipeline:
        self._queued.append(lambda: self._client.ttls.__setitem__(key, ttl))
        return self

    def xack(self, _stream: str, _group: str, *message_ids: str) -> _Pipeline:
        self._queued.append(lambda: self._client.acked.extend(message_ids))
        return self

    async def execute(self) -> list[object]:
        self._client.round_trips += 1
        return [call() for call in self._queued]


def _envelope(n: int) -> EventEnvelope:
    return EventEnvelope(type="t", producer="p", key=f"k:{n}", payload={"n": n})


def _read(envelopes: list[EventEnvelope], *, first: int = 1) -> Any:
    entries = [
        (f"1-{first + index}".encode(), {FIELD_NAME: envelope.to_bytes()})
        for index, envelope in enumerate(envelopes)
    ]
    return [(b"market.ticks", entries)]


def _client(reads: list[Any], **kwargs: Any) -> Any:
    return cast("Any", BatchRedis(reads, **kwargs))


async def _first_batch(client: Any, **kwargs: Any) -> list[tuple[str, EventEnvelope]]:
    gen = consume_batches(client, "market.ticks", "g", "c", now=lambda: NOW, **kwargs)
    batch = await gen.__anext__()
    await gen.aclose()
    return batch


async def test_a_whole_batch_is_delivered_at_once_and_asks_for_the_batch_size() -> None:
    """The read is one ``XREADGROUP`` with ``COUNT=batch``, and what comes back
    reaches the caller as one list -- that is what lets the scanner coalesce."""
    client = _client([_read([_envelope(index) for index in range(50)])])

    batch = await _first_batch(client, batch=500)

    assert [envelope.payload["n"] for _id, envelope in batch] == list(range(50))
    assert client.read_counts == [500]
    assert client.block_values == [DEFAULT_BLOCK_MS]


async def test_the_guard_costs_one_round_trip_per_batch_not_two_per_message() -> None:
    """The regression this task exists for: 500 messages used to cost 1000
    ``SISMEMBER`` round trips before the first of them was even handled."""
    client = _client([_read([_envelope(index) for index in range(500)])])

    batch = await _first_batch(client, batch=500)

    assert len(batch) == 500
    assert client.sismember_calls == 0
    assert client.smismember_calls == 2, "one SMISMEMBER per day read, not one per message"
    assert client.round_trips == 1


async def test_an_event_already_processed_is_never_delivered_and_is_acked_away() -> None:
    """Idempotency by ``event_id`` is preserved verbatim: a redelivery of
    something this group already finished is filtered *and* acked, so it stops
    being redelivered."""
    envelopes = [_envelope(index) for index in range(3)]
    client = _client([_read(envelopes)])
    client.mark("g", str(envelopes[1].event_id))

    batch = await _first_batch(client)

    assert [envelope.payload["n"] for _id, envelope in batch] == [0, 2]
    assert client.acked == ["1-2"], "the message of a processed event is acked, not left pending"


async def test_two_deliveries_of_one_event_id_are_both_delivered() -> None:
    """Collapsing them here would ack a message whose effect never happened.

    A handler that fails on the first delivery leaves the event unmarked, and
    today the second delivery is what gets it done. So the batch path delivers
    every unprocessed entry and lets the caller decide (Astra, T2.5d design
    review, must-fix 1).
    """
    envelope = _envelope(7)
    entries = [
        (b"1-1", {FIELD_NAME: envelope.to_bytes()}),
        (b"1-2", {FIELD_NAME: envelope.to_bytes()}),
    ]
    client = _client([[(b"market.ticks", entries)]])

    batch = await _first_batch(client)

    assert [message_id for message_id, _envelope in batch] == ["1-1", "1-2"]
    assert client.acked == []


async def test_one_unreadable_message_does_not_hold_back_the_readable_ones() -> None:
    """499 good messages must not be lost because the 500th is garbage; the bad
    one is left pending and reported, never acked away silently."""
    good = _envelope(1)
    entries = [
        (b"1-1", {FIELD_NAME: good.to_bytes()}),
        (b"1-2", {b"nothing": b"useful"}),
        (b"1-3", {FIELD_NAME: b"not-an-envelope"}),
    ]
    client = _client([[(b"market.ticks", entries)]])

    batch = await _first_batch(client)

    assert [message_id for message_id, _envelope in batch] == ["1-1"]
    assert client.acked == []


async def test_a_reclaimed_message_is_delivered_too_and_still_guarded() -> None:
    """A crash leaves messages pending; ``XAUTOCLAIM`` brings them back. The
    ones whose effect was already marked are dropped, the rest are re-delivered
    -- no loss, no duplicate effect."""
    survived, done = _envelope(1), _envelope(2)
    claimed = [
        b"0-0",
        [(b"1-1", {FIELD_NAME: survived.to_bytes()}), (b"1-2", {FIELD_NAME: done.to_bytes()})],
        [],
    ]
    client = _client([[]], claims=[claimed])
    client.mark("g", str(done.event_id))

    batch = await _first_batch(client)

    assert [message_id for message_id, _envelope in batch] == ["1-1"]
    assert client.acked == ["1-2"]


async def test_a_reclaim_that_spans_two_pages_delivers_both(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``XAUTOCLAIM`` pages: a cursor that is not ``0-0`` means there is more.

    Recovering a dead instance's pending list is exactly when the batch is
    large, so stopping at the first page would leave the rest for the next
    iteration and make the recovery as slow as the failure was (Astra, T2.5d
    diff review, test gap 1).
    """
    first, second = _envelope(1), _envelope(2)
    pages = [
        [b"5-0", [(b"1-1", {FIELD_NAME: first.to_bytes()})], []],
        [b"0-0", [(b"1-2", {FIELD_NAME: second.to_bytes()})], []],
    ]
    client = _client([[]], claims=pages)

    gen = consume_batches(client, "market.ticks", "g", "c", now=lambda: NOW)
    delivered = [await gen.__anext__(), await gen.__anext__()]
    await gen.aclose()

    assert [message_id for batch in delivered for message_id, _envelope in batch] == ["1-1", "1-2"]
    assert client.read_counts == [], "the second page came from the reclaim, not from a new read"


async def test_the_guard_of_a_batch_read_before_midnight_still_holds_after_it() -> None:
    """A batch read at 23:59:59 and acked at 00:00:01 marks **today's** key, and
    the redelivery that follows is read against today and yesterday — so the
    seam at midnight closes for the batch path exactly as it does for
    :func:`ack` (Astra, T2.5d diff review, test gap 2)."""
    before = datetime(2026, 9, 6, 23, 59, 59, tzinfo=UTC)
    after = datetime(2026, 9, 7, 0, 0, 1, tzinfo=UTC)
    envelopes = [_envelope(index) for index in range(2)]
    client = _client([_read(envelopes), _read(envelopes)])

    gen = consume_batches(client, "market.ticks", "g", "c", now=lambda: before)
    batch = await gen.__anext__()
    await gen.aclose()
    await ack_many(client, "market.ticks", "g", batch, now=lambda: after)

    assert set(client.members) == {keys.processed("g", after.date())}
    gen = consume_batches(client, "market.ticks", "g", "c", now=lambda: after)
    assert await gen.__anext__() == []
    await gen.aclose()


async def test_ack_many_completes_every_message_in_one_round_trip() -> None:
    """Every entry the batch absorbed is completed -- not just the ones that
    produced a distinct effect -- or the rest stay pending and come back forever
    (Astra, T2.5d design review, must-fix 3)."""
    envelopes = [_envelope(index) for index in range(4)]
    client = _client([])
    items = [(f"1-{index}", envelope) for index, envelope in enumerate(envelopes, start=1)]

    await ack_many(client, "market.ticks", "g", items, now=lambda: NOW)

    assert client.round_trips == 1
    assert client.acked == ["1-1", "1-2", "1-3", "1-4"]
    key = keys.processed("g", NOW.date())
    assert client.members[key] == {str(envelope.event_id) for envelope in envelopes}
    assert client.ttls == {key: PROCESSED_TTL_S}


async def test_ack_many_of_nothing_touches_the_server_at_all() -> None:
    client = _client([])

    await ack_many(client, "market.ticks", "g", [], now=lambda: NOW)

    assert client.round_trips == 0


async def test_what_ack_many_marked_is_what_the_next_batch_filters_out() -> None:
    """The loop the proof depends on: handle, ack the batch, and a redelivery
    of the same messages after a crash yields nothing."""
    envelopes = [_envelope(index) for index in range(3)]
    client = _client([_read(envelopes), _read(envelopes)])

    first = await _first_batch(client)
    await ack_many(client, "market.ticks", "g", first, now=lambda: NOW)

    gen = consume_batches(client, "market.ticks", "g", "c", now=lambda: NOW)
    again = await gen.__anext__()
    await gen.aclose()
    assert again == []
    assert client.acked == ["1-1", "1-2", "1-3", "1-1", "1-2", "1-3"]


async def test_consume_still_guards_one_message_at_a_time() -> None:
    """Nothing changes for a caller that does not ask for batches: the guard is
    still evaluated per message, immediately before that message is yielded."""
    client = _client([_read([_envelope(index) for index in range(3)])])

    gen = consume(client, "market.ticks", "g", "c", now=lambda: NOW)
    await gen.__anext__()
    await gen.aclose()

    assert client.sismember_calls == 2, "today and yesterday, for the first message only"
    assert client.smismember_calls == 0
