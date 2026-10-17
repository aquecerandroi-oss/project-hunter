"""The copy lane's state around the database (H-037, R2 fix B3/B2e), without a database: the funnel is a
durable global hole that opens when a fact is lost and closes on the next successful write, an outbox that
overflows is a lost fact, gap records are never dropped while there is a place to keep them, and the
frozen defaults are the registered ones. Fakes only."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderGap
from hunter_meme_worker import copy_lane
from hunter_meme_worker.copy_events import (
    CensorEntry,
    CloseIntent,
    OpenIntent,
    RecordGap,
    RejectEntry,
    leader_ref,
)
from hunter_meme_worker.copy_lane import CopyLane
from hunter_meme_worker.copy_retry import Held, Retries

from .copy_fakes import FakeClock
from .copy_support import LEADER_A, MINT_1, MINT_2, T0, buy, gap, make_spec, sell

pytestmark = pytest.mark.unit


class _NoIO:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"touched IO: {name}")


def _lane(**overrides: Any) -> tuple[CopyLane, FakeClock]:
    clock = FakeClock(T0)
    lane = CopyLane(
        spec=make_spec(**overrides),
        session_factory=_NoIO(),  # type: ignore[arg-type]
        chain=_NoIO(),  # type: ignore[arg-type]
        clock=clock,
        sleep=clock.sleep,
        t0=T0 - timedelta(hours=1),
    )
    return lane, clock


def _drain(lane: CopyLane) -> list[Any]:
    out: list[Any] = []
    while not lane.queue.empty():
        out.append(lane.queue.get_nowait())
    return out


def test_a_lost_funnel_fact_opens_one_durable_global_hole_and_blocks_entries() -> None:
    lane, _ = _lane()
    lane.funnel_failed()
    lane.funnel_failed()  # idempotent
    records = [j for j in _drain(lane) if isinstance(j, RecordGap)]
    assert len(records) == 1
    assert records[0].gap.wallet is None and records[0].gap.end is None
    assert records[0].gap.reason == "funil_indisponivel"
    assert lane.book.funnel_unavailable
    lane.on_item(buy(at=T0 + timedelta(seconds=1)))
    [reject] = [j for j in _drain(lane) if isinstance(j, RejectEntry)]
    assert reject.reason == "lacuna"


def test_the_next_successful_write_closes_the_hole_and_owes_a_recomposition() -> None:
    lane, clock = _lane()
    lane.funnel_failed()
    _drain(lane)
    clock.advance(seconds=12)
    lane.funnel_ok()
    [closed] = [j for j in _drain(lane) if isinstance(j, RecordGap)]
    assert closed.gap.end == T0 + timedelta(seconds=12) and closed.gap.start == T0
    assert not lane.book.funnel_unavailable  # NOT sticky
    assert lane.book.recompositions_pending() == len(lane.spec.wallets)
    lane.funnel_ok()  # idempotent when nothing is down
    assert _drain(lane) == []


def test_funnel_ok_with_nothing_down_does_nothing() -> None:
    lane, _ = _lane()
    lane.funnel_ok()
    assert lane.queue.empty() and not lane.outbox


def test_an_outbox_overflow_of_a_funnel_fact_declares_the_funnel_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(copy_lane, "OUTBOX_MAX", 1)
    lane, _ = _lane(queue_max=1)
    ref = leader_ref(buy(at=T0), "regra")
    lane.queue.put_nowait(RejectEntry(MINT_1, ref, "nao_primeira", T0))  # the queue is full
    lane.submit(CensorEntry(MINT_1, ref, "sem_estado", T0))  # fills the outbox (1)
    assert not lane.book.funnel_unavailable
    lane.submit(RejectEntry(MINT_2, ref, "nao_primeira", T0))  # no room anywhere: a lost fact
    assert lane.stats.outbox_dropped >= 1 and lane.book.funnel_unavailable


def test_an_overflowing_gap_record_is_kept_owed_and_counts_as_a_lost_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(copy_lane, "OUTBOX_MAX", 1)
    lane, _ = _lane(queue_max=1)
    ref = leader_ref(buy(at=T0), "regra")
    lane.queue.put_nowait(RejectEntry(MINT_1, ref, "nao_primeira", T0))
    lane.submit(CensorEntry(MINT_1, ref, "sem_estado", T0))
    lane.submit(RecordGap(gap(T0, None, reason="nats_silent")))
    assert lane.stats.outbox_dropped >= 1
    # the health record is kept (owed) AND counts as a lost funnel fact, as does the hole this declared
    assert {r.gap.reason for r in lane.owed} == {"nats_silent", "funil_indisponivel"}
    assert lane.book.funnel_unavailable
    _drain(lane)
    lane.outbox.clear()
    import asyncio

    asyncio.run(lane.sweep_once())
    assert not lane.owed  # re-submitted once there was room


def test_an_overflowing_exit_goes_back_to_open_so_the_time_cap_still_sees_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(copy_lane, "OUTBOX_MAX", 0)
    lane, _ = _lane(queue_max=1)
    opened = lane.book.on_event(buy(at=T0), T0).jobs[0]
    assert isinstance(opened, OpenIntent)
    lane.book.mark_open(opened.key, bet_id="b", entry_at=T0)
    lane.queue.put_nowait(CensorEntry(MINT_1, opened.leader, "x", T0))
    lane.submit(CloseIntent(opened.key, MINT_1, "leader_exit_full", None, T0, T0))
    lane.book._by_key[opened.key].state = "closing"  # pyright: ignore[reportPrivateUsage]
    lane._defer(CloseIntent(opened.key, MINT_1, "leader_exit_full", opened.leader, T0, T0))  # pyright: ignore[reportPrivateUsage]
    position = lane.book.position(opened.key)
    assert position is not None and position.state != "closing"
    assert sell is not None and LeaderGap is not None


def test_retries_and_held_results_are_bounded() -> None:
    retries = Retries(cap=3)
    for i in range(10):
        retries.bump(f"o{i}")
    assert len(retries) == 3
    held: Held[int] = Held(cap=2)
    for i in range(5):
        held.put(f"o{i}", i)
    assert len(held) == 2 and held.get("o4") == 4 and held.get("o0") is None


def test_the_registered_defaults_are_the_frozen_ones() -> None:
    from hunter_meme_worker.copy_spec import CopySpec

    from .copy_support import LEADER_B

    params: dict[str, Any] = {
        "leaders": [
            {"wallet": LEADER_A, "stratum": "regra"},
            {"wallet": LEADER_B, "stratum": "regra"},
        ],
        "size_sol": "0.05",
        "min_trigger_sol": "0.1",
        "exit_leader_drop_fraction": "0.5",
        "stop_fraction": "0.5",
        "exec_latency_s": "1.65",
    }
    spec = CopySpec.from_params(id="x", name="copy_v0", version="1", params=params)
    from decimal import Decimal

    assert spec.fee_pct == Decimal("1.25")  # the curve's fee per leg, not the Lab's 1.75
    assert spec.priority_fee_sol == Decimal("0.00005")
    assert spec.horizon_days == 30  # emenda 4
    assert spec.fill_window_s == 30 and spec.exit_window_s == 60
    assert spec.stress_latency_s == Decimal("3.9")
    assert spec.time_cap_s == 3600 and spec.max_open_per_stratum == 100


def test_the_funnel_hole_reaches_back_to_the_fact_that_was_lost_not_to_when_the_retries_gave_up() -> (
    None
):
    lane, clock = _lane()
    clock.advance(seconds=15)  # the retries gave up fifteen seconds after the fact was decided
    lane.funnel_failed(T0)
    [record] = [j for j in _drain(lane) if isinstance(j, RecordGap)]
    assert record.gap.start == T0  # NOT T0 + 15 s
    lane.funnel_failed(T0 + timedelta(seconds=5))  # a younger fact: the open hole already covers it
    assert _drain(lane) == []
    lane.funnel_failed(
        T0 - timedelta(seconds=30)
    )  # an OLDER fact lost later: a second hole reaches it
    [older] = [j for j in _drain(lane) if isinstance(j, RecordGap)]
    assert older.gap.start == T0 - timedelta(seconds=30)
    lane.funnel_ok()  # the next successful write closes every open hole
    closed = [j for j in _drain(lane) if isinstance(j, RecordGap)]
    assert sorted(c.gap.start for c in closed) == [T0 - timedelta(seconds=30), T0]
    assert all(c.gap.end == T0 + timedelta(seconds=15) for c in closed)


def test_a_restart_owes_only_the_slices_not_recorded_as_recomposed() -> None:
    from .copy_support import LEADER_B

    lane, _ = _lane()
    hole = gap(T0, T0 + timedelta(seconds=20), wallet=None, reason="no_coverage:a+b")
    lane.book.owe_window(hole, frozenset({LEADER_A}))  # A's slice was already done before the crash
    owed = {w.wallet for w in lane.book.recompositions_due(T0 + timedelta(minutes=1))}
    assert owed == {LEADER_B}


def test_an_entry_the_outbox_has_no_room_for_is_abandoned_and_its_hole_reaches_back_to_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 round 4 (MF1): a parked entry whose redelivery finds the outbox full used to vanish: the book kept
    a position with no row, and the exit waited on it for ever."""
    monkeypatch.setattr(copy_lane, "OUTBOX_MAX", 0)
    lane, _ = _lane(queue_max=1)
    opened = lane.book.on_event(buy(at=T0), T0).jobs[0]
    assert isinstance(opened, OpenIntent)
    lane._defer(opened)  # pyright: ignore[reportPrivateUsage]
    assert lane.book.position(opened.key) is None  # released: no row will ever exist
    assert lane.book.funnel_unavailable
    holes = [j for j in _drain(lane) if isinstance(j, RecordGap)]
    assert [h.gap.start for h in holes] == [opened.decided_at]  # the hole reaches the lost entry


