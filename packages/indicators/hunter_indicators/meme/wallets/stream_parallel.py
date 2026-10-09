"""The night's pass 3 in worker processes (CPU plan step 3): whole mints, exact reduction.

Passes 1–2 stay on the coordinator (:func:`.stream.plan_night`: survey, entities, the bets under
the global per-entity daily cap, fee seeds) — they read every mint and decide what no single mint
can. Each mint's replay is then a pure function of the plan and that mint
(:func:`.stream.replay_one`), so:

- workers are **processes** (``spawn``), never threads: the pricing memo is per process and the
  lazy :class:`.pricing.MintTape` indexes are not thread-safe (Astra, step 2);
- each worker gets the night once (initializer) and then only mint **names**, largest estimated
  cost first (:meth:`.stream.NightPlan.schedule`), each with that mint's bets and fee seeds; it
  loads the window itself through ``fetch(name)`` (the storage; picklable), so no window crosses
  the coordinator. Consecutive small mints of the schedule travel together (:func:`chunks`, about
  1/16 of a worker's share each; a big mint alone) and are reduced in the worker, because a task
  and its returned tallies cost ~0.7–1 ms of pickling per mint, near half on the coordinator;
- at most ``2 × workers`` chunks are in flight (:func:`bounded`); parts come back in completion
  order and are reduced exactly (:meth:`.stream_mint.Tallies.merge`: integer sums, unions, max
  with absence, concatenated holds — the median and the ratios only in the final metrics);
- next carries go to ``emit`` as they arrive (completion order) or, without it, come back in
  source order — the tuple the one-process :func:`.stream.stream_snapshot` returns.

The source must be immutable for the run (:mod:`.carry`): every pass and every ``fetch`` see the
same mint. The name and the event count are re-checked (``fetch_mismatch``) as a sanity check,
not a proof. A failure anywhere (worker, fetch, emit, the check) stops the workers and
re-raises; the pool's processes are gone when this returns or raises (Ctrl+C is held during the
cleanup), or a ``RuntimeError`` names the ones that survived terminate and kill.
"""

from __future__ import annotations

import multiprocessing
import signal
import threading
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, Executor, Future, ProcessPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime
from multiprocessing.process import BaseProcess
from typing import Any

from hunter_indicators.meme.wallets.carry import ContractViolation, MintCarry
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.stream import finish_night, plan_night, replay_one
from hunter_indicators.meme.wallets.stream_mint import Night, Tallies
from hunter_indicators.meme.wallets.stream_source import MintWindow, StreamInputs, StreamResult

__all__ = ["Fetch", "abort_pool", "bounded", "chunks", "close_pool", "stream_snapshot_parallel"]

Fetch = Callable[[str], MintWindow]
"""Loads one mint's window by name — picklable (a spawned worker unpickles it)."""
_Seeds = frozenset[tuple[str, str]]
_Job = tuple[str, frozenset[tuple[str, str, int]], _Seeds, _Seeds]
_CHUNKS_PER_WORKER = 16
_GRACE_S = 5.0  # a terminated worker exits at once; past this it is killed
_JOIN_S = 30.0  # after kill
_MAX_MINTS_PER_CHUNK = 256  # carry-only mints can cost ~0 and must not all pile into one task
_worker: tuple[Night, datetime, Fetch] | None = None


def bounded[R](
    pool: Executor, fn: Callable[..., R], jobs: Iterable[tuple[Any, ...]], *, limit: int
) -> Iterator[R]:
    """``fn(*job)`` on ``pool`` for every job, results in completion order, never more than
    ``limit`` submitted and not yet yielded; what is still pending is cancelled on exit."""
    if limit < 1:
        raise ValueError("limit must be at least 1")
    pending: set[Future[R]] = set()
    try:
        for job in jobs:
            pending.add(pool.submit(fn, *job))
            if len(pending) >= limit:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                while done:  # popped: a consumed result is not kept alive by the set
                    yield done.pop().result()
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            while done:
                yield done.pop().result()
    finally:
        for future in pending:
            future.cancel()


