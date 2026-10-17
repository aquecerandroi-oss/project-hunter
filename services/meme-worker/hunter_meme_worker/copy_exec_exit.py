"""The exit half of the copy executor (H-037): price the sale of a copy and write it. Split from
``copy_exec.py`` for the 350-line budget; the executor inherits it and owns the state these methods use.

The sale is priced at the first eligible state: observed at or after ``max(decided_at + latency,
entry_at + latency)`` (an exit decided *before* the fill still waits the latency **after** it), at a slot
strictly above the copy's last accepted slot and above the leader's own slot, and after the entry's own
state (``after=entry_at``) — the entry is never its own exit. What was priced is held by the job's ``oid``:
a failure to write redelivers the same sale.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.copy_bets import censored_exit, close_on_curve, close_on_pool_trade
from hunter_meme_worker.copy_events import (
    LEADER_GAP_EXIT,
    MIGROU_FORA_DE_PRACA,
    NO_EXIT_STATE,
    NO_POOL_TRADE,
    WORKER_RESTART_GAP,
    ms_iso,
)
from hunter_meme_worker.copy_exec_facts import NotYet
from hunter_meme_worker.copy_repo import close_copy_bet
from hunter_meme_worker.copy_retry import Held, PricedExit
from hunter_meme_worker.copy_sens import Sensitivities
from hunter_meme_worker.lab_models import MARK_CURVE, MARK_POOL_TAPE

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine
    from datetime import datetime
    from typing import Any

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import CloseIntent
    from hunter_meme_worker.copy_history import MintTrace
    from hunter_meme_worker.copy_position import Live
    from hunter_meme_worker.copy_reads import CopyReader
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats
    from hunter_meme_worker.lab_models import BetExit, BetState

__all__ = ["ExitJobs"]

logger = get_logger(__name__)
WORKER_ROLE = "hunter_worker"
CLOSED_MEMORY = 5000


class ExitJobs(Sensitivities):
    spec: CopySpec
    live: dict[str, Live]
    _sessions: async_sessionmaker[AsyncSession]
    _reader: CopyReader
    _book: CopyBook
    _stats: CopyStats
    _clock: Callable[[], datetime]
    _closed: dict[str, str]
    _held_exit: Held[PricedExit]
    _retrace: Callable[[str, str, datetime], Awaitable[MintTrace | None]] | None

    def spawn_side(self, coro: Coroutine[Any, Any, None]) -> None:
        raise NotImplementedError

    async def _lift_censor(self, live: Live, job: CloseIntent) -> str | None:
        """A leader-driven exit censored only because the leader's position had not been **re-read** yet
        (a hole, a restart): read it now. Readable = the exit is priced and flagged; unreadable (or no
        history hook) = the censor stands, by name. A *pending* read is not an *impossible* one (R2 F8)."""
        censor = job.censor
        if censor not in (LEADER_GAP_EXIT, WORKER_RESTART_GAP) or self._retrace is None:
            return censor
        trace = await self._retrace(live.leader, live.state.mint, live.state.entry_at)
        if trace is None:
            return censor
        self._book.lift_censor(job.key, censor)
        return None

    async def _price_close(self, live: Live, job: CloseIntent) -> PricedExit:
        censor = await self._lift_censor(live, job)
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
        flag = job.contaminated or (pos.contam if pos else None)
        if flag is None and censor is None and pos is not None:
            flag = pos.gap_reason
        closed.exit["copy"]["contaminated"] = flag
        return PricedExit(closed, mark_source, censor)

    async def _close(self, job: CloseIntent) -> None:
        live = self.live.get(job.key)
        if live is None:
            if self._book.position(job.key) is not None:
                raise NotYet  # the entry is still being delivered: the exit waits for its row
            return  # the entry never became a bet (refused): nothing to sell
        priced = self._held_exit.get(job.oid)
        if priced is None:
            priced = await self._price_close(live, job)
            self._held_exit.put(job.oid, priced)
        closed = priced.closed
        started = self._clock()
        stamp = ms_iso(started)
        closed.exit["copy"]["ts"]["persisted_at"] = stamp
        async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
            landed = await close_copy_bet(
                session, live.bet_id, closed, mark_source=priced.mark_source, stamp=stamp
            )
        self._stats.record_persisted(round((self._clock() - started).total_seconds() * 1000))
        del self.live[job.key]
        if not landed:  # another writer (the Lab, an operator) closed this row first
            self._stats.closed_elsewhere += 1
            logger.warning("meme_copy_closed_by_another_writer", bet_id=live.bet_id, key=job.key)
            self._book.mark_closed(job.key)
            return
        self._closed[job.key] = live.bet_id
        while len(self._closed) > CLOSED_MEMORY:
            self._closed.pop(next(iter(self._closed)))
        self._book.mark_closed(job.key)
        if priced.censor is None:
            self._stats.record_exit(live.leader)
            if priced.mark_source == MARK_CURVE:
                self.spawn_side(self.exit_p90(live.state, live.p90, job, live.bet_id))
        else:
            self._stats.record_censored(live.leader, priced.censor)

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
            deadline=not_before + timedelta(seconds=self.spec.exit_window_s),
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
