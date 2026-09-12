"""The pool side of a Lab tick (T4.11): a bet whose mint migrated and whose
rule set holds through it is walked over the PumpSwap pool's trades it has
not seen yet, the way ``lab_bets._process_one`` walks the curve's snapshots.

Per tick, for one such bet:

1. the pool trades with ``block_time > mark_at`` and ``received_at <= now``
   (plus the five minutes before, for the first trade's volume);
2. **walk in tape order**: a pending intent is filled on the first trade past
   its ``decided_at``; otherwise the trade marks the position
   (``pool_mark.mark_on_pool``) and the exit rules judge it at the trade's
   block time — target, trailing (armed after ``trailing_arm_x``), creator
   dump (the creator's sells re-read from the whole tape), time stop;
3. **the tick itself**: ``mark_stale_s`` = seconds since the last trade the
   tick could see (or since the migration, if the pool never printed), and
   the rules judged once more at ``now`` — this is where ``dead`` can fire
   (silent ≥ ``dead_stale_s`` **and** mark ≤ ``dead_mark_pct`` of the cost),
   and where a time stop fires on a tape that stopped;
4. the row: ``mark_source = pool_tape`` once a pool trade priced it
   (``curve`` until then), ``mark_stale_s`` refreshed every tick;
5. an intent the fill window closes on without a trade: ``dead`` is written
   off at zero **as ``dead``** (``fill = none``); any other reason closes as
   ``rug_no_snapshot`` with ``pending_reason``, exactly like the curve.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from hunter_core.logging import get_logger
from hunter_indicators.meme.pool import VOLUME_WINDOW, PoolTrade, last_trade_at_or_before
from hunter_meme_worker.lab_models import MARK_POOL_TAPE, BetState
from hunter_meme_worker.lab_repo import apply_command
from hunter_meme_worker.lab_repo_bets import close_bet_row, update_mark
from hunter_meme_worker.lab_repo_pool import creator_sold_on_tape, pool_trades
from hunter_meme_worker.paper_engine import Mark, close_without_snapshot, decide_exit_at
from hunter_meme_worker.pool_mark import (
    POOL_VENUE,
    PoolMark,
    close_dead_without_trade,
    close_on_pool,
    mark_on_pool,
    stale_seconds,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_meme_worker.lab import LabContext
    from hunter_meme_worker.lab_rows import CommandRow, OpenBet

logger = get_logger(__name__)

__all__ = ["holds_through_migration", "parse_ts", "process_pool_bet", "settle_command"]


def parse_ts(value: Any) -> datetime:
    return datetime.fromisoformat(str(value))


def holds_through_migration(bet: OpenBet) -> bool:
    """The pool path applies once the mint migrated and the set does not sell on it."""
    return bet.migrated_at is not None and not bet.state.params.exit_on_migration


def _intent(reason: str, *, decided_at: datetime, trade_at: datetime | None) -> dict[str, Any]:
    return {
        "reason": reason,
        "decided_at": decided_at.isoformat(),
        "snapshot_observed_at": None,
        "trade_block_time": None if trade_at is None else trade_at.isoformat(),
        "trigger": "rules",
        "venue": POOL_VENUE,
    }


async def settle_command(
    session: AsyncSession,
    command: CommandRow | None,
    intent: Mapping[str, Any] | None,
    exit_reason: str,
    *,
    now: datetime,
) -> None:
    """The operator's order is answered when the bet closes, whichever rule won."""
    if command is None:
        return
    applied = intent is not None and intent.get("command_id") == command.id
    await apply_command(
        session,
        command.id,
        now=now,
        result={"status": "applied" if applied else "superseded", "exit_reason": exit_reason},
    )