def chunks(
    schedule: Sequence[str],
    cost: Callable[[str], int],
    parts: int,
    max_mints: int = _MAX_MINTS_PER_CHUNK,
) -> list[tuple[str, ...]]:
    """Consecutive runs of ``schedule`` with an estimated cost of at least ``total // parts``
    or ``max_mints`` mints each (the last may be less): a big mint alone, small ones packed, the
    order kept."""
    target = max(1, sum(cost(m) for m in schedule) // max(1, parts))
    out: list[tuple[str, ...]] = []
    run: list[str] = []
    acc = 0
    for mint in schedule:
        run.append(mint)
        acc += cost(mint)
        if acc >= target or len(run) >= max_mints:
            out.append(tuple(run))
            run, acc = [], 0
    if run:
        out.append(tuple(run))
    return out


@dataclass(frozen=True, slots=True)
class _Chunk:
    """A worker's answer for one chunk: its mints' event counts, reduced tallies, next carries."""

    events: dict[str, int]
    tallies: Tallies
    carries: tuple[MintCarry, ...]


def _workers_of(pool: Executor) -> list[BaseProcess]:
    """The pool's worker processes — ``ProcessPoolExecutor._processes`` (private, stable since
    3.8), read BEFORE a shutdown drops it, so that an interrupted shutdown can still stop them.
    An executor without it is refused loudly rather than cleaned up silently (code review)."""
    state: dict[str, Any] = vars(pool)
    if "_processes" not in state:
        raise TypeError(f"{type(pool).__name__} has no _processes: its workers cannot be stopped")
    procs: dict[int, BaseProcess] | None = state["_processes"]
    return list((procs or {}).values())


def _terminate(proc: BaseProcess) -> None:
    if proc.is_alive():
        proc.terminate()


@contextmanager
def _sigint_held() -> Generator[list[int]]:
    """Ctrl+C cannot cut the cleanup short: while inside, SIGINT is recorded instead of raised
    (main thread only — Python delivers it nowhere else). An interrupt between two statements of
    the cleanup left workers alive (Astra, after the code review)."""
    caught: list[int] = []
    if threading.current_thread() is not threading.main_thread():
        yield caught
        return
    previous = signal.signal(signal.SIGINT, lambda signum, _frame: caught.append(signum))
    try:
        yield caught
    finally:
        signal.signal(signal.SIGINT, previous)


def _stop(procs: list[BaseProcess]) -> None:
    """Terminate every worker (a worker writes nothing; its result is being discarded), give each a
    short grace, kill what survived, and refuse loudly if any is still alive. Ctrl+C is held until
    the end, then re-raised; the first other error is re-raised too."""
    first: BaseException | None = None
    with _sigint_held() as caught:
        for proc in procs:
            try:
                _terminate(proc)
            except BaseException as exc:
                first = first or exc
        for proc in procs:
            try:
                proc.join(_GRACE_S)
                if proc.is_alive():  # terminate did not take: kill, then wait for it
                    proc.kill()
                    proc.join(_JOIN_S)
            except BaseException as exc:
                first = first or exc
    alive = [proc.pid for proc in procs if proc.is_alive()]
    if alive:
        raise RuntimeError(f"workers still alive after terminate and kill: {alive}") from first
    if first is not None:
        raise first
    if caught:
        raise KeyboardInterrupt


def abort_pool(pool: Executor) -> None:
    """The night failed: stop the workers now (a hot mint may run for minutes), then let go of the
    executor without waiting on it — the latter even if stopping was interrupted."""
    try:
        _stop(_workers_of(pool))
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def close_pool(pool: Executor) -> None:
    """The night ended: cancel what has not started and join the workers. If that join is
    interrupted (Ctrl+C), the executor's own join cannot be trusted again — CPython 3.12 may mark
    its manager thread stopped while it still runs, and a second shutdown returned with a worker
    alive (Astra, step 3 round 2) — so the workers are stopped and joined here, then the interrupt
    is re-raised."""
    procs = _workers_of(pool)
    try:
        pool.shutdown(wait=True, cancel_futures=True)
    except BaseException:
        try:
            _stop(procs)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        raise


def _start(night: Night, sealed_until: datetime, fetch: Fetch) -> None:
    global _worker  # one night per worker process, set once by the pool's initializer
    _worker = (night, sealed_until, fetch)


def _job(jobs: tuple[_Job, ...]) -> _Chunk:
    assert _worker is not None, "the pool initializer did not run"
    night, sealed_until, fetch = _worker
    events, tallies, carries = dict[str, int](), Tallies(), list[MintCarry]()
    for mint, bets, entity, wallet in jobs:
        window = fetch(mint)
        if window.carry.mint != mint:
            raise ContractViolation("fetch_mismatch", f"asked for {mint}, got {window.carry.mint}")
        one = replace(night, bets=bets, entity_seeds={mint: entity}, wallet_seeds={mint: wallet})
        part = replay_one(one, sealed_until, window)
        events[mint] = part.events
        tallies.merge(part.tallies)
        if part.carry is not None:
            carries.append(part.carry)
    return _Chunk(events, tallies, tuple(carries))


def stream_snapshot_parallel(
    inputs: StreamInputs,
    day: date,
    *,
    fetch: Fetch,
    workers: int,
    policy: FollowPolicy | None = None,
    params: RankingParams | None = None,
    code_version: str = "",
    emit: Callable[[MintCarry], None] | None = None,
) -> StreamResult:
    """:func:`.stream.stream_snapshot`, with pass 3 spread over ``workers`` processes."""
    if workers < 1:
        raise ValueError("workers must be at least 1")
    plan = plan_night(inputs, day, policy=policy, params=params)
    # a MappingProxyType does not pickle; the seeds go with each mint
    portable = replace(
        plan.base, funded_by=dict(plan.base.funded_by), entity_seeds={}, wallet_seeds={}
    )
    none: _Seeds = frozenset()

    def job(m: str) -> _Job:
        return (m, plan.bets.get(m, frozenset()), plan.entity_seeds.get(m, none),
                plan.wallet_seeds.get(m, none))  # fmt: skip

    runs = chunks(plan.schedule(), plan.cost, _CHUNKS_PER_WORKER * workers)
    jobs = ((tuple(job(m) for m in run),) for run in runs)
    tallies, kept = Tallies(), dict[str, MintCarry]()
    if not runs:  # an empty source: nothing to replay, no pool
        return finish_night(plan, tallies, (), code_version)
    pool = ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn"),
                               initializer=_start,
                               initargs=(portable, plan.carry.sealed_until, fetch))  # fmt: skip
    try:
        for part in bounded(pool, _job, jobs, limit=2 * workers):
            for mint, n in part.events.items():
                if n != plan.events[mint]:
                    raise ContractViolation("fetch_mismatch", f"{mint}: {n} events, "
                                            f"{plan.events[mint]} surveyed")  # fmt: skip
            tallies.merge(part.tallies)
            for carry in part.carries:
                if emit is None:
                    kept[carry.mint] = carry
                else:
                    emit(carry)
    except BaseException:  # failure or interrupt: no worker outlives this call
        abort_pool(pool)
        raise
    close_pool(pool)
    carries = tuple(kept[m] for m in plan.order if m in kept)
    return finish_night(plan, tallies, carries, code_version)
