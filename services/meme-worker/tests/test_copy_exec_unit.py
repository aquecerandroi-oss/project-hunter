"""The copy executor's pricing contracts and its obligation discipline, with fakes and no database
(H-037, R2 fix F7/F9/B6/B3). Each test fails when the line it names is removed (the review's mutants):
the exit slot floors, the ``landed`` rule, ``after=entry_at``, the fill deadline counted from the decision,
a retry budget per obligation, a priced sale held across redelivery, a confirmation that waits for its
close and is never consumed by a zero-row update."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.pumpfun.models import NormalizedCurveState
from hunter_meme_worker import copy_exec, copy_exec_exit, copy_exec_facts
from hunter_meme_worker.copy_bets import bet_state_of, build_entry, snapshot_of
from hunter_meme_worker.copy_book import CopyBook
from hunter_meme_worker.copy_events import (
    CloseIntent,
    ConfirmIntent,
    OpenIntent,
    RecordGap,
    RejectEntry,
    leader_ref,
)
from hunter_meme_worker.copy_exec import CopyExecutor
from hunter_meme_worker.copy_history import MintTrace
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_reads import CurveRead
from hunter_meme_worker.copy_stats import CopyStats

from .copy_fakes import FakeClock
from .copy_support import LEADER_A, MINT_1, T0, buy, gap, make_spec, sell

pytestmark = pytest.mark.unit

ENTRY_AT = T0 + timedelta(seconds=10)


def _state(
    slot: int, at: datetime, *, vsol: str = "30", vtok: str = "1073000000"
) -> NormalizedCurveState:  # type: ignore[no-untyped-def]
    return NormalizedCurveState(
        mint=MINT_1,
        virtual_sol_reserves=Decimal(vsol),
        virtual_token_reserves=Decimal(vtok),
        real_sol_reserves=Decimal("0.5"),
        real_token_reserves=Decimal("700000000"),
        total_supply=Decimal("1000000000"),
        complete=False,
        market_cap_sol=Decimal("30"),
        source="solana_rpc",
        mayhem_enabled=False,
        slot=slot,
        observed_at=at,
        received_at=at,
    )


class FakeReader:
    def __init__(self, read: CurveRead | None = None) -> None:
        self.read = read
        self.calls: list[dict[str, Any]] = []
        self.last_refused: dict[str, str] = {}

    async def curve_at(self, mint: str, **kwargs: Any) -> CurveRead | None:
        self.calls.append({"mint": mint, **kwargs})
        return self.read


def _executor(
    reader: FakeReader, *, retrace: Any = None, **spec_overrides: Any
) -> tuple[CopyExecutor, Live, list[Any], dict[str, int]]:
    spec = make_spec(**spec_overrides)
    book = CopyBook(spec, t0=T0 - timedelta(hours=1))
    deferred: list[Any] = []
    calls = {"failed": 0, "ok": 0}
    executor = CopyExecutor(
        spec=spec,
        session_factory=None,  # type: ignore[arg-type]
        reader=reader,  # type: ignore[arg-type]
        book=book,
        stats=CopyStats(sorted(spec.wallets)),
        clock=FakeClock(T0 + timedelta(seconds=30)),
        defer=deferred.append,
        funnel_failed=lambda since=None: calls.__setitem__("failed", calls["failed"] + 1),
        funnel_ok=lambda: calls.__setitem__("ok", calls["ok"] + 1),
        retrace=retrace,
    )
    event = buy(at=T0)
    intent = OpenIntent(
        "k1",
        MINT_1,
        leader_ref(event, "regra"),
        T0,
        T0 + timedelta(milliseconds=spec.execution_latency_ms),
    )
    entry = build_entry(spec, snapshot_of(_state(100, ENTRY_AT)), intent, queued_at=T0, slot=100)
    state = bet_state_of(bet_id="b", rule_set_id="rs", mint=MINT_1, entry=entry, mayhem=False)
    live = Live(bet_id="b", state=state, leader=LEADER_A, last_slot=100)
    executor.live["k1"] = live
    book.recover_open(
        key="k1", mint=MINT_1, leader=LEADER_A, stratum="regra", bet_id="b",
        entry_at=ENTRY_AT, peak_atoms=1_000_000,
    )  # fmt: skip
    return executor, live, deferred, calls


def _close(leader_slot: int = 2_000, *, target_at=T0 + timedelta(seconds=40)) -> CloseIntent:  # type: ignore[no-untyped-def]
    event = sell(at=target_at, position_after=0)
    leader = leader_ref(event, "regra")
    object.__setattr__(leader, "slot", leader_slot)
    return CloseIntent("k1", MINT_1, "leader_exit_full", leader, target_at, target_at)


async def _drive(executor: CopyExecutor, job: Any) -> None:
    """What ``run()`` does for one job: admit it (lock, in-flight), take the gate, run it guarded."""
    executor._admit(job)  # pyright: ignore[reportPrivateUsage]
    await executor._gate.acquire()  # pyright: ignore[reportPrivateUsage]
    await executor._guarded(job)  # pyright: ignore[reportPrivateUsage]


def _read(slot: int = 9_000) -> CurveRead:
    return CurveRead(snapshot_of(_state(slot, T0 + timedelta(minutes=5))), slot)


# ---------------------------------------------------------------------------------- F7: exit floors
async def test_the_exit_floor_is_above_the_leaders_own_slot_when_that_is_the_higher() -> None:
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader)
    live.last_slot = 100
    await executor._priced_exit(live, _close(leader_slot=2_000))  # pyright: ignore[reportPrivateUsage]
    assert reader.calls[0]["min_slot"] == 2_001  # max(100, 2000) + 1


async def test_the_exit_floor_is_above_the_copys_last_accepted_slot_when_that_is_the_higher() -> (
    None
):
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader)
    live.last_slot = 5_000
    await executor._priced_exit(live, _close(leader_slot=2_000))  # pyright: ignore[reportPrivateUsage]
    assert reader.calls[0]["min_slot"] == 5_001  # strictly above, never equal


async def test_an_exit_decided_before_the_fill_waits_the_latency_after_the_entry() -> None:
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader, exec_latency_s="1.65")
    early = _close(target_at=T0 + timedelta(seconds=1))  # decided long before the fill landed
    await executor._priced_exit(live, early)  # pyright: ignore[reportPrivateUsage]
    assert reader.calls[0]["not_before"] == ENTRY_AT + timedelta(milliseconds=1650)


async def test_a_late_exit_keeps_its_own_target_when_that_is_after_the_landing() -> None:
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader, exec_latency_s="1.65")
    late = _close(target_at=T0 + timedelta(minutes=3))
    await executor._priced_exit(live, late)  # pyright: ignore[reportPrivateUsage]
    assert reader.calls[0]["not_before"] == late.target_at


async def test_the_exit_is_never_priced_at_the_state_the_entry_used() -> None:
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader)
    await executor._priced_exit(live, _close())  # pyright: ignore[reportPrivateUsage]
    assert reader.calls[0]["after"] == live.state.entry_at == ENTRY_AT


async def test_the_exit_window_runs_from_the_pricing_instant() -> None:
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader, exit_window_s=60)
    await executor._priced_exit(live, _close())  # pyright: ignore[reportPrivateUsage]
    call = reader.calls[0]
    assert call["deadline"] == call["not_before"] + timedelta(seconds=60)


# ---------------------------------------------------------------------------------- F9: fill deadline
async def test_the_fill_deadline_counts_from_the_decision_not_from_the_target() -> None:
    reader = FakeReader(None)
    executor, _, *_ = _executor(reader, exec_latency_s="1.65")
    decided = T0 + timedelta(milliseconds=7)
    job = OpenIntent(
        "k2",
        MINT_1,
        leader_ref(buy(at=T0), "regra"),
        decided,
        decided + timedelta(milliseconds=1650),
    )
    await executor._price_open(job)  # pyright: ignore[reportPrivateUsage]
    call = reader.calls[0]
    assert call["not_before"] == decided + timedelta(milliseconds=1650)
    assert call["deadline"] == decided + timedelta(seconds=30)  # NOT target + 30 s
    assert call["min_slot"] == job.leader.slot + 1


# ---------------------------------------------------------------------------------- B6: redelivery
def _session_factory(cls: Any) -> Any:
    def make(*args: Any, **kwargs: Any) -> Any:
        return cls()

    return make


def _patch_close(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> list[Any]:
    persisted: list[Any] = []

    class _Session:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *exc: object) -> None:
            return None

    async def fake_close(
        session: object, bet_id: str, closed: Any, *, mark_source: Any, stamp: str
    ) -> bool:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        persisted.append(closed)
        return bool(outcome)

    monkeypatch.setattr(copy_exec_exit, "role_session", _session_factory(_Session))
    monkeypatch.setattr(copy_exec_exit, "close_copy_bet", fake_close)
    monkeypatch.setattr(copy_exec, "RETRY_BASE_S", 0.0)
    return persisted


async def test_a_sale_priced_before_a_database_failure_is_redelivered_with_the_same_price(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted = _patch_close(monkeypatch, [RuntimeError("db down"), True])
    reader = FakeReader(_read())
    executor, *_ = _executor(reader)
    job = _close()
    await _drive(executor, job)
    assert len(reader.calls) == 1 and not persisted
    reader.read = _read(slot=99_999)  # the market moved: a repricing would show it
    executor._unpark(job.oid)  # pyright: ignore[reportPrivateUsage]
    await _drive(executor, job)
    assert len(reader.calls) == 1  # NOT priced again
    assert len(persisted) == 1 and persisted[0].exit["snapshot"]["observed_at"]


async def test_each_obligation_has_its_own_retry_budget_keyed_per_gap() -> None:
    executor, _, _, calls = _executor(FakeReader())
    gaps = [RecordGap(gap(T0 + timedelta(seconds=i), None, reason="nats_silent")) for i in range(6)]
    for g in gaps:  # six DISTINCT gaps, each failing once
        executor._failed(g)  # pyright: ignore[reportPrivateUsage]
    assert executor._stats.persist_dropped == 0 and calls["failed"] == 0  # pyright: ignore[reportPrivateUsage]
    for _ in range(copy_exec.MAX_RETRIES):  # ONE gap failing past its budget
        executor._failed(gaps[0])  # pyright: ignore[reportPrivateUsage]
    assert executor._stats.persist_dropped == 1 and calls["failed"] == 1  # pyright: ignore[reportPrivateUsage]
    assert executor._stats.gaps_lost == 1  # pyright: ignore[reportPrivateUsage]


async def test_an_exhausted_funnel_fact_declares_the_funnel_unavailable() -> None:
    executor, _, _, calls = _executor(FakeReader())
    reject = RejectEntry(MINT_1, leader_ref(buy(), "regra"), "nao_primeira", T0)
    for _ in range(copy_exec.MAX_RETRIES + 1):
        executor._failed(reject)  # pyright: ignore[reportPrivateUsage]
    assert calls["failed"] == 1


async def test_an_exhausted_entry_gives_the_slot_back_and_declares_the_funnel_unavailable() -> None:
    executor, _, _, calls = _executor(FakeReader())
    book = executor._book  # pyright: ignore[reportPrivateUsage]
    fresh = book.on_event(buy(mint=MINT_1 + "z", at=T0), T0).jobs[0]
    assert isinstance(fresh, OpenIntent) and book.occupied("regra") == 2
    for _ in range(copy_exec.MAX_RETRIES + 1):
        executor._failed(fresh)  # pyright: ignore[reportPrivateUsage]
    assert book.occupied("regra") == 1 and calls["failed"] == 1


async def test_an_exit_confirmation_waits_for_its_close_it_is_parked_not_failed() -> None:
    executor, live, *_ = _executor(FakeReader())
    job = ConfirmIntent("k1", "SIG", "exit", 120)
    await _drive(executor, job)
    assert executor.is_parked(job.oid)
    assert executor._stats.persist_dropped == 0 and not executor._stats.confirm_delay_ms  # pyright: ignore[reportPrivateUsage]
    assert live.bet_id == "b"


async def test_a_zero_row_update_is_not_consumed_as_a_confirmation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Session:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, *exc: object) -> None:
            return None

    async def no_row(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(copy_exec_facts, "role_session", _session_factory(_Session))
    monkeypatch.setattr(copy_exec_facts, "set_copy_fact", no_row)
    monkeypatch.setattr(copy_exec, "RETRY_BASE_S", 0.0)
    executor, *_ = _executor(FakeReader())
    job = ConfirmIntent("k1", "SIG", "entry", 120)  # entry kind: the row exists (live)
    await _drive(executor, job)
    assert executor.is_parked(job.oid)  # retried, because nothing was written
    assert not executor._stats.confirm_delay_ms  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------------- p90 causal order
async def test_the_p90_exit_is_unavailable_when_the_p90_purchase_came_after_the_exit_intent() -> (
    None
):
    reader = FakeReader(_read())
    executor, live, *_ = _executor(reader)
    written: list[dict[str, Any]] = []

    async def capture(bet_id: str, where: str, value: dict[str, Any]) -> None:
        written.append(value)

    executor._write = capture  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
    job = _close(target_at=T0 + timedelta(seconds=40))
    late_p90 = {"observed_at": job.decided_at + timedelta(seconds=1), "slot": 1, "tokens": "1",
                "sol_spent": "1", "curve_cost_sol": "1"}  # fmt: skip
    await executor.exit_p90(live.state, late_p90, job, "b")
    await executor.exit_p90(live.state, None, job, "b")
    assert written == [{"unavailable": "causal_order"}, {"unavailable": "no_entry_p90"}]
    assert (
        reader.calls == []
    )  # it never even read a state: a sale before the purchase is not priced


# ---------------------------------------------------------------------------------- R2 round 3
async def test_an_exit_waits_for_an_entry_still_being_delivered_instead_of_vanishing() -> None:
    executor, *_ = _executor(FakeReader(_read()))
    del executor.live["k1"]  # the entry write failed once: its row is not there yet ...
    book = executor._book  # pyright: ignore[reportPrivateUsage]
    assert book.position("k1") is not None  # ... but the book still holds the position
    job = _close()
    await _drive(executor, job)
    assert executor.is_parked(job.oid)  # parked: NOT consumed as "nothing to sell"
    assert book.position("k1") is not None and executor._stats.persist_dropped == 0  # pyright: ignore[reportPrivateUsage]


async def test_an_exit_of_an_entry_that_was_abandoned_is_dropped_quietly() -> None:
    executor, *_ = _executor(FakeReader(_read()))
    del executor.live["k1"]
    executor._book.mark_closed("k1")  # pyright: ignore[reportPrivateUsage]
    job = _close()
    await _drive(executor, job)
    assert not executor.is_parked(job.oid)


async def test_a_job_interrupted_by_the_lanes_stop_is_handed_back_not_lost() -> None:
    executor, *_ = _executor(FakeReader(_read()))
    started = asyncio.Event()

    async def hang(job: Any) -> None:
        started.set()
        await asyncio.Event().wait()

    executor._handle = hang  # type: ignore[method-assign]  # pyright: ignore[reportPrivateUsage]
    job = RejectEntry(MINT_1, leader_ref(buy(), "regra"), "nao_primeira", T0)
    task = asyncio.create_task(_drive(executor, job))
    executor._tasks.add(task)  # pyright: ignore[reportPrivateUsage]
    await started.wait()
    handed_back = await executor.shutdown()
    assert [j.oid for j in handed_back] == [job.oid]


async def test_a_censor_for_a_hole_is_lifted_when_the_leaders_position_can_be_re_read() -> None:
    async def readable(wallet: str, mint: str, since: datetime) -> MintTrace | None:
        return MintTrace(0, 1_000_000)

    async def unreadable(wallet: str, mint: str, since: datetime) -> MintTrace | None:
        return None

    for retrace, lifted in ((readable, True), (unreadable, False)):
        executor, live, *_ = _executor(FakeReader(_read()), retrace=retrace)
        job = CloseIntent(
            "k1", MINT_1, "leader_exit_full", _close().leader, T0, T0, "worker_restart_gap"
        )
        priced = await executor._price_close(live, job)  # pyright: ignore[reportPrivateUsage]
        assert (priced.censor is None) is lifted
        if lifted:
            position = executor._book.position("k1")  # pyright: ignore[reportPrivateUsage]
            assert position is not None and position.contam == "worker_restart_gap"
            assert priced.closed.exit["copy"]["contaminated"] == "worker_restart_gap"
        else:
            assert priced.censor == "worker_restart_gap"


async def test_a_job_cancelled_before_its_first_step_is_handed_back_not_lost() -> None:
    """R2 round 4 (MF2): the task exists but has not started when the lane stops - its own cancellation
    handler never runs, so the executor must remember which job each task carries."""
    executor, *_ = _executor(FakeReader(_read()))
    queue: asyncio.Queue[Any] = asyncio.Queue()
    runner = asyncio.create_task(executor.run(queue))
    job = RejectEntry(MINT_1, leader_ref(buy(), "regra"), "nao_primeira", T0)
    queue.put_nowait(job)
    for _ in range(
        3
    ):  # the runner takes the job and creates its task; the task has not started yet
        await asyncio.sleep(0)
        if executor.in_flight:
            break
    assert executor.in_flight == 1
    handed_back = await executor.shutdown()
    runner.cancel()
    await asyncio.gather(runner, return_exceptions=True)
    assert [j.oid for j in handed_back] == [job.oid]


async def test_a_job_taken_from_the_queue_while_the_lane_stops_goes_back_to_it() -> None:
    executor, *_ = _executor(FakeReader(_read()))
    queue: asyncio.Queue[Any] = asyncio.Queue()
    await executor.shutdown()  # closing
    job = RejectEntry(MINT_1, leader_ref(buy(), "regra"), "nao_primeira", T0)
    queue.put_nowait(job)
    await executor.run(queue)  # takes it, sees it is closing, returns
    assert queue.qsize() == 1 and queue.get_nowait() is job


async def test_an_exit_that_waits_for_ever_on_a_missing_entry_is_given_up_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R2 round 4 (MF1): running out of waits for the entry's row is a lost exit, not a lost annotation:
    the position goes back to open (the time cap decides) and the funnel is declared down."""
    monkeypatch.setattr(copy_exec, "MAX_WAITS", 1)
    monkeypatch.setattr(copy_exec, "WAIT_S", 0.0)
    executor, _, deferred, calls = _executor(FakeReader(_read()))
    del executor.live["k1"]
    job = _close()
    for _ in range(3):
        await _drive(executor, job)
        for parked in list(deferred):
            deferred.remove(parked)
    assert calls["failed"] == 1  # given up: the funnel is told
    assert executor._stats.annotation_lost == 0  # pyright: ignore[reportPrivateUsage]
