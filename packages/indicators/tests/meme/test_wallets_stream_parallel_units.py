"""CPU plan step 3 (06/10/2026): the parallel engine's parts in isolation — the exact reduction
operators on known values, the chunking, the bounded queue, the named refusal's trip between
processes, and the worker cleanup when an interrupt lands mid-cleanup (real pools). Fixtures, not
data. The end-to-end proofs are in ``test_wallets_stream_parallel.py``.
"""

from __future__ import annotations

import multiprocessing
import pickle
import random
import signal
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from datetime import date
from threading import Lock
from typing import Any

import pytest

from hunter_indicators.meme.wallets.carry import ContractViolation
from hunter_indicators.meme.wallets.stream_metrics import EntityTally
from hunter_indicators.meme.wallets.stream_mint import CopyTally, Tallies
from hunter_indicators.meme.wallets.stream_parallel import abort_pool, bounded, chunks, close_pool

pytestmark = pytest.mark.unit


def test_a_named_refusal_survives_the_trip_back_from_a_worker() -> None:
    again = pickle.loads(pickle.dumps(ContractViolation("repeated_mint", "M1")))  # noqa: S301 — own bytes
    assert isinstance(again, ContractViolation)
    assert again.reason == "repeated_mint"
    assert str(again) == "repeated_mint: M1"


def test_bounded_keeps_at_most_limit_tasks_in_flight_and_yields_every_result() -> None:
    lock, state = Lock(), {"in_flight": 0, "peak": 0}

    class Counting(ThreadPoolExecutor):
        def submit[T](self, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> Future[T]:
            with lock:
                state["in_flight"] += 1
                state["peak"] = max(state["peak"], state["in_flight"])
            return super().submit(fn, *args, **kwargs)

    def slow(x: int) -> int:
        time.sleep(random.Random(x).uniform(0, 0.005))
        return x * x

    out: list[int] = []
    with Counting(max_workers=4) as pool:
        for value in bounded(pool, slow, ((i,) for i in range(40)), limit=3):
            with lock:
                state["in_flight"] -= 1
            out.append(value)
    assert sorted(out) == [i * i for i in range(40)]
    assert state["peak"] <= 3


def test_chunks_keep_whole_mints_in_schedule_order_and_a_big_mint_alone() -> None:
    cost = {"BIG": 900, "a": 40, "b": 30, "c": 20, "d": 5, "e": 5, "zero": 0}
    schedule = ("BIG", "a", "b", "c", "d", "e", "zero")
    out = chunks(schedule, cost.__getitem__, parts=10)  # target = 1000 // 10 = 100
    assert [m for chunk in out for m in chunk] == list(schedule)
    assert out[0] == ("BIG",)
    assert all(sum(cost[m] for m in chunk) >= 100 for chunk in out[:-1])
    assert chunks((), cost.__getitem__, parts=4) == []
    assert chunks(("zero",), cost.__getitem__, parts=4) == [("zero",)]


def test_the_reduction_operators_are_exact_on_known_values() -> None:
    a = EntityTally(days=2, episodes=3, creator=1, create_block=0, daily=[5, -2],
                    closed_non_neutral=2, mints={"M1"}, active_dates={date(2026, 1, 1)},
                    largest=-4, incomplete=1, contaminated=0, sold_atoms=70, unmatched_atoms=7)  # fmt: skip
    a.holds.extend([30.0, 90.0])
    b = EntityTally(days=2, episodes=0, sold_atoms=10, unmatched_atoms=10)  # a sale without lots
    c = EntityTally(days=2, episodes=2, creator=0, create_block=1, daily=[-1, 4],
                    closed_non_neutral=1, mints={"M1", "M2"}, active_dates={date(2026, 1, 2)},
                    largest=-9, incomplete=0, contaminated=2, sold_atoms=5, unmatched_atoms=0)  # fmt: skip
    c.holds.append(12.5)
    a.merge(b)
    assert a.largest == -4  # absence is not 0: an all-negative entity keeps its negative largest
    a.merge(c)
    assert (a.episodes, a.creator, a.create_block, a.daily, a.closed_non_neutral) == (
        5,
        1,
        1,
        [4, 2],
        3,
    )
    assert (a.mints, a.active_dates) == ({"M1", "M2"}, {date(2026, 1, 1), date(2026, 1, 2)})
    assert (a.largest, a.incomplete, a.contaminated, a.sold_atoms, a.unmatched_atoms) == (
        -4,
        1,
        2,
        85,
        17,
    )
    assert sorted(a.holds) == [12.5, 30.0, 90.0]
    none = EntityTally(days=2)
    none.merge(EntityTally(days=2))
    assert none.largest is None
    with pytest.raises(ValueError, match="different lengths"):
        none.merge(EntityTally(days=3))
    copies = CopyTally(total=1, copies=2, incomplete=3, contaminated=4)
    copies.merge(CopyTally(total=-10, copies=20, incomplete=30, contaminated=40))
    assert copies == CopyTally(total=-9, copies=22, incomplete=33, contaminated=44)
    whole = Tallies()
    whole.merge(Tallies(books={"E": EntityTally(days=2, sold_atoms=3, unmatched_atoms=3)},
                        copies={"F": CopyTally(contaminated=1)}, w_pnl={"E": -5}))  # fmt: skip
    whole.merge(Tallies(copies={"F": CopyTally(contaminated=2)}, w_pnl={"E": 8, "G": 1}))
    assert set(whole.books) == {"E"}  # a book with no episode still makes a row; copies make none
    assert whole.books["E"].unmatched_atoms == 3
    assert whole.copies["F"].contaminated == 3
    assert whole.w_pnl == {"E": 3, "G": 1}


def test_an_interrupted_join_leaves_no_worker_even_if_the_manager_looks_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real pool with a task running; the first join of the executor's manager thread is
    interrupted and every later one returns at once — the state CPython 3.12 can leave when
    Ctrl+C lands inside the join's lock (Astra, round 2: a child stayed alive)."""
    pool = ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn"))
    pool.submit(time.sleep, 30.0)
    manager = getattr(pool, "_executor_manager_thread")  # noqa: B009 — the thread to break
    joins: list[float | None] = []

    def broken_join(timeout: float | None = None) -> None:
        joins.append(timeout)
        if len(joins) == 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(manager, "join", broken_join)
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        close_pool(pool)
    assert multiprocessing.active_children() == []
    assert time.monotonic() - started < 20  # the 30 s task was stopped, not waited for


def test_chunks_also_cap_the_mints_per_chunk() -> None:
    zeros = tuple(f"z{i}" for i in range(1000))
    out = chunks(zeros, lambda _m: 0, parts=4, max_mints=256)
    assert [len(c) for c in out] == [256, 256, 256, 232]
    assert [m for c in out for m in c] == list(zeros)


def test_an_interrupt_inside_terminate_still_stops_every_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code review, step 3: a second Ctrl+C inside ``abort_pool``'s terminate loop escaped with
    both workers alive (real 2-worker pool) and skipped the executor's shutdown."""
    pool = ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("spawn"))
    for _ in range(2):
        pool.submit(time.sleep, 30.0)
    procs = getattr(pool, "_processes")  # noqa: B009 — the workers to break
    deadline = time.monotonic() + 30
    while len(procs) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(procs) == 2
    first = next(iter(procs.values()))
    real, calls = first.terminate, list[int]()

    def interrupted() -> None:
        if threading.current_thread() is not threading.main_thread():
            return real()  # the executor's manager thread, once it sees the broken pool
        calls.append(1)
        if len(calls) == 1:
            raise KeyboardInterrupt  # the second Ctrl+C, before this worker was stopped
        real()

    monkeypatch.setattr(first, "terminate", interrupted)
    started = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        abort_pool(pool)
    assert multiprocessing.active_children() == []
    assert len(calls) == 1  # not retried: the survivor is killed after the grace
    assert time.monotonic() - started < 20


