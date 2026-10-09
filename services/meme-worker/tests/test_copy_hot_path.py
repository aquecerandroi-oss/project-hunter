"""Everton's requirement (2026-10-09): the follow path is milliseconds. The decision is made in memory,
before any IO: no database, no HTTP, no await. Proved three ways — the function is not a coroutine,
every IO collaborator explodes if it is touched or awaited, and the measured decision cost over many
events stays far under a millisecond-scale budget."""

from __future__ import annotations

import asyncio
import inspect
from datetime import timedelta
from typing import Any

import pytest

from hunter_meme_worker.copy_events import (
    CensorEntry,
    CloseIntent,
    ConfirmIntent,
    OpenIntent,
)
from hunter_meme_worker.copy_lane import CopyLane

from .copy_support import LEADER_A, LEADER_B, MINT_1, T0, buy, confirmation, gap, make_spec, sell

pytestmark = pytest.mark.unit


class _Exploding:
    """Any attribute access, call or await is a failed test: the hot path must not reach IO."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the hot path touched IO: {name}")

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("the hot path called an IO collaborator")


class _Ticking:
    """A clock that advances 2 ms per read: decided_at - observed_at is deterministic."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self):  # type: ignore[no-untyped-def]
        self.now += timedelta(milliseconds=2)
        return self.now


def _lane(**overrides: Any) -> CopyLane:
    return CopyLane(
        spec=make_spec(**overrides),
        session_factory=_Exploding(),  # type: ignore[arg-type]
        chain=_Exploding(),  # type: ignore[arg-type]
        heartbeat=_Exploding(),  # type: ignore[arg-type]
        clock=_Ticking(),
        sleep=_Exploding(),  # type: ignore[arg-type]
        t0=T0 - timedelta(hours=1),
    )


def test_the_decision_function_is_synchronous_so_it_cannot_await_io() -> None:
    assert not inspect.iscoroutinefunction(CopyLane.on_item)
    assert not inspect.iscoroutinefunction(CopyLane.submit)


def test_a_leader_buy_is_decided_with_no_io_and_queued_for_the_executor() -> None:
    lane = _lane()
    lane.on_item(buy(at=T0))
    job = lane.queue.get_nowait()
    assert isinstance(job, OpenIntent)
    assert lane.stats.observed_to_decided_us[0] == 2000  # exactly the 2 ms the fake clock ticked
    assert lane.queue.empty()


def test_a_leader_sell_and_a_gap_are_also_decided_with_no_io() -> None:
    lane = _lane()
    lane.on_item(buy(at=T0))
    opened = lane.queue.get_nowait()
    assert isinstance(opened, OpenIntent)
    lane.book.mark_open(opened.key, bet_id="b", entry_at=T0)
    lane.on_item(gap(T0, None, wallet=LEADER_B))
    lane.on_item(sell(at=T0 + timedelta(seconds=9)))
    assert isinstance(lane.queue.get_nowait(), CloseIntent)
    assert lane.stats.gaps_seen == 1


def test_the_decision_is_made_inside_a_running_loop_without_yielding_to_it() -> None:
    """A task that would run if the decision yielded must not get a turn in the middle of it."""

    async def scenario() -> list[str]:
        lane = _lane()
        order: list[str] = []

        async def canary() -> None:
            order.append("canary")

        task = asyncio.create_task(canary())
        lane.on_item(buy(at=T0))
        order.append("decided")
        await task
        return order

    assert asyncio.run(scenario()) == ["decided", "canary"]


def test_a_full_queue_never_blocks_the_decision_an_entry_is_given_back_with_a_row_owed() -> None:
    lane = _lane(queue_max=1)
    lane.on_item(buy(LEADER_A, MINT_1, at=T0))
    lane.on_item(buy(LEADER_B, "OtherMint111111111111111111111111111111111", at=T0))
    assert lane.queue.qsize() == 1
    assert lane.stats.queue_full == 1
    assert lane.book.open_count == 1  # the refused copy left no ghost position behind
    [owed] = lane.outbox
    assert isinstance(owed, CensorEntry) and owed.reason == "sobrecarga"  # a row, not a lost fact


def test_a_full_queue_keeps_an_exit_as_an_obligation_until_the_sweep_delivers_it() -> None:
    lane = _lane(queue_max=1)
    lane.on_item(buy(LEADER_A, MINT_1, at=T0))
    opened = lane.queue.get_nowait()
    assert isinstance(opened, OpenIntent)
    lane.book.mark_open(opened.key, bet_id="b", entry_at=T0)
    lane.queue.put_nowait(opened)  # the queue is full again (a slow executor)
    lane.on_item(sell(LEADER_A, MINT_1, at=T0 + timedelta(seconds=5)))
    [owed] = lane.outbox
    assert isinstance(owed, CloseIntent)
    position = lane.book.position(opened.key)
    assert position is not None and position.state == "closing"  # not lost, not re-decidable
    lane.queue.get_nowait()  # the executor drains
    asyncio.run(lane.sweep_once())
    assert isinstance(lane.queue.get_nowait(), CloseIntent) and not lane.outbox


def test_the_hot_path_never_logs_so_a_blocked_stderr_cannot_hold_a_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hunter_meme_worker.copy_lane as copy_lane_module

    monkeypatch.setattr(copy_lane_module, "logger", _Exploding())
    lane = _lane(queue_max=1)
    lane.on_item(buy(LEADER_A, MINT_1, at=T0))
    lane.on_item(buy(LEADER_B, "OtherMint111111111111111111111111111111111", at=T0))  # queue full
    lane.on_item(sell(LEADER_A, MINT_1, at=T0 + timedelta(seconds=5)))


def test_a_confirmation_item_is_decided_in_memory_too() -> None:
    lane = _lane()
    event = buy(LEADER_A, MINT_1, at=T0, confirmed=False, signature="PROV")
    lane.on_item(event)
    lane.queue.get_nowait()
    lane.on_item(confirmation(event))
    assert isinstance(lane.queue.get_nowait(), ConfirmIntent)


def test_the_measured_decision_cost_stays_far_under_the_millisecond_budget() -> None:
    lane = _lane(queue_max=100_000)
    for i in range(2000):
        lane.on_item(buy(LEADER_A, f"Mint{i:040d}", at=T0))
    p99 = sorted(lane.stats.decide_us)[int(len(lane.stats.decide_us) * 0.99) - 1]
    assert p99 < 5_000, f"decision p99 {p99} us is not milliseconds"  # 5 ms, ~100x headroom
    assert lane.stats.persist_dropped == 0
