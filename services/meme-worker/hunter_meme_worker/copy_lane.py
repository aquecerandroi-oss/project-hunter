"""The copy lane (H-037, decision 2026-10-09): follow a frozen set of wallets and, in paper only, buy
what they buy and sell what they sell — priced with our own latency and the Lab's own costs.

**Two halves, joined by a bounded queue that never blocks.**

* the **hot path** — :meth:`CopyLane.on_item`, a plain synchronous function: stamp the instant,
  decide against the in-memory :class:`~hunter_meme_worker.copy_book.CopyBook`, ``put_nowait`` the
  job, record the latencies. No ``await``, no database, no HTTP, no lock and no logging. When the
  queue is full the job is **deferred to an in-memory outbox** (never dropped, never waited for) and
  the sweep re-submits it; only an entry that cannot be queued is given back (``sobrecarga``).
* the **executor** (``copy_exec.py``) — prices each job at the market state at
  ``decided_at`` + the declared execution latency and persists it, off the hot path, with a cap on
  the jobs in flight.

Around them: a 1 s sweep (time caps, confirmation timeouts, the outbox), the mark pass (live marks and
the safety stop) and the heartbeat. The lane never touches the executor service, a wallet or an order;
every row it writes is ``mode = 'paper'`` of a ``research_only`` rule set. The supervisor that keeps it
inert until a ``copy_v0`` set is active lives in ``copy_forever.py``.
"""

from __future__ import annotations

import asyncio
from collections import deque
from time import perf_counter_ns
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderConfirmation, LeaderGap
from hunter_meme_worker.copy_book import CopyBook
from hunter_meme_worker.copy_events import (
    SOBRECARGA,
    CensorEntry,
    CloseIntent,
    OpenIntent,
    RecordGap,
    RejectEntry,
)
from hunter_meme_worker.copy_exec import CopyExecutor
from hunter_meme_worker.copy_marks import mark_pass
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_reads import CopyReader
from hunter_meme_worker.copy_repo import load_funnel, load_open_copies
from hunter_meme_worker.copy_repo_gaps import ensure_t0
from hunter_meme_worker.copy_stats import CopyStats, heartbeat_fields

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_exchanges.pumpfun.leader_events import LeaderItem
    from hunter_meme_worker.context import ChainSource
    from hunter_meme_worker.copy_events import Job
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["CopyLane"]

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
SWEEP_S = 1.0
HEARTBEAT_S = 5.0
OUTBOX_MAX = 10_000