async def process_pool_bet(
    ctx: LabContext,
    session: AsyncSession,
    bet: OpenBet,
    command: CommandRow | None,
    *,
    intent: dict[str, Any] | None,
    now: datetime,
) -> str:
    """Mark, decide and sell one migrated bet over the pool trades it has not seen."""
    state = bet.state
    after = state.mark_at or state.entry_at
    trades = await pool_trades(session, mint=state.mint, since=after - VOLUME_WINDOW, until=now)
    creator_sold = await creator_sold_on_tape(
        session, mint=state.mint, creator=bet.creator, until=now
    )
    last: PoolMark | None = None
    for trade in (t for t in trades if t.block_time > after):
        pool_mark = mark_on_pool(state, trade, trades, total_supply=bet.total_supply)
        if intent is not None and trade.block_time > parse_ts(intent["decided_at"]):
            trigger_at = intent.get("trade_block_time")
            exit_ = close_on_pool(
                state,
                pool_mark,
                str(intent["reason"]),
                await ctx.sol_usd(now),
                intent_trade_at=None if trigger_at is None else parse_ts(trigger_at),
                mark_stale_s=stale_seconds(trade.block_time, _last_seen(bet, trades, trade)),
            )
            exit_.exit["trigger"] = intent.get("trigger")
            await close_bet_row(
                session, state.id, exit_, exit_intent=intent, mark_source=MARK_POOL_TAPE
            )
            await settle_command(session, command, intent, exit_.exit["reason"], now=now)
            logger.info(
                "meme_lab_bet_closed",
                bet_id=state.id,
                mint=state.mint,
                venue=POOL_VENUE,
                reason=exit_.exit["reason"],
                pnl_sol=str(exit_.pnl_sol),
            )
            return "closed"
        state = replace(state, high_water_x=pool_mark.mark.high_water_x)
        last = pool_mark
        if intent is None:
            reason = decide_exit_at(
                state,
                pool_mark.mark,
                at=trade.block_time,
                migrated=True,
                curve_complete=True,
                creator_net_seller=creator_sold,
                sell_now=False,
                mark_stale_s=0,
            )
            if reason is not None:
                intent = _intent(reason, decided_at=trade.block_time, trade_at=trade.block_time)
    return await _judge_the_tick(
        ctx, session, bet, state, command, trades, last, intent, creator_sold, now=now
    )


def _last_seen(bet: OpenBet, trades: list[PoolTrade], before: PoolTrade) -> datetime:
    """The last pool trade strictly before ``before`` — how long the tape was
    silent before the fill — else the migration itself."""
    earlier = [t for t in trades if t.block_time < before.block_time]
    if earlier:
        return max(t.block_time for t in earlier)
    assert bet.migrated_at is not None
    return bet.migrated_at


async def _judge_the_tick(
    ctx: LabContext,
    session: AsyncSession,
    bet: OpenBet,
    state: BetState,
    command: CommandRow | None,
    trades: list[PoolTrade],
    last: PoolMark | None,
    intent: dict[str, Any] | None,
    creator_sold: bool | None,
    *,
    now: datetime,
) -> str:
    """Steps 3–5 of the module docstring: staleness, the rules at ``now``, the
    row, and the window closing on an intent without a trade."""
    assert bet.migrated_at is not None
    latest = last_trade_at_or_before(trades, now)
    last_seen = latest.block_time if latest is not None else max(bet.migrated_at, state.entry_at)
    stale = stale_seconds(now, last_seen)
    if last is not None:
        mark, mark_at, source = last.mark, last.trade.block_time, MARK_POOL_TAPE
    elif state.mark_sol is not None and state.mark_at is not None:
        mark = Mark(mark_sol=state.mark_sol, high_water_x=state.high_water_x)
        mark_at, source = state.mark_at, state.mark_source
    else:  # a bet always has its fill's mark; a row without one is not judged
        return "unchanged"
    if intent is None:
        reason = decide_exit_at(
            state,
            mark,
            at=now,
            migrated=True,
            curve_complete=True,
            creator_net_seller=creator_sold,
            sell_now=False,
            mark_stale_s=stale,
        )
        if reason is not None:
            intent = _intent(reason, decided_at=now, trade_at=None)
    await update_mark(
        session,
        state.id,
        mark_sol=mark.mark_sol,
        mark_at=mark_at,
        high_water_x=mark.high_water_x,
        exit_intent=intent,
        mark_source=source,
        mark_stale_s=stale,
    )
    window = timedelta(seconds=ctx.config.lab_fill_window_s)
    if intent is None or now - parse_ts(intent["decided_at"]) < window:
        return "marked" if last is not None else "unchanged"
    pending = str(intent["reason"])
    if pending == "dead":
        exit_ = close_dead_without_trade(
            state,
            now=now,
            mark_stale_s=stale,
            last_trade_at=latest.block_time if latest is not None else None,
            last_mark_sol=mark.mark_sol,
        )
    else:
        exit_ = close_without_snapshot(state, now=now, pending_reason=pending)
        exit_.exit["venue"] = POOL_VENUE
    await close_bet_row(session, state.id, exit_, exit_intent=intent, mark_source=source)
    await settle_command(session, command, intent, str(exit_.exit["reason"]), now=now)
    logger.warning(
        "meme_lab_bet_closed_without_trade",
        bet_id=state.id,
        mint=state.mint,
        venue=POOL_VENUE,
        reason=exit_.exit["reason"],
        pending_reason=pending,
        mark_stale_s=stale,
    )
    return "closed"
