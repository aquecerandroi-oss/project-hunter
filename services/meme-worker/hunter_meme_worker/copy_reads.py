"""The copy lane's market reads (H-037) — everything that *waits for or fetches* a price, away from
the decision path: one chain read of the curve at/after the pricing instant, and the pool tape for a
migrated mint. Time and sleeping are injected (``clock``/``sleep``) so a test drives them.

**The eligible state** (design §3.3/§3.4) is the first one that satisfies all of: observed at or after
``not_before`` (= ``decided_at`` + the declared execution latency); served at a slot of at least
``min_slot`` (the leader's slot + 1 for an entry, the exit floor for a sale — a state from before the
leader's own transaction is never a price for copying it); observed after ``after`` (our own entry,
so an exit is never priced at the state the entry used); read at ``confirmed`` commitment. A state whose
slot is unknown cannot be shown to satisfy the floor and is not eligible — closed, never optimistic.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_indicators.meme.pool import VOLUME_WINDOW, PoolTrade
from hunter_meme_worker.copy_bets import snapshot_of
from hunter_meme_worker.lab_repo_pool import pool_trades

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.context import ChainSource
    from hunter_meme_worker.lab_models import Snapshot

__all__ = ["CopyReader", "CurveRead"]

logger = get_logger(__name__)

WORKER_ROLE = "hunter_worker"
RETRY_S = 0.25
POOL_RETRY_S = 1.0
COMMITMENT = "confirmed"
"""The fast lane's own paper-read commitment (``MEME_FAST_LANE_COMMITMENT``): proposal/paper reads
only — the admissor of a real order re-reads before money moves, which this lane never reaches."""


@dataclass(frozen=True, slots=True)
class CurveRead:
    snapshot: Snapshot
    slot: int


class CopyReader:
    def __init__(
        self,
        *,
        chain: ChainSource,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._chain = chain
        self._sessions = session_factory
        self._clock = clock
        self._sleep = sleep
        self.last_refused: dict[str, str] = {}
        """The adapter's named refusal per mint on the last read (``curve_emptied`` = migrated)."""

    async def sleep_until(self, target: datetime) -> None:
        delay = (target - self._clock()).total_seconds()
        if delay > 0:
            await self._sleep(delay)

    async def curve_at(
        self,
        mint: str,
        *,
        not_before: datetime,
        window_s: int,
        min_slot: int,
        after: datetime | None = None,
    ) -> CurveRead | None:
        """The eligible curve state (see the module docstring), retrying for ``window_s``; ``None``
        when none came back — never a guess."""
        await self.sleep_until(not_before)
        deadline = not_before + timedelta(seconds=window_s)
        while True:
            remaining = max(0.001, (deadline - self._clock()).total_seconds())
            try:
                async with asyncio.timeout(remaining):  # a stuck RPC cannot hold the window open
                    batch = await self._chain.get_curve_states(
                        [mint], with_block_time=False, commitment=COMMITMENT
                    )
            except Exception as exc:  # one failed read is a retry, not a crash
                logger.warning("meme_copy_curve_read_failed", mint=mint, error=str(exc)[:200])
            else:
                refusal = batch.refused.get(mint)
                if refusal is not None:
                    self.last_refused[mint] = refusal
                state = batch.states.get(mint)
                if (
                    state is not None
                    and state.slot is not None
                    and state.slot >= min_slot
                    and not_before <= state.observed_at <= deadline
                    and (after is None or state.observed_at > after)
                ):
                    return CurveRead(snapshot_of(state), state.slot)
            if self._clock() >= deadline:
                return None
            await self._sleep(RETRY_S)

    async def pool_sale_trades(
        self, mint: str, *, not_before: datetime, after: datetime, window_s: int
    ) -> tuple[PoolTrade, list[PoolTrade]] | None:
        """The first pool trade at/after ``not_before`` — whole-second resolution, the swap-api
        tape's own — and the trades known by now (for the impact window); ``None`` inside the
        window means no trade to sell into, a censor and not a fill."""
        deadline = not_before + timedelta(seconds=window_s)
        # whole-second tape: never sell on a trade that may have printed before the allowed instant
        floor = not_before.replace(microsecond=0)
        if floor < not_before:
            floor += timedelta(seconds=1)
        while True:
            now = self._clock()
            async with role_session(self._sessions, db_role=WORKER_ROLE) as session:
                trades = await pool_trades(
                    session, mint=mint, since=floor - VOLUME_WINDOW, until=min(now, deadline)
                )
            ready = [
                t for t in trades if floor <= t.block_time <= deadline and t.block_time > after
            ]
            if ready:
                return min(ready, key=lambda t: t.block_time), trades
            if now >= deadline:
                return None
            await self._sleep(POOL_RETRY_S)