class CopyLane:
    def __init__(
        self,
        *,
        spec: CopySpec,
        session_factory: async_sessionmaker[AsyncSession],
        chain: ChainSource,
        heartbeat: Callable[[dict[str, str]], Awaitable[None]] | None = None,
        clock: Callable[[], datetime] = utcnow,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        t0: datetime | None = None,
    ) -> None:
        self.spec = spec
        self.stats = CopyStats(sorted(spec.wallets))
        self._t0_given = t0
        self.book = CopyBook(spec, t0=t0 or clock())
        self.queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=spec.queue_max)
        self.outbox: deque[Job] = deque()
        self._sessions = session_factory
        self._chain = chain
        self._heartbeat = heartbeat
        self._clock = clock
        self._sleep = sleep
        self.executor = CopyExecutor(
            spec=spec,
            session_factory=session_factory,
            reader=CopyReader(
                chain=chain, session_factory=session_factory, clock=clock, sleep=sleep
            ),
            book=self.book,
            stats=self.stats,
            clock=clock,
            defer=self._defer,
        )

    # ================================================================ hot path
    def on_item(self, item: LeaderItem) -> None:
        """Decide one leader event or gap **in memory**. Synchronous by construction: nothing here
        can await, so nothing here can wait on IO (and nothing logs: a blocked stderr must not
        hold the decision — counters are published by the heartbeat instead)."""
        started = perf_counter_ns()
        now = self._clock()
        if isinstance(item, LeaderConfirmation):
            for job in self.book.on_confirmation(item, now).jobs:
                self.submit(job)
            return
        if isinstance(item, LeaderGap):
            self.stats.gaps_seen += 1
            self.book.on_gap(item, now)
            if item.end is not None:
                self.submit(RecordGap(item))
            return
        decision = self.book.on_event(item, now)
        if not decision.wallet_known:
            if decision.skipped is not None:
                self.stats.record_skip(decision.skipped)
            return
        if decision.skipped is not None:
            self.stats.record_skip(decision.skipped)
        for job in decision.jobs:
            if isinstance(job, RejectEntry):
                self.stats.record_rejected(job.reason)
            self.submit(job)
        block_to_decided = (
            None
            if item.block_time is None
            else round((now - item.block_time).total_seconds() * 1_000_000)
        )
        self.stats.record_decision(
            item.wallet,
            observed_to_decided_us=round((now - item.first_seen_at).total_seconds() * 1_000_000),
            fields_to_decided_us=round((now - item.fields_complete_at).total_seconds() * 1_000_000),
            block_to_decided_us=block_to_decided,
            decide_us=(perf_counter_ns() - started) // 1000,
            at=item.first_seen_at,
        )

    def submit(self, job: Job) -> bool:
        """Hand a decided job to the executor without ever waiting for room. A refused job is an
        **obligation kept**, not a loss: it waits in the outbox for the next sweep. Only an entry is
        given back (the book rolls it back and a ``sobrecarga`` row is owed instead)."""
        self._flush_outbox()  # older obligations first: a new job never overtakes a deferred one
        if self.outbox:
            self.stats.queue_full += 1
            if isinstance(job, OpenIntent):
                self.book.rollback(job)
                job = CensorEntry(job.mint, job.leader, SOBRECARGA, job.decided_at)
            self._defer(job)
            return False
        try:
            self.queue.put_nowait(job)
        except asyncio.QueueFull:
            self.stats.queue_full += 1
            if isinstance(job, OpenIntent):
                self.book.rollback(job)
                job = CensorEntry(job.mint, job.leader, SOBRECARGA, job.decided_at)
            self._defer(job)
            return False
        return True

    def _flush_outbox(self) -> None:
        while self.outbox and not self.queue.full():
            self.queue.put_nowait(self.outbox.popleft())

    def _defer(self, job: Job) -> None:
        if len(self.outbox) >= OUTBOX_MAX:
            self.stats.outbox_dropped += 1  # declared: the outbox itself overflowed
            if isinstance(job, CloseIntent):
                self.book.rollback(job)  # back to open: the sweep's time cap still sees it
            return
        self.outbox.append(job)

    # ================================================================ off the hot path
    async def start(self) -> None:
        """Recover, then (and only then) accept events: the fleet awaits this for every lane before
        it opens the source, so no event meets an empty memory."""
        await self.recover()

    async def recover(self) -> None:
        """Rebuild the book from the database before the source opens: T0, the funnel, the copies
        still open and the confirmations still owed."""
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            if self._t0_given is None:
                self.book.set_t0(await ensure_t0(session, self.spec, self._clock()))
            funnel = await load_funnel(session, self.spec)
            opens = await load_open_copies(session, self.spec)
        for leader, mint in funnel.pairs:
            self.book.restore_pair(leader, mint)
        for stratum, mint in funnel.consumed:
            self.book.restore_consumed(stratum, mint)
        for leader, day in funnel.attempts:
            self.book.restore_attempt(leader, day)
        for copy in opens:
            key = str(uuid7())
            self.book.recover_open(
                key=key,
                mint=copy.state.mint,
                leader=copy.leader,
                stratum=copy.stratum,
                bet_id=copy.state.id,
                entry_at=copy.state.entry_at,
                peak_atoms=copy.peak_atoms,
            )
            if copy.unconfirmed_signature is not None:
                self.book.restore_pending(
                    key,
                    copy.unconfirmed_signature,
                    copy.leader,
                    copy.state.mint,
                    first_observed_at=copy.leader_observed_at,
                    position_after=copy.peak_atoms,
                    token_delta=copy.leader_token_delta,
                    slot=copy.leader_slot,
                )
            self.executor.live[key] = Live(
                bet_id=copy.state.id,
                state=copy.state,
                leader=copy.leader,
                last_slot=copy.priced_slot,
            )

    async def sweep_once(self) -> None:
        now = self._clock()
        self._flush_outbox()
        for job in self.book.due_time_caps(now):
            self.submit(job)
        for invalid in self.book.expired_confirmations(now):
            self.submit(invalid)

    async def mark_once(self) -> int:
        return await mark_pass(
            spec=self.spec,
            chain=self._chain,
            session_factory=self._sessions,
            book=self.book,
            live=self.executor.live,
            submit=self._submit_close,
            now=self._clock,
        )

    def _submit_close(self, job: CloseIntent) -> None:
        self.submit(job)

    def fields(self) -> dict[str, str]:
        base = heartbeat_fields(
            self.stats,
            now=self._clock(),
            open_count=self.book.open_count,
            queue_depth=self.queue.qsize(),
            outbox_depth=len(self.outbox),
        )
        fields = {
            **base,
            "copy_state": "running",
            "copy_rule_set": self.spec.label,
            "copy_t0": self.book.t0.isoformat(timespec="milliseconds"),
            "copy_entries_end": self.book.horizon_end.isoformat(timespec="milliseconds"),
        }
        if self.spec.is_primary:
            return fields
        tag = f"copy_{self.spec.name}_"  # a secondary set never overwrites the primary's fields
        return {key.replace("copy_", tag, 1): value for key, value in fields.items()}

    async def heartbeat_once(self) -> None:
        if self._heartbeat is not None:
            await self._heartbeat(self.fields())

    async def _guard(self, name: str, step: Callable[[], Awaitable[object]], every: float) -> None:
        while True:
            await self._sleep(every)
            try:
                await step()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # one failed pass never stops the lane
                logger.warning("meme_copy_step_failed", step=name, error=str(exc)[:200])

    async def run(self) -> None:
        """The lane's loops (after :meth:`start`)."""
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(self.executor.run(self.queue), name="meme-copy-executor")
                group.create_task(
                    self._guard("sweep", self.sweep_once, SWEEP_S), name="meme-copy-sweep"
                )
                group.create_task(
                    self._guard("mark", self.mark_once, float(self.spec.mark_every_s)),
                    name="meme-copy-mark",
                )
                group.create_task(
                    self._guard("heartbeat", self.heartbeat_once, HEARTBEAT_S),
                    name="meme-copy-hb",
                )
        finally:  # no job outlives the lane: an old lane must never write after a new one recovers
            await self.executor.shutdown()
