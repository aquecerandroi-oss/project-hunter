"""The entry half of the copy executor (H-037): a priced entry, an admitted attempt that never filled,
a rejected funnel row, a coverage hole. Split from ``copy_exec.py`` for the 350-line budget; the
executor inherits it and owns the state these methods use."""

from __future__ import annotations

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
from hunter_meme_worker.copy_repo import censor_entry, open_copy_bet, reject_entry
from hunter_meme_worker.copy_repo_gaps import record_gap

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import LeaderRef, OpenIntent, RecordGap, RejectEntry
    from hunter_meme_worker.copy_reads import CopyReader
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats

__all__ = ["EntryJobs"]

WORKER_ROLE = "hunter_worker"


class EntryJobs:
    spec: CopySpec
    live: dict[str, Live]
    _sessions: async_sessionmaker[AsyncSession]
    _reader: CopyReader
    _book: CopyBook
    _stats: CopyStats
    _clock: Callable[[], datetime]

    async def _record_gap(self, job: RecordGap) -> None:
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await record_gap(session, self.spec, job.gap)

    # ------------------------------------------------------------------ entry
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

    async def _censor(
        self, mint: str, ref: LeaderRef, decided_at: datetime, reason: str, *, key: str | None
    ) -> None:
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            await censor_entry(
                session, self.spec, mint=mint, ref=ref, decided_at=decided_at, reason=reason
            )
        if key is not None:
            self._book.mark_closed(key)
        self._stats.record_censored(ref.wallet, reason)

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

    async def _open(self, job: OpenIntent) -> None:
        read = await self._reader.curve_at(
            job.mint,
            not_before=job.target_at,
            window_s=self.spec.fill_window_s,
            min_slot=job.leader.slot + 1,
        )
        emptied = read is None and self._reader.last_refused.get(job.mint) == "curve_emptied"
        if emptied or (
            read is not None and (read.snapshot.complete or read.snapshot.reserves.complete)
        ):
            await self._venue_out(job)  # on the pool: the paper machinery has no pool BUY quote
            return
        if read is None:
            await self._censor(job.mint, job.leader, job.decided_at, SEM_ESTADO, key=job.key)
            return
        snapshot = read.snapshot
        try:
            entry = build_entry(self.spec, snapshot, job, queued_at=job.decided_at, slot=read.slot)
        except ValueError:  # quote_buy: the curve no longer sells that much
            await self._censor(
                job.mint, job.leader, job.decided_at, INSUFFICIENT_CURVE_RESERVES, key=job.key
            )
            return
        self._stats.record_priced(
            round((snapshot.observed_at - job.decided_at).total_seconds() * 1000)
        )
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
            mayhem=snapshot.mayhem_enabled,
        )
        self.live[job.key] = Live(
            bet_id=bet_id, state=state, leader=job.leader.wallet, last_slot=read.slot
        )
        self._book.mark_open(job.key, bet_id=bet_id, entry_at=entry.entry_at)
        self._stats.record_entry(job.leader.wallet, at=job.decided_at)
