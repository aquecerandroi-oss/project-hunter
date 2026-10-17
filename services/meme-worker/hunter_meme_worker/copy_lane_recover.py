"""Everything the copy lane does around its edges (H-037, R2 fix B2): rebuilding itself from the database
before the source opens, **declaring the lane's own downtime**, recomposing what a hole hid, keeping a
durable liveness marker, and stopping without dropping obligations on the floor. Split from
``copy_lane.py`` for the 350-line budget; :class:`CopyLane` inherits it and owns the state.

Order of a start (the fleet drives it):

1. :meth:`recover` — funnel, open copies, confirmations owed (database only; no clock decisions);
2. the fleet opens the **one** source and lets the stream start;
3. :meth:`source_up` — *T0 is this moment* (first run), or the downtime since the last durable marker is
   declared a ``worker_downtime`` hole (recorded, then recomposed per leader), holes the dead process left
   open are closed at that marker, and entries are armed.

A leader that cannot be recomposed (no history hook, a window past the signature cap, a node failure) has
**no new entry** until it is — fail closed — and a copy whose leader position cannot be re-read keeps its
leader-driven exit censored by name.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import uuid7
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.leader_events import LeaderGap
from hunter_meme_worker.copy_events import (
    FUNIL_INDISPONIVEL,
    LEADER_GAP_EXIT,
    WORKER_DOWNTIME,
    WORKER_RESTART_GAP,
    CensorEntry,
    CloseIntent,
    InvalidateIntent,
    Job,
    OpenIntent,
    RecomposeDone,
    RecordGap,
    RejectEntry,
    UnverifiedIntent,
)
from hunter_meme_worker.copy_history import SIGNATURE_CAP
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_repo import load_open_copies
from hunter_meme_worker.copy_repo_funnel import load_funnel
from hunter_meme_worker.copy_repo_gaps import (
    ensure_t0,
    last_alive,
    owed_gaps,
    record_gap,
    unclosed_gaps,
    write_alive,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_exec import CopyExecutor
    from hunter_meme_worker.copy_history import LeaderHistory
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats

__all__ = ["LaneRecovery"]

logger = get_logger(__name__)
WORKER_ROLE = "hunter_worker"
MARKER_S = 30.0
TRACE_RETRY_FIRST_S = 5
TRACE_RETRY_MAX_S = 120
ONE_US = timedelta(microseconds=1)
STOP_WRITE_TIMEOUT_S = 5.0


class LaneRecovery:
    spec: CopySpec
    book: CopyBook
    stats: CopyStats
    executor: CopyExecutor
    history: LeaderHistory | None
    _sessions: async_sessionmaker[AsyncSession]
    _clock: Callable[[], datetime]
    _t0_given: datetime | None
    _alive_from: datetime | None
    _unlanded: dict[str, datetime]
    _trace_next: dict[str, tuple[int, datetime]]

    def submit(self, job: Job) -> bool:
        raise NotImplementedError

    def drain_pending(self) -> list[Job]:
        raise NotImplementedError

    # ------------------------------------------------------------------ before the source opens
    async def recover(self) -> None:
        """Rebuild the book from the database: the funnel, and the copies still open (their leader-driven
        exit is censored until their position is re-read) with the confirmations still owed."""
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            funnel = await load_funnel(session, self.spec)
            opens = await load_open_copies(session, self.spec)
            owed = await owed_gaps(session, self.spec)
        for hole, done in owed:  # holes closed in an earlier life whose windows were never read
            self.book.owe_window(hole, done)
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

    # ------------------------------------------------------------------ the source is up
    async def source_up(self) -> None:
        """T0 (first run) or the declared downtime (every later run); then entries are armed."""
        now = self._clock()
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            if self._t0_given is not None:
                t0, created = self._t0_given, False
            else:
                t0, created = await ensure_t0(session, self.spec, now)
            last = await last_alive(session, self.spec)
            unclosed = await unclosed_gaps(session, self.spec)
            since = last if last is not None else (None if self._t0_given is not None else t0)
            holes = [] if created or since is None else self._downtime_holes(since, now, unclosed)
            for (
                hole
            ) in holes:  # durable BEFORE the marker moves: a crash here cannot forget the downtime
                await record_gap(session, self.spec, hole)
            await write_alive(session, self.spec, now, now + ONE_US)
        self._alive_from = now + ONE_US
        for hole in holes:
            self.book.on_gap(hole, now)
        self.book.set_t0(t0)

    @staticmethod
    def _downtime_holes(
        last: datetime, now: datetime, unclosed: list[LeaderGap]
    ) -> list[LeaderGap]:
        """Each hole the dead process left open ended no later than its last marker - **with its own
        scope and its own kind** (a source-health hole stays a health hole; it is not promoted to a
        global loss). The downtime itself is ``[last marker, now)``, global, and owes every leader."""
        holes = [
            LeaderGap(old.wallet, old.start, max(last, old.start + ONE_US), old.reason)
            for old in unclosed
        ]
        if last < now:
            holes.append(LeaderGap(None, last, now, WORKER_DOWNTIME))
        return holes

    # ------------------------------------------------------------------ recomposition
    async def recompose_once(self) -> None:
        """Read what each hole hid (leader by leader) and re-read the copies it blinded. With no history
        hook the leaders simply stay blocked — fail closed."""
        history = self.history
        if history is None:
            return
        now = self._clock()
        for window in self.book.recompositions_due(now):
            try:
                trace = await history.window(
                    window.wallet, window.start, window.end, limit=SIGNATURE_CAP
                )
            except Exception as exc:
                logger.warning("meme_copy_window_failed", error=str(exc)[:200])
                self.book.window_failed(window, self._clock())
                self.stats.recompose_failed += 1
                continue
            jobs = self.book.apply_window(window, trace, self._clock())
            if trace.complete:
                self.stats.recomposed += 1
            else:
                self.stats.recompose_failed += 1
            for job in jobs:
                if isinstance(job, RejectEntry):
                    self.stats.record_rejected(job.reason)
                self.submit(job)
        await self._retrace_censored(history)

    async def _retrace_censored(self, history: LeaderHistory) -> None:
        for pos in self.book.open_positions():
            if pos.gap_reason is None or pos.entry_at is None:
                continue
            tries, next_try = self._trace_next.get(pos.key, (0, self._clock()))
            if next_try > self._clock():
                continue
            try:
                trace = await history.mint_trace(pos.leader, pos.mint, pos.entry_at)
            except Exception as exc:
                logger.warning("meme_copy_trace_failed", error=str(exc)[:200])
                trace = None
            if trace is None:
                wait = min(TRACE_RETRY_MAX_S, TRACE_RETRY_FIRST_S * 2**tries)
                self._trace_next[pos.key] = (tries + 1, self._clock() + timedelta(seconds=wait))
                continue
            flag = WORKER_RESTART_GAP if pos.gap_reason == WORKER_RESTART_GAP else LEADER_GAP_EXIT
            self._trace_next.pop(pos.key, None)
            for job in self.book.apply_trace(pos.key, trace, self._clock(), reason_flag=flag):
                self.submit(job)

    # ------------------------------------------------------------------ liveness
    def _track(self, job: Job) -> None:
        """Remember a fact the funnel needs until it is durable: the liveness marker never moves past the
        oldest one, so a crash leaves a downtime that reaches back to it."""
        if isinstance(job, OpenIntent | RejectEntry | CensorEntry | RecordGap | RecomposeDone):
            self._unlanded.setdefault(job.oid, self._job_time(job))

    def settled(self, oid: str) -> None:
        self._unlanded.pop(oid, None)

    def oldest_unlanded(self) -> datetime | None:
        return min(self._unlanded.values(), default=None)

    async def marker_once(self) -> None:
        """The lane was alive up to now - or up to the oldest fact not yet durable, whichever is older:
        a crash must leave a downtime that reaches back to what was only in memory. Contiguous with the
        previous marker; a failed write leaves ``_alive_from`` where it was."""
        if self._alive_from is None:
            return
        now = self._clock()
        oldest = min(self._unlanded.values(), default=None)
        upto = now if oldest is None else min(now, oldest)
        if upto <= self._alive_from:
            return
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await write_alive(session, self.spec, self._alive_from, upto)
        self._alive_from = upto

    # ------------------------------------------------------------------ stopping
    async def stop(self) -> None:
        """No obligation is dropped silently when the lane stops (a rule-set change restarts it): in-flight
        work is cancelled and handed back, what can still be written is written, and a funnel fact that
        cannot is recorded as a ``funil_indisponivel`` hole from the **oldest** such fact - left open, so
        the next process closes it at the last marker and recomposes it. The final liveness marker is
        written only when nothing was lost: otherwise the previous marker keeps the downtime honest."""
        pending = [*await self.executor.shutdown(), *self.drain_pending()]
        lost: list[datetime] = []
        for job in pending:
            if isinstance(job, OpenIntent):
                lost.append(job.decided_at)  # a decided entry that never got its row
            elif isinstance(job, RejectEntry | CensorEntry | RecordGap | RecomposeDone):
                try:
                    await asyncio.wait_for(self.executor.run_now(job), STOP_WRITE_TIMEOUT_S)
                except Exception:
                    lost.append(self._job_time(job))
            elif not isinstance(job, CloseIntent):  # a late fact about a copy: best effort
                try:
                    await asyncio.wait_for(self.executor.run_now(job), STOP_WRITE_TIMEOUT_S)
                except Exception as exc:
                    self.stats.annotation_lost += 1
                    logger.warning("meme_copy_stop_fact_unwritten", error=str(exc)[:200])
                    if isinstance(job, UnverifiedIntent | InvalidateIntent):
                        lost.append(self._clock())  # a terminal note: the restart cannot know it
            # a CloseIntent stays a row that is still open: the restart re-reads the leader's position
        recorded = True
        if lost:
            hole = LeaderGap(None, min(lost), None, FUNIL_INDISPONIVEL)
            try:
                await asyncio.wait_for(self.executor.run_now(RecordGap(hole)), STOP_WRITE_TIMEOUT_S)
            except Exception as exc:
                recorded = False
                logger.warning("meme_copy_stop_gap_unwritten", error=str(exc)[:200])
        if recorded:
            try:
                await asyncio.wait_for(self.marker_once(), STOP_WRITE_TIMEOUT_S)
            except Exception as exc:  # best effort; the previous marker bounds the downtime
                logger.warning("meme_copy_stop_marker_unwritten", error=str(exc)[:200])

    def _job_time(self, job: Job) -> datetime:
        decided = getattr(job, "decided_at", None)
        if decided is not None:
            return decided
        for name in ("start",):
            if hasattr(job, name):
                return getattr(job, name)
        gap = getattr(job, "gap", None)
        return gap.start if gap is not None else self._clock()