def test_the_liveness_ceiling_is_the_oldest_fact_not_yet_durable() -> None:
    lane, _ = _lane(queue_max=1)
    ref = leader_ref(buy(at=T0), "regra")
    assert lane.oldest_unlanded() is None
    lane.submit(RejectEntry(MINT_1, ref, "nao_primeira", T0 + timedelta(seconds=5)))
    older = CensorEntry(MINT_2, ref, "sem_estado", T0)
    lane.submit(older)
    assert lane.oldest_unlanded() == T0
    lane.settled(older.oid)
    assert lane.oldest_unlanded() == T0 + timedelta(seconds=5)


def test_an_entry_handed_back_as_overload_is_tracked_as_the_censor_that_replaces_it() -> None:
    lane, _ = _lane(queue_max=1)
    lane.queue.put_nowait(RejectEntry(MINT_1, leader_ref(buy(at=T0), "regra"), "x", T0))
    opened = lane.book.on_event(buy(LEADER_A, MINT_2, at=T0), T0).jobs[0]
    assert isinstance(opened, OpenIntent)
    lane.submit(opened)  # refused: rolled back into a censor
    assert opened.oid not in lane._unlanded  # pyright: ignore[reportPrivateUsage]
    assert lane.oldest_unlanded() == T0  # ... but the censor that replaced it is owed
