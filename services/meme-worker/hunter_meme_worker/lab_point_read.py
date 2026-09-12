"""T4.16b: before a pending exit is written off as ``indeterminate``, one
point read of the mint's own curve straight from the chain.

The measured cause (``docs/RISK_ENGINE_MEME.md`` §10): the tracker's cap can
evict a mint the Lab still holds a bet on, and once it is out of the tracked
set neither the minute loop nor the fast lane photographs it again — the last
snapshot a bet has to price its exit against just stops arriving, however
alive the curve still is. Pinning (``tracker_pins.py``) is the fix for a bet
still inside its normal life; this is the fix for the instant right before an
``indeterminate`` close, when the tracker has already lost the mint and there
is no time left to wait for the next tick's pin reload to catch up: one
``getMultipleAccounts`` of exactly this mint, the same chain client and the
same budget the minute loop spends (``ctx.chain`` is the same instance,
``main.py``), never more than one RPC call and never a retry — the caller
falls back to ``indeterminate`` exactly as before this existed when the read
fails, refuses, or the mint's own clock does not move forward.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from hunter_core.logging import get_logger
from hunter_meme_worker.curve_rows import snapshot_row
from hunter_meme_worker.lab_repo_bets import first_snapshot_after
from hunter_meme_worker.metrics import meme_polls_total
from hunter_meme_worker.paper_engine import close_bet
from hunter_meme_worker.repo import insert_snapshot

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_models import BetExit, BetState

__all__ = ["point_read_rescue"]

logger = get_logger(__name__)


def _parse(value: Any) -> datetime:
    return datetime.fromisoformat(str(value))


async def point_read_rescue(
    ctx: LabContext,
    session: AsyncSession,
    state: BetState,
    intent: dict[str, Any] | None,
    reason: str,
    *,
    now: datetime,
) -> tuple[BetExit, int] | None:
    """Sell into a fresh chain read instead of nothing, when the chain has one
    to give. ``None`` means the caller's ``close_without_snapshot`` still
    applies — no response is the only case that stays ``indeterminate``."""
    if ctx.chain is None:
        return None
    try:
        batch = await ctx.chain.get_curve_states([state.mint])
    except Exception as exc:  # one bet's rescue is not the tick's
        meme_polls_total.labels(source="solana_rpc", outcome="error").inc()
        logger.warning(
            "meme_lab_point_read_failed",
            bet_id=state.id,
            mint=state.mint,
            error=str(exc)[:200],
        )
        return None
    curve_state = batch.states.get(state.mint)
    if curve_state is None:
        meme_polls_total.labels(source="solana_rpc", outcome="insufficient_coverage").inc()
        return None
    meme_polls_total.labels(source="solana_rpc", outcome="ok").inc()
    await insert_snapshot(session, snapshot_row(curve_state))
    after = state.mark_at or state.entry_at
    snapshot = await first_snapshot_after(session, mint=state.mint, after=after)
    if snapshot is None:  # the read did not move the mint's own clock forward
        return None
    trigger_at = None if intent is None else intent.get("snapshot_observed_at")
    exit_ = close_bet(
        state,
        snapshot,
        reason,
        await ctx.sol_usd(now),
        intent_snapshot_at=None if not trigger_at else _parse(trigger_at),
    )
    mark_stale_s = max(0, int((now - snapshot.observed_at).total_seconds()))
    return exit_, mark_stale_s
