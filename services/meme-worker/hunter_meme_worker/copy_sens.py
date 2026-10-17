"""The latency sensitivities of a copy (H-037, design §3.3), **secondary fields only**: they never decide, size
or close anything and a failure of any of them cannot fail a job (they run as side tasks).

* ``p90`` — the entry (and, if its causal order allows, the exit) priced at the first eligible state at or
  after ``decided_at + stress_latency_s`` (3.9 s, the p90 of KB-0182), through the same read path as the
  nominal fill. An entry whose p90 state is only observable **after** the primary exit intent has no p90
  exit: ``unavailable/causal_order`` — it is never a sale before the purchase;
* ``ideal`` — the market right after the leader's trade, which the chain's confirmation carries
  (``LeaderConfirmation.post_reserves``); persisted by the confirmation job as ``ideal_post_reserves``.

Stored in ``entry.copy.sensitivity_p90`` / ``exit.copy.sensitivity_p90`` (the existing JSON columns).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_meme_worker.copy_bets import build_entry
from hunter_meme_worker.copy_events import ms_iso
from hunter_meme_worker.copy_repo import set_copy_fact
from hunter_meme_worker.paper_engine import close_bet

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.copy_events import CloseIntent, OpenIntent
    from hunter_meme_worker.copy_position import Live
    from hunter_meme_worker.copy_reads import CopyReader
    from hunter_meme_worker.copy_spec import CopySpec
    from hunter_meme_worker.copy_stats import CopyStats
    from hunter_meme_worker.lab_models import BetState

__all__ = ["Sensitivities"]

logger = get_logger(__name__)
WORKER_ROLE = "hunter_worker"
FIELD = "sensitivity_p90"


class Sensitivities:
    spec: CopySpec
    live: dict[str, Live]
    _sessions: async_sessionmaker[AsyncSession]
    _reader: CopyReader
    _stats: CopyStats
    _clock: Callable[[], datetime]

    def _window(self, decided_at: datetime) -> tuple[datetime, datetime]:
        not_before = decided_at + timedelta(milliseconds=self.spec.stress_latency_ms)
        return not_before, not_before + timedelta(seconds=self.spec.fill_window_s)

    async def _write(self, bet_id: str, where: str, value: dict[str, Any]) -> None:
        try:
            async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
                await set_copy_fact(session, bet_id, where=where, name=FIELD, value=value)
        except Exception as exc:  # secondary: never fails a job
            self._stats.side_failed += 1
            logger.warning("meme_copy_sensitivity_write_failed", error=str(exc)[:200])

    async def entry_p90(self, job: OpenIntent, bet_id: str, key: str) -> None:
        not_before, deadline = self._window(job.decided_at)
        read = await self._reader.curve_at(
            job.mint, not_before=not_before, deadline=deadline, min_slot=job.leader.slot + 1
        )
        if read is None or read.snapshot.complete or read.snapshot.reserves.complete:
            await self._write(bet_id, "entry", {"unavailable": "no_state"})
            return
        try:
            alt = build_entry(
                self.spec, read.snapshot, job, queued_at=job.decided_at, slot=read.slot
            )
        except ValueError:
            await self._write(bet_id, "entry", {"unavailable": "insufficient_curve_reserves"})
            return
        value: dict[str, Any] = {
            "priced_at": ms_iso(read.snapshot.observed_at),
            "slot": read.slot,
            "latency_s": str(self.spec.stress_latency_s),
            "tokens": alt.entry["tokens"],
            "sol_spent": alt.entry["sol_spent"],
            "curve_cost_sol": alt.entry["curve_cost_sol"],
            "average_price_sol": alt.entry["average_price_sol"],
        }
        live = self.live.get(key)
        if live is not None:
            live.p90 = {**value, "observed_at": read.snapshot.observed_at}
        await self._write(bet_id, "entry", value)

    async def exit_p90(
        self, state: BetState, p90: dict[str, Any] | None, job: CloseIntent, bet_id: str
    ) -> None:
        if p90 is None:
            await self._write(bet_id, "exit", {"unavailable": "no_entry_p90"})
            return
        if p90["observed_at"] > job.decided_at:  # the p90 purchase did not exist yet at the intent
            await self._write(bet_id, "exit", {"unavailable": "causal_order"})
            return
        not_before, deadline = self._window(job.decided_at)
        read = await self._reader.curve_at(
            state.mint,
            not_before=not_before,
            deadline=deadline,
            min_slot=int(p90["slot"]) + 1,
            after=p90["observed_at"],
        )
        if read is None or read.snapshot.complete or read.snapshot.reserves.complete:
            await self._write(bet_id, "exit", {"unavailable": "no_state"})
            return
        alt = replace(
            state,
            tokens=Decimal(p90["tokens"]),
            sol_spent=Decimal(p90["sol_spent"]),
            initial_risk_sol=Decimal(p90["sol_spent"]),
            curve_cost_sol=Decimal(p90["curve_cost_sol"]),
        )
        closed = close_bet(alt, read.snapshot, job.reason, None, intent_snapshot_at=job.decided_at)
        await self._write(
            bet_id,
            "exit",
            {
                "priced_at": ms_iso(read.snapshot.observed_at),
                "slot": read.slot,
                "sol_received": closed.exit["sol_received"],
                "pnl_sol": str(closed.pnl_sol),
                "r_multiple": str(closed.r_multiple),
            },
        )
