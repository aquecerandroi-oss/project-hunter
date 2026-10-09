"""The copy lane's periodic mark pass (H-037): one batched chain read of every open copy's curve, the
live mark written with the Lab's ``update_mark`` (so Everton can watch a copy live), and our **safety
stop** — the only exit that is neither the leader's nor the clock's. It runs off the hot path, every
``mark_every_s`` seconds; the stop fires a close job exactly like a leader sell does, and that job is
priced at the next eligible read after the declared latency.

**After the migration** the curve no longer prices the copy. The pass then follows the cohort's
``venues``: without ``pumpswap`` the copy is sent out as ``migrated`` and closed ``indeterminate/
migrou_fora_de_praca`` (priced by no one); with it, the copy is marked on the PumpSwap pool's tape with
``pool_mark.mark_on_pool`` — the same arithmetic ``lab_bets_pool`` uses — and the stop keeps working.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.logging import get_logger
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.pool import VOLUME_WINDOW, last_trade_at_or_before
from hunter_meme_worker.copy_bets import snapshot_of
from hunter_meme_worker.copy_events import EXIT_SAFETY_STOP, MIGROU_FORA_DE_PRACA
from hunter_meme_worker.lab_models import MARK_POOL_TAPE
from hunter_meme_worker.lab_repo_bets import update_mark
from hunter_meme_worker.lab_repo_pool import pool_trades
from hunter_meme_worker.paper_engine import mark_bet
from hunter_meme_worker.pool_mark import mark_on_pool

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_meme_worker.context import ChainSource
    from hunter_meme_worker.copy_book import CopyBook
    from hunter_meme_worker.copy_events import CloseIntent
    from hunter_meme_worker.copy_position import Live
    from hunter_meme_worker.copy_spec import CopySpec

__all__ = ["mark_pass", "stop_hit"]

logger = get_logger(__name__)
WORKER_ROLE = "hunter_worker"
COMMITMENT = "confirmed"
MIGRATED_REASON = "migrated"
POOL_LOOKBACK = timedelta(minutes=10)


def stop_hit(mark_sol: Decimal, sol_spent: Decimal, stop_fraction: Decimal) -> bool:
    """The mark is at or below ``stop_fraction`` of what the copy cost (the design's 50 %)."""
    with localcontext(CONTEXT):
        return mark_sol <= sol_spent * stop_fraction


async def _mark_on_pool(
    session: AsyncSession, entry: Live, at: datetime
) -> tuple[Decimal, Decimal, datetime] | None:
    """``(mark_sol, high_water_x, trade block time)`` on the latest pool trade known by ``at``."""
    trades = await pool_trades(
        session, mint=entry.state.mint, since=at - POOL_LOOKBACK - VOLUME_WINDOW, until=at
    )
    trade = last_trade_at_or_before(trades, at)
    if trade is None:
        return None
    pool = mark_on_pool(entry.state, trade, trades, total_supply=None)
    return pool.mark.mark_sol, pool.mark.high_water_x, trade.block_time


async def mark_pass(
    *,
    spec: CopySpec,
    chain: ChainSource,
    session_factory: async_sessionmaker[AsyncSession],
    book: CopyBook,
    live: dict[str, Live],
    submit: Callable[[CloseIntent], None],
    now: Callable[[], datetime],
) -> int:
    """Mark every open copy once; returns how many were marked. Never raises on a failed read."""
    open_keys = {p.key for p in book.open_positions() if p.key in live}
    if not open_keys:
        return 0
    mints = sorted({live[k].state.mint for k in open_keys})
    try:
        batch = await chain.get_curve_states(mints, with_block_time=False, commitment=COMMITMENT)
    except Exception as exc:  # the next pass retries; a failed read marks nothing
        logger.warning("meme_copy_mark_read_failed", error=str(exc)[:200])
        return 0
    marked = 0
    pool_venue = "pumpswap" in spec.venues
    async with role_session(session_factory, db_role=WORKER_ROLE) as session:
        for key in open_keys:
            entry = live.get(key)
            state = batch.states.get(entry.state.mint) if entry is not None else None
            emptied = entry is not None and batch.refused.get(entry.state.mint) == "curve_emptied"
            if entry is None or (state is None and not emptied):
                continue
            if emptied or (state is not None and state.complete):
                if not pool_venue:  # the pool is not a venue: out, unpriced, by name
                    job = book.request_exit(
                        key, MIGRATED_REASON, now(), censor=MIGROU_FORA_DE_PRACA
                    )
                    if job is not None:
                        submit(job)
                    continue
                pooled = await _mark_on_pool(session, entry, now())
                if pooled is None:
                    continue
                mark_sol, high_water, mark_at = pooled
                source = MARK_POOL_TAPE
            else:
                assert state is not None
                snapshot = snapshot_of(state)
                mark = mark_bet(entry.state, snapshot)
                mark_sol, high_water, mark_at, source = (
                    mark.mark_sol,
                    mark.high_water_x,
                    snapshot.observed_at,
                    "curve",
                )
                if state.slot is not None:
                    entry.last_slot = max(entry.last_slot, state.slot)
            entry.state = replace(entry.state, high_water_x=high_water)
            await update_mark(
                session,
                entry.bet_id,
                mark_sol=mark_sol,
                mark_at=mark_at,
                high_water_x=high_water,
                exit_intent=None,
                mark_source=source,
            )
            marked += 1
            if stop_hit(mark_sol, entry.state.sol_spent, spec.stop_fraction):
                job = book.request_exit(key, EXIT_SAFETY_STOP, now())
                if job is not None:
                    submit(job)
    return marked
