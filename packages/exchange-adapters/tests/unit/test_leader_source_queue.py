"""Copy-trade pilot (H-037), security R1 LOW-1: the stream queues are finite and an overflow is a gap.

A consumer that stalls must not turn a burst of leader activity into unbounded memory — and what could
not be queued must never vanish silently: the drop is announced as a named gap over the interval."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Collection
from datetime import UTC, datetime, timedelta

import pytest

from hunter_exchanges.pumpfun import leader_source as combinator_module
from hunter_exchanges.pumpfun.leader_events import LeaderEvent, LeaderGap, LeaderItem
from hunter_exchanges.pumpfun.leader_source import CombinedLeaderSource
from hunter_exchanges.pumpfun.leader_source_queue import OverflowQueue
from hunter_exchanges.pumpfun.solana_codec import b58encode

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
W = b58encode(bytes([7]) * 32)


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        self.now += timedelta(milliseconds=5)
        return self.now


def event(i: int) -> LeaderEvent:
    return LeaderEvent(
        wallet=W,
        mint=f"M{i}",
        side="buy",
        token_delta_atoms=1,
        sol_delta_lamports=None,
        position_after_atoms=1,
        signature=f"s{i}",
        slot=i,
        block_time=None,
        first_seen_at=T0,
        fields_complete_at=T0,
        source="nats",
        confirmed=False,
    )


async def test_items_beyond_the_cap_are_dropped_counted_and_announced_at_once() -> None:
    q = OverflowQueue("nats_queue", cap=3, wall=Clock())
    for i in range(10):
        q.put_nowait(event(i))
    assert q.dropped == 7
    got = [await q.get() for _ in range(4)]
    assert got[:3] == [event(0), event(1), event(2)]  # arrival order is kept
    opened = got[3]
    assert isinstance(opened, LeaderGap)  # the open gap sits right behind the kept items
    assert (opened.wallet, opened.reason, opened.end) == (None, "nats_queue_overflow", None)
    closed = await q.get()  # the consumer drained below half the cap: the episode ends
    assert isinstance(closed, LeaderGap) and closed.start == opened.start
    assert (
        closed.end is not None and closed.end > closed.start
    )  # an interval a consumer can test against


async def test_the_overflow_is_announced_even_if_the_consumer_never_drains_below_half() -> None:
    """Astra R3: the announcement must not depend on a drain that a steady load can postpone forever."""
    q = OverflowQueue("x", cap=4, wall=Clock())
    for i in range(5):
        q.put_nowait(event(i))  # one dropped
    seen: list[LeaderItem] = []
    for i in range(5, 25):  # consume one, refill one: the queue never drains
        seen.append(await q.get())
        q.put_nowait(event(i))
    assert any(isinstance(i, LeaderGap) and i.end is None for i in seen)


async def test_open_gaps_beyond_twice_the_cap_are_coalesced_not_queued() -> None:
    q = OverflowQueue("chain_queue", cap=2, wall=Clock())
    for i in range(100):
        q.put_nowait(LeaderGap(W, T0, None, f"chain_ws_down_{i}"))
    assert q.qsize() <= 2 * 2 + 1 and q.gaps_absorbed > 90
    items = [await q.get() for _ in range(q.qsize())]
    assert any(
        isinstance(i, LeaderGap) and i.reason == "chain_queue_overflow" and i.end is None
        for i in items
    )
    after: list[LeaderItem] = []
    for _ in range(q.qsize()):
        after.append(await q.get())
    # the absorbed open gaps come back OPEN with their original start once the queue has drained
    reopened = {i.reason for i in items + after if isinstance(i, LeaderGap) and i.end is None}
    assert {f"chain_ws_down_{i}" for i in range(100)} <= reopened | {
        f"chain_ws_down_{i}" for i in range(5)
    }


async def test_a_thousand_closed_intervals_are_bounded_and_coalesced_per_key() -> None:
    q = OverflowQueue("chain_queue", cap=2, wall=Clock())
    for i in range(1000):
        start = T0 + timedelta(seconds=i)
        q.put_nowait(LeaderGap(W, start, start + timedelta(seconds=1), "chain_tx_unavailable"))
    assert q.qsize() <= 2 * 2 + 1  # bounded, not 1000
    drained: list[LeaderItem] = [await q.get() for _ in range(q.qsize())]
    while q.qsize():
        drained.append(await q.get())
    closed = [i for i in drained if isinstance(i, LeaderGap) and i.reason == "chain_tx_unavailable"]
    assert closed[-1].start <= T0 + timedelta(seconds=5) and closed[-1].end == T0 + timedelta(
        seconds=1000
    )


async def test_an_absorbed_open_gap_survives_the_drain_still_open_with_its_original_start() -> None:
    """Astra R3: a source that is still down must not look recovered just because the queue emptied."""
    clock = Clock()
    q = OverflowQueue("x", cap=2, wall=clock)
    for i in range(4):
        q.put_nowait(LeaderGap("filler", T0, T0 + timedelta(seconds=1), f"r{i}"))
    still_down = LeaderGap(None, T0 + timedelta(seconds=2), None, "still_down")
    q.put_nowait(still_down)  # absorbed: the queue is at its gap ceiling
    clock.now = T0 + timedelta(seconds=10)
    out: list[LeaderItem] = []
    while q.qsize():
        out.append(await q.get())
    reopened = [i for i in out if isinstance(i, LeaderGap) and i.reason == "still_down"]
    assert reopened and reopened[-1].end is None and reopened[-1].start == T0 + timedelta(seconds=2)
    overflow = [i for i in out if isinstance(i, LeaderGap) and i.reason == "x_overflow"]
    assert min(o.start for o in overflow) <= T0 + timedelta(seconds=2)  # the episode covers it


async def test_a_gap_queued_open_still_reaches_the_consumer_closed_when_the_close_is_absorbed() -> (
    None
):
    q = OverflowQueue("x", cap=1, wall=Clock())
    q.put_nowait(LeaderGap(W, T0, None, "nats_disconnect"))  # queued open
    for i in range(3):
        q.put_nowait(LeaderGap("filler", T0, T0 + timedelta(seconds=1), f"r{i}"))
    q.put_nowait(
        LeaderGap(W, T0, T0 + timedelta(seconds=5), "nats_disconnect")
    )  # the close: absorbed
    out: list[LeaderItem] = []
    while q.qsize():
        out.append(await q.get())
    assert any(
        isinstance(i, LeaderGap) and i.reason == "nats_disconnect" and i.end is not None
        for i in out
    )


async def test_one_overflow_episode_is_one_gap_pair_not_one_per_dropped_item() -> None:
    q = OverflowQueue("x", cap=1, wall=Clock())
    for i in range(50):
        q.put_nowait(event(i))
    items = [await q.get() for _ in range(3)]
    assert sum(isinstance(i, LeaderGap) for i in items) == 2 and q.qsize() == 0


async def test_a_queue_that_never_overflows_behaves_like_a_plain_queue() -> None:
    q = OverflowQueue("x", cap=100, wall=Clock())
    for i in range(5):
        q.put_nowait(event(i))
    assert [(await q.get()).signature for _ in range(5)] == [f"s{i}" for i in range(5)]  # type: ignore[union-attr]
    assert q.dropped == 0


class Burst:
    """A NATS stand-in that emits a burst at once and a chain that is silent."""

    def __init__(self, n: int) -> None:
        self.n = n

    async def stream(self, wallets: Collection[str]) -> AsyncIterator[LeaderItem]:
        for i in range(self.n):
            yield event(i)
        await asyncio.sleep(3600)

    async def confirm(self, ev: LeaderEvent) -> object:  # pragma: no cover - never reached
        raise AssertionError


async def test_the_combined_stream_is_bounded_and_a_stalled_consumer_gets_a_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(combinator_module, "QUEUE_MAX", 5)
    src = CombinedLeaderSource(nats=Burst(40), chain=Burst(0), wall=Clock())  # type: ignore[arg-type]
    agen = src.stream([W])
    first = await agen.__anext__()  # the consumer shows up late
    await asyncio.sleep(0.1)  # ... while the burst and its confirmations pile up
    seen: list[LeaderItem] = [first]
    for _ in range(40):
        item = await asyncio.wait_for(agen.__anext__(), 2)
        seen.append(item)
        if isinstance(item, LeaderGap) and item.reason == "combined_queue_overflow":
            break
    else:
        raise AssertionError("the overflow was silent")
    await agen.aclose()  # type: ignore[attr-defined]
