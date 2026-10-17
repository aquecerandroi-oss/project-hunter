"""The copy lane's executor (H-037): everything that happens **after** the hot path decided. It
drains the bounded queue (``copy_lane.py`` fills it with ``put_nowait`` and never waits), prices
each job at the market state at ``decided_at`` + the declared latency (``copy_reads.py``), and
persists with the Lab's own repository functions (``copy_repo*.py``).

Jobs of one copy never overlap: a per-key lock is taken first thing in every task, tasks are created
in queue order and asyncio locks wake FIFO, so an exit always runs after the entry it closes (and prices
a state **after** it).

**Every job is an obligation with its own budget** (R2 fix B6). A failure is retried with a growing delay
(``RETRY_BASE_S``) up to ``MAX_RETRIES`` times, keyed by the job's own ``oid`` — six distinct gaps that
each fail once are six budgets, not one; what was already priced is held, so a database failure never
changes the photograph of a sale. A job that is not ready yet (a confirmation whose row has not landed) is
*parked*, not failed. When the budget is exhausted the failure becomes durable state: the funnel is
declared unavailable (``funil_indisponivel``, a global hole that is recorded and later recomposed), the
copy's lost exit is flagged, never silently forgotten.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from hunter_core.logging import get_logger
from hunter_meme_worker.copy_events import (
    CensorEntry,
    CloseIntent,
    ConfirmIntent,
    OpenIntent,
    RecomposeDone,
    RecordGap,
    RejectEntry,
    UnverifiedIntent,
)
from hunter_meme_worker.copy_exec_entry import EntryJobs
from hunter_meme_worker.copy_exec_exit import ExitJobs
from hunter_meme_worker.copy_exec_facts import FactJobs, NotYet
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_retry import Held, PricedEntry, PricedExit, Retries

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine
    from datetime import datetime
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import Job
    from hunter_meme_worker.copy_history import MintTrace
    from hunter_meme_worker.copy_reads import CopyReader
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats

__all__ = ["CopyExecutor"]

logger = get_logger(__name__)

CLOSED_MEMORY = 5000
MAX_RETRIES = 5
RETRY_BASE_S = 1.0
MAX_WAITS = 120
WAIT_S = 1.0
MAX_INFLIGHT = 32
MAX_INFLIGHT_SECONDARY = 8
"""Jobs being priced or written at once. The executor takes no new job while it is at the cap, so the
queue fills and the hot path's ``put_nowait`` is refused (counted, deferred) instead of an unbounded
set of tasks piling up behind a slow RPC or database."""


class CopyExecutor(EntryJobs, ExitJobs, FactJobs):
    def __init__(
        self,
        *,
        spec: CopySpec,
        session_factory: async_sessionmaker[AsyncSession],
        reader: CopyReader,
        book: CopyBook,
        stats: CopyStats,
        clock: Callable[[], datetime],
        defer: Callable[[Job], None],
        funnel_failed: Callable[[datetime | None], None] = lambda since=None: None,
        funnel_ok: Callable[[], None] = lambda: None,
        settled: Callable[[str], None] = lambda oid: None,
        retrace: Callable[[str, str, datetime], Awaitable[MintTrace | None]] | None = None,
    ) -> None:
        self.spec = spec
        self.live: dict[str, Live] = {}
        self._sessions = session_factory
        self._reader = reader
        self._book = book
        self._stats = stats
        self._clock = clock
        self._defer = defer
        self._funnel_failed = funnel_failed
        self._funnel_ok = funnel_ok
        self._settled = settled
        self._retrace = retrace
        self._cancelled: list[Job] = []
        self._retries = Retries()
        self._waits = Retries()
        self._held_exit: Held[PricedExit] = Held()
        self._held_entry: Held[PricedEntry] = Held()
        self._parked: dict[str, tuple[asyncio.TimerHandle, Job]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, int] = {}
        self._gate = asyncio.Semaphore(MAX_INFLIGHT if spec.is_primary else MAX_INFLIGHT_SECONDARY)
        self._closed: dict[str, str] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._owned: dict[asyncio.Task[None], Job] = {}
        self._side: set[asyncio.Task[None]] = set()
        self._closing = False

    # ------------------------------------------------------------------ drain
    async def run(self, queue: asyncio.Queue[Job]) -> None:
        while True:
            await self._gate.acquire()
            job = await queue.get()
            if self._closing:  # shut down: take nothing new - and give back what was just taken
                queue.put_nowait(job)
                return
            self._admit(job)
            task = asyncio.create_task(self._guarded(job), name="meme-copy-job")
            self._tasks.add(task)
            # remembered before it starts: a cancel-before-start loses nothing
            self._owned[task] = job
            task.add_done_callback(self._forget)

    def _forget(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        self._owned.pop(task, None)

    def _admit(self, job: Job) -> None:
        key = getattr(job, "key", None)
        if key:
            self._locks.setdefault(key, asyncio.Lock())
            self._inflight[key] = self._inflight.get(key, 0) + 1

    def is_parked(self, oid: str) -> bool:
        return oid in self._parked

    @property
    def in_flight(self) -> int:
        return len(self._tasks)

    @property
    def idle(self) -> bool:
        """No job in flight, none parked waiting for its row, no sensitivity read running."""
        return not self._tasks and not self._side and not self._parked

    def spawn_side(self, coro: Coroutine[Any, Any, None]) -> None:
        """A secondary read (the p90 sensitivity) — never on the gate, never able to fail a job."""
        task = asyncio.create_task(coro, name="meme-copy-side")
        self._side.add(task)
        task.add_done_callback(self._side.discard)

    async def shutdown(self) -> list[Job]:
        """Tie every job in flight to the lane's life: cancel them and wait, so an old lane can never
        write a bet after a new one has recovered the book. Returns the obligations that were parked."""
        self._closing = True
        tasks = [*self._tasks, *self._side]
        owned = dict(self._owned)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        parked: list[Job] = list(self._cancelled)  # jobs the cancellation interrupted come back too
        self._cancelled.clear()
        seen = {job.oid for job in parked}
        for (
            task,
            job,
        ) in owned.items():  # cancelled before its first step: its own handler never ran
            if task.cancelled() and job.oid not in seen:
                parked.append(job)
        for oid in list(self._parked):
            handle, job = self._parked.pop(oid)
            handle.cancel()
            parked.append(job)
        return parked

    async def run_now(self, job: Job) -> None:
        """Process one job right here, outside the gate and the retry budget (the lane is stopping)."""
        await self._handle(job)
        self._landed(job)

    async def drain(self) -> None:
        """Wait for every job in flight (tests, and a clean shutdown)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _guarded(self, job: Job) -> None:
        key = getattr(job, "key", None)
        lock = self._locks[key] if key else None
        try:
            if lock is None:
                await self._handle(job)
            else:
                async with lock:
                    await self._handle(job)
            self._landed(job)
        except asyncio.CancelledError:
            if (
                self._closing
            ):  # the lane is stopping: the obligation goes back to it, not to the floor
                self._cancelled.append(job)
            raise
        except NotYet:
            self._wait(job)
        except (
            Exception
        ) as exc:  # a failed job is an obligation: retried, then declared, never silent
            self._failed(job)
            logger.warning(
                "meme_copy_job_failed",
                job=type(job).__name__,
                key=key,
                error_type=type(exc).__name__,
                error=str(exc)[:300],
            )
        finally:
            self._gate.release()
            if key:
                self._inflight[key] -= 1
                if self._inflight[key] == 0 and key not in self.live:
                    del self._inflight[key]
                    self._locks.pop(key, None)

    def _landed(self, job: Job) -> None:
        self._settled(job.oid)
        self._book.landed(job)
        self._retries.clear(job.oid)
        self._waits.clear(job.oid)
        self._held_exit.drop(job.oid)
        self._held_entry.drop(job.oid)
        if isinstance(
            job, OpenIntent | CloseIntent | RejectEntry | CensorEntry | RecordGap | RecomposeDone
        ):
            self._funnel_ok()  # the database took a fact: if the funnel was declared down, it is back

    def _park(self, job: Job, delay: float) -> None:
        if self._closing:
            self._defer(job)
            return
        handle = asyncio.get_running_loop().call_later(delay, self._unpark, job.oid)
        self._parked[job.oid] = (handle, job)

    def _unpark(self, oid: str) -> None:
        pair = self._parked.pop(oid, None)
        if pair is not None:
            self._defer(pair[1])  # the lane's outbox: older obligations first, in order

    def _wait(self, job: Job) -> None:
        """Not ready yet (its row has not landed): neither a success nor a failure."""
        if self._waits.bump(job.oid) > MAX_WAITS:
            self._waits.clear(job.oid)
            # the row it waited for never came: a lost obligation, not a lost note
            self._give_up(job)
            return
        self._park(job, WAIT_S)

    def _failed(self, job: Job) -> None:
        """Keep the obligation: the original intent comes back after a growing delay, a bounded number of
        times. Out of budget, the failure becomes durable state (see the module docstring)."""
        tries = self._retries.bump(job.oid)
        if tries <= MAX_RETRIES:
            self._park(job, RETRY_BASE_S * tries)
            return
        self._retries.clear(job.oid)
        self._stats.persist_dropped += 1
        self._give_up(job)

    def _give_up(self, job: Job) -> None:
        """Out of budget: the failure becomes durable state (a funnel hole from the lost fact). A hole
        record that could not be written stays *unsettled*: the liveness marker does not pass it, so a
        restart declares the downtime from before it instead of trusting a record that never landed."""
        if not isinstance(job, RecordGap):
            self._settled(job.oid)
        self._held_exit.drop(job.oid)
        self._held_entry.drop(job.oid)
        since = getattr(
            job, "decided_at", None
        )  # the hole must reach back to the fact that was lost
        if isinstance(job, OpenIntent):
            self._book.mark_closed(job.key)  # no row exists: do not hold the slot forever
            self._funnel_failed(since)
        elif isinstance(job, CloseIntent):
            self._book.rollback(job)  # the row is still open: the time cap decides, flagged
            self._funnel_failed(since)
        elif isinstance(job, RejectEntry | CensorEntry):
            self._funnel_failed(since)  # a first observation was lost for good
        elif isinstance(job, RecomposeDone):
            self._funnel_failed(
                job.start
            )  # its pairs / marker did not land: the window is owed again
        elif isinstance(job, RecordGap):
            self._stats.gaps_lost += 1
            if job.gap.reason != "funil_indisponivel":
                self._funnel_failed(job.gap.start)
        else:  # ConfirmIntent | InvalidateIntent | UnverifiedIntent: the annotation, not the fact
            self._stats.annotation_lost += 1

    async def _handle(self, job: Job) -> None:
        if isinstance(job, OpenIntent):
            await self._open(job)
        elif isinstance(job, CloseIntent):
            await self._close(job)
        elif isinstance(job, CensorEntry):
            await self._censor(job)
        elif isinstance(job, RejectEntry):
            await self._reject(job)
        elif isinstance(job, ConfirmIntent):
            await self._confirm(job)
        elif isinstance(job, RecordGap):
            await self._record_gap(job)
        elif isinstance(job, RecomposeDone):
            await self._recomposed(job)
        elif isinstance(job, UnverifiedIntent):
            await self._unverified(job)
        else:
            await self._invalidate(job)
