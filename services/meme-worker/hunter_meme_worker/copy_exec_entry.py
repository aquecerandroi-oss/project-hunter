"""The entry half of the copy executor (H-037): a priced entry, an admitted attempt that never filled, a
rejected funnel row, a coverage hole. Split from ``copy_exec.py`` for the 350-line budget; the executor
inherits it and owns the state these methods use.

**The fill deadline is ``decided_at`` + 30 s** (``FILL_DEADLINE_S``, pending emenda 5), not the target
instant + 30 s: the declared latency eats into the window, it does not extend it. What an open priced is
held by the job's ``oid`` (a fill, a pool mint, a named refusal): a failure to write redelivers the *same*
outcome instead of pricing again.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_meme_worker.copy_bets import bet_state_of, build_entry
from hunter_meme_worker.copy_events import (
    INSUFFICIENT_CURVE_RESERVES,
    SEM_ESTADO,
    VENUE_FORA_DO_ESCOPO,
    ms_iso,
)
from hunter_meme_worker.copy_position import Live
from hunter_meme_worker.copy_repo_funnel import censor_entry, open_copy_bet, reject_entry
from hunter_meme_worker.copy_repo_gaps import record_gap, record_recomposed
from hunter_meme_worker.copy_retry import Held, PricedEntry
from hunter_meme_worker.copy_sens import Sensitivities

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine
    from datetime import datetime
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import (
        CensorEntry,
        LeaderRef,
        OpenIntent,
        RecomposeDone,
        RecordGap,
        RejectEntry,
    )
    from hunter_meme_worker.copy_reads import CopyReader
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats

__all__ = ["FILL_DEADLINE_S", "EntryJobs"]

WORKER_ROLE = "hunter_worker"
FILL_DEADLINE_S = 30
"""Named constant (R2 fix F9, pending the emenda): the fill window counts from the decision."""


class EntryJobs(Sensitivities):
    spec: CopySpec
    live: dict[str, Live]
    _sessions: async_sessionmaker[AsyncSession]
    _reader: CopyReader
    _book: CopyBook
    _stats: CopyStats
    _clock: Callable[[], datetime]
    _held_entry: Held[PricedEntry]

    def spawn_side(self, coro: Coroutine[Any, Any, None]) -> None:
        raise NotImplementedError

    async def _record_gap(self, job: RecordGap) -> None:
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await record_gap(session, self.spec, job.gap)

    async def _recomposed(self, job: RecomposeDone) -> None:
        """The pairs a leader bought inside a hole, then the durable mark that its slice is done - one
        transaction: a crash can never leave the mark without the pairs."""
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            for seen in job.seen:
                await reject_entry(
                    session,
                    self.spec,
                    mint=seen.mint,
                    ref=seen.leader,
                    decided_at=seen.decided_at,
                    reason=seen.reason,
                )
            await record_recomposed(
                session,
                self.spec,
                wallet=job.wallet,
                hole_id=job.gap_id,
                start=job.start,
                end=job.end,
            )

    # ------------------------------------------------------------------ funnel rows
    async def _reject(self, job: RejectEntry) -> None:
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            written = await reject_entry(
                session,
                self.spec,
                mint=job.mint,
                ref=job.leader,
                decided_at=job.decided_at,
                reason=job.reason,
            )
        if not written:
            self._stats.funnel_collisions += 1

    async def _write_unfilled(
        self, mint: str, ref: LeaderRef, decided_at: datetime, reason: str, *, key: str | None
    ) -> None:
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await censor_entry(
                session, self.spec, mint=mint, ref=ref, decided_at=decided_at, reason=reason
            )
        if key is not None:
            self._book.mark_closed(key)
        self._stats.record_censored(ref.wallet, reason)

    async def _censor(self, job: CensorEntry) -> None:
        await self._write_unfilled(job.mint, job.leader, job.decided_at, job.reason, key=None)

    async def _venue_out(self, job: OpenIntent) -> None:
        """The mint trades on the pool, outside this cohort's venues (emenda 4 b): a ``rejected`` funnel
        row, the first observation of the pair, no attempt consumed and no key taken."""
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await reject_entry(
                session,
                self.spec,
                mint=job.mint,
                ref=job.leader,
                decided_at=job.decided_at,
                reason=VENUE_FORA_DO_ESCOPO,
            )
        self._book.pool_mint_found(
            job.key, job.leader.wallet, job.leader.stratum, job.mint, job.decided_at.date()
        )
        self._stats.record_rejected(VENUE_FORA_DO_ESCOPO)

    # ------------------------------------------------------------------ the entry
    async def _price_open(self, job: OpenIntent) -> PricedEntry:
        read = await self._reader.curve_at(
            job.mint,
            not_before=job.target_at,
            deadline=job.decided_at + timedelta(seconds=FILL_DEADLINE_S),
            min_slot=job.leader.slot + 1,
        )
        emptied = read is None and self._reader.last_refused.get(job.mint) == "curve_emptied"
        if emptied or (
            read is not None and (read.snapshot.complete or read.snapshot.reserves.complete)
        ):
            return PricedEntry("venue")  # on the pool: the paper machinery has no pool BUY quote
        if read is None:
            return PricedEntry("censor", reason=SEM_ESTADO)
        try:
            entry = build_entry(
                self.spec, read.snapshot, job, queued_at=job.decided_at, slot=read.slot
            )
        except ValueError:  # quote_buy: the curve no longer sells that much
            return PricedEntry("censor", reason=INSUFFICIENT_CURVE_RESERVES)
        self._stats.record_priced(
            round((read.snapshot.observed_at - job.decided_at).total_seconds() * 1000)
        )
        return PricedEntry("fill", entry=entry, mayhem=read.snapshot.mayhem_enabled, slot=read.slot)

    async def _open(self, job: OpenIntent) -> None:
        priced = self._held_entry.get(job.oid)
        if priced is None:
            priced = await self._price_open(job)
            self._held_entry.put(job.oid, priced)
        if priced.kind == "venue":
            await self._venue_out(job)
            return
        if priced.kind == "censor":
            assert priced.reason is not None
            await self._write_unfilled(
                job.mint, job.leader, job.decided_at, priced.reason, key=job.key
            )
            return
        entry = priced.entry
        assert entry is not None
        started = self._clock()
        entry.entry["copy"]["ts"]["persisted_at"] = ms_iso(
            started
        )  # the instant the write is issued
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            bet_id = await open_copy_bet(
                session,
                self.spec,
                mint=job.mint,
                ref=job.leader,
                decided_at=job.decided_at,
                entry=entry,
            )
        self._stats.record_persisted(round((self._clock() - started).total_seconds() * 1000))
        state = bet_state_of(
            bet_id=bet_id,
            rule_set_id=self.spec.id,
            mint=job.mint,
            entry=entry,
            mayhem=priced.mayhem,
        )
        self.live[job.key] = Live(
            bet_id=bet_id, state=state, leader=job.leader.wallet, last_slot=priced.slot
        )
        self._book.mark_open(job.key, bet_id=bet_id, entry_at=entry.entry_at)
        self._stats.record_entry(job.leader.wallet, at=job.decided_at)
        self.spawn_side(self.entry_p90(job, bet_id, job.key))
