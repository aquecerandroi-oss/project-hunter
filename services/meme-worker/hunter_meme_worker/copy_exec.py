"""The copy lane's executor (H-037): everything that happens **after** the hot path decided. It
drains the bounded queue (``copy_lane.py`` fills it with ``put_nowait`` and never waits), prices
each job at the market state at ``decided_at`` + the declared latency (``copy_reads.py``), and
persists with the Lab's own repository functions (``copy_repo.py``).

Jobs of one copy never overlap: a per-key lock is taken first thing in every task, tasks are created
in queue order and asyncio locks wake FIFO, so an exit always runs after the entry it closes (and prices
a state **after** it), a confirmation after the row it annotates, and an invalidation after both.

A failure to price is a **named refusal**, never a guessed fill: an admitted attempt with no eligible
state is ``unfilled/sem_estado``; a mint already on the pool is ``unfilled/fora_de_praca`` (the paper
machinery has no pool *buy* quote — design §3.3 "P"); an exit with no eligible state or pool trade
closes ``indeterminate``. A failure to write (the database down) is logged and counted
(``persist_dropped``); the book lets go of an entry that has no row, and takes a lost exit back to
``open`` so the time cap retries it.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.copy_bets import (
    censored_exit,
    close_on_curve,
    close_on_pool_trade,
)
from hunter_meme_worker.copy_events import (
    MIGROU_FORA_DE_PRACA,
    NO_EXIT_STATE,
    NO_POOL_TRADE,
    CensorEntry,
    CloseIntent,
    ConfirmIntent,
    InvalidateIntent,
    OpenIntent,
    RecordGap,
    RejectEntry,
    ms_iso,
)
from hunter_meme_worker.copy_exec_entry import EntryJobs
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_repo import (
    close_copy_bet,
    set_copy_fact,
)
from hunter_meme_worker.lab_models import MARK_CURVE, MARK_POOL_TAPE

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import Job
    from hunter_meme_worker.copy_reads import CopyReader
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats
    from hunter_meme_worker.lab_models import BetExit, BetState

__all__ = ["CopyExecutor"]

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
CLOSED_MEMORY = 5000
MAX_RETRIES = 5
MAX_INFLIGHT = 32
MAX_INFLIGHT_SECONDARY = 8
"""Jobs being priced or written at once. The executor takes no new job while it is at the cap, so the
queue fills and the hot path's ``put_nowait`` is refused (counted, deferred) instead of an unbounded
set of tasks piling up behind a slow RPC or database."""


class CopyExecutor(EntryJobs):
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
    ) -> None:
        self.spec = spec
        self.live: dict[str, Live] = {}
        self._sessions = session_factory
        self._reader = reader
        self._book = book
        self._stats = stats
        self._clock = clock
        self._defer = defer
        self._tries: dict[tuple[str, str, str], int] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, int] = {}
        self._gate = asyncio.Semaphore(MAX_INFLIGHT if spec.is_primary else MAX_INFLIGHT_SECONDARY)
        self._closed: OrderedDict[str, str] = OrderedDict()
        self._tasks: set[asyncio.Task[None]] = set()
        self._closing = False

    # ------------------------------------------------------------------ drain
    async def run(self, queue: asyncio.Queue[Job]) -> None:
        while True:
            await self._gate.acquire()
            job = await queue.get()
            if self._closing:  # shut down: take nothing new
                return
            key = getattr(job, "key", None)
            if key:
                self._locks.setdefault(key, asyncio.Lock())
                self._inflight[key] = self._inflight.get(key, 0) + 1
            task = asyncio.create_task(self._guarded(job), name="meme-copy-job")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    @property
    def in_flight(self) -> int:
        return len(self._tasks)

    @property
    def idle(self) -> bool:
        """No job in flight (the queue is the lane's to check)."""
        return not self._tasks

    async def shutdown(self) -> None:
        """Tie every job in flight to the lane's life: cancel them and wait, so an old lane can never
        write a bet after a new one has recovered the book."""
        self._closing = True
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

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
        except asyncio.CancelledError:
            raise
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

    def _failed(self, job: Job) -> None:
        """Keep the obligation: the original intent goes back to the outbox (a bounded number of
        times) so a database blip cannot turn a leader's exit into someone else's time cap. An entry
        that never got its row is given up — and the funnel is then declared unrecoverable."""
        if isinstance(job, OpenIntent):
            self._stats.persist_dropped += 1
            self._book.mark_closed(job.key)  # no row exists: do not hold the slot forever
            self._book.funnel_unavailable = True
            return
        ident = getattr(job, "key", None) or getattr(job, "mint", "") or ""
        tag = (type(job).__name__, str(ident), str(getattr(job, "decided_at", "")))
        tries = self._tries.get(tag, 0) + 1
        self._tries[tag] = tries
        if tries <= MAX_RETRIES:
            self._defer(job)
            return
        self._stats.persist_dropped += 1
        if isinstance(job, CloseIntent):
            self._book.rollback(job)  # out of retries: the time cap decides
        elif isinstance(job, RejectEntry | CensorEntry):
            self._book.funnel_unavailable = True  # a first observation was lost for good

    async def _handle(self, job: Job) -> None:
        if isinstance(job, OpenIntent):
            await self._open(job)
        elif isinstance(job, CloseIntent):
            await self._close(job)
        elif isinstance(job, CensorEntry):
            await self._censor(job.mint, job.leader, job.decided_at, job.reason, key=None)
        elif isinstance(job, RejectEntry):
            await self._reject(job)
        elif isinstance(job, ConfirmIntent):
            await self._confirm(job)
        elif isinstance(job, RecordGap):
            await self._record_gap(job)
        else:
            await self._invalidate(job)

    # ------------------------------------------------------------------ exit
    async def _close(self, job: CloseIntent) -> None:
        live = self.live.get(job.key)
        if live is None:  # the entry never became a bet (refused): nothing to sell
            self._book.mark_closed(job.key)
            return
        censor = job.censor
        mark_source: str | None = None
        closed: BetExit | None = None
        if censor is None:
            closed, mark_source = await self._priced_exit(live, job)
            if closed is None:
                censor = mark_source  # the reason the price could not be read
        if closed is None:
            assert censor is not None
            closed = censored_exit(live.state, job, censor=censor, now=self._clock())
            mark_source = None
        else:
            self._stats.record_priced(
                round((closed.exit_at - job.decided_at).total_seconds() * 1000)
            )
        pos = self._book.position(job.key)
        closed.exit["copy"]["contaminated"] = job.contaminated or (pos.gap_reason if pos else None)
        started = self._clock()
        stamp = ms_iso(started)
        closed.exit["copy"]["ts"]["persisted_at"] = stamp
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            landed = await close_copy_bet(
                session, live.bet_id, closed, mark_source=mark_source, stamp=stamp
            )
        self._stats.record_persisted(round((self._clock() - started).total_seconds() * 1000))
        if not landed:  # another writer (the Lab, an operator) closed this row first
            self._stats.closed_elsewhere += 1
            logger.warning("meme_copy_closed_by_another_writer", bet_id=live.bet_id, key=job.key)
            del self.live[job.key]
            self._book.mark_closed(job.key)
            return
        del self.live[job.key]
        self._closed[job.key] = live.bet_id
        while len(self._closed) > CLOSED_MEMORY:
            self._closed.popitem(last=False)
        self._book.mark_closed(job.key)
        if censor is None:
            self._stats.record_exit(live.leader)
        else:
            self._stats.record_censored(live.leader, censor)

    async def _priced_exit(self, live: Live, job: CloseIntent) -> tuple[BetExit | None, str | None]:
        """``(exit, mark_source)`` priced at the pricing instant, or ``(None, censor_reason)``."""
        state = live.state
        floor = live.last_slot
        if job.leader is not None:
            floor = max(floor, job.leader.slot)  # the sale prices a slot after the leader's event
        # an exit decided before the fill still waits the latency AFTER the entry: max(intent, entry_at)
        landed = state.entry_at + timedelta(milliseconds=self.spec.execution_latency_ms)
        not_before = max(job.target_at, landed)
        read = await self._reader.curve_at(
            state.mint,
            not_before=not_before,
            window_s=self.spec.exit_window_s,
            min_slot=floor + 1,
            after=state.entry_at,
        )
        if read is None and self._reader.last_refused.get(state.mint) == "curve_emptied":
            return await self._migrated(state, job, not_before)
        if read is None:
            return None, NO_EXIT_STATE
        snapshot = read.snapshot
        if not (snapshot.complete or snapshot.reserves.complete):
            return close_on_curve(state, snapshot, job), MARK_CURVE
        return await self._migrated(state, job, not_before)

    async def _migrated(
        self, state: BetState, job: CloseIntent, not_before: datetime
    ) -> tuple[BetExit | None, str | None]:
        """The curve is gone (``complete`` or emptied): out by name unless the pool is a venue."""
        if "pumpswap" not in self.spec.venues:  # the pool is not a venue of this cohort
            return None, MIGROU_FORA_DE_PRACA
        found = await self._reader.pool_sale_trades(
            state.mint,
            not_before=not_before,
            after=state.entry_at,
            window_s=self.spec.exit_window_s,
        )
        if found is None:
            return None, NO_POOL_TRADE
        trade, known = found
        return close_on_pool_trade(state, trade, known, job), MARK_POOL_TAPE

    # ------------------------------------------------------------------ late facts
    async def _confirm(self, job: ConfirmIntent) -> None:
        bet_id = self._bet_of(job.key)
        self._stats.record_confirmation(job.delay_ms)
        if bet_id is None:
            return
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await set_copy_fact(
                session, bet_id, where=job.kind, name="confirmation_delay_ms", value=job.delay_ms
            )

    async def _invalidate(self, job: InvalidateIntent) -> None:
        """The event behind a copy was not confirmed: the reason is written on the copy and the copy
        **stays** in the primary with its economic result — an open one was already sent to market
        (``invalidated``) by the book, ahead of this job in the same lock."""
        self._stats.record_invalidated()
        bet_id = self._bet_of(job.key)
        if bet_id is None:
            return
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await set_copy_fact(
                session, bet_id, where="entry", name="invalid_reason", value=job.reason
            )
            await set_copy_fact(
                session, bet_id, where="entry", name="invalid_event", value=job.kind
            )

    def _bet_of(self, key: str) -> str | None:
        live = self.live.get(key)
        return live.bet_id if live is not None else self._closed.get(key)