def test_an_executor_without_worker_processes_is_refused_loudly() -> None:
    pool = ThreadPoolExecutor(1)
    with pytest.raises(TypeError, match="_processes"):
        abort_pool(pool)


def _two_sleeping_workers() -> tuple[ProcessPoolExecutor, list[Any]]:
    pool = ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("spawn"))
    for _ in range(2):
        pool.submit(time.sleep, 30.0)
    procs = getattr(pool, "_processes")  # noqa: B009 — the workers to break
    deadline = time.monotonic() + 30
    while len(procs) < 2 and time.monotonic() < deadline:
        time.sleep(0.05)
    assert len(procs) == 2
    return pool, list(procs.values())


def test_a_real_ctrl_c_during_cleanup_is_held_until_every_worker_is_gone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real SIGINT raised while the first worker is being stopped: the cleanup is not cut
    (the worker is terminated once, not retried after an exception) and the interrupt comes out
    only at the end (Astra, after the code review: an interrupt outside the per-call try left two
    workers alive)."""
    pool, workers = _two_sleeping_workers()
    first, calls = workers[0], list[int]()
    real = first.terminate

    def ctrl_c_then_terminate() -> None:
        if threading.current_thread() is not threading.main_thread():
            return real()  # the executor's manager thread, once it sees the broken pool
        calls.append(1)
        signal.raise_signal(signal.SIGINT)
        real()

    monkeypatch.setattr(first, "terminate", ctrl_c_then_terminate)
    with pytest.raises(KeyboardInterrupt):
        abort_pool(pool)
    assert multiprocessing.active_children() == []
    assert calls == [1]


def test_a_worker_that_survives_terminate_is_killed_not_left_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Terminate that never takes effect (Astra: three failed attempts plus a timed-out join left a
    worker alive after 30 s): the survivor is killed after a short grace."""
    pool, workers = _two_sleeping_workers()
    monkeypatch.setattr(workers[0], "terminate", lambda: None)
    started = time.monotonic()
    abort_pool(pool)
    assert multiprocessing.active_children() == []
    assert time.monotonic() - started < 20
