"""Shared between ``exits.py`` (bonding curve), ``pumpswap_exit.py`` (T4.29a)
and ``event_exits.py`` (T4.63) — kept in its own module so none imports the
other.

T4.63 moved three things here so the tick and the event path decide with the
**same** arithmetic and never both send: ``exit_params`` (the rule-set's
numbers → ``ExitParams``), ``mark_sol`` (what a full sell nets now, from the
reserves of a curve read *or* of a WS notification — the same ``quote_sell``)
and ``exit_lock`` (one ``asyncio.Lock`` per position; whoever holds it re-reads
the row before selling, so a position the other path just closed is nothing).
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from hunter_core.db.session import role_session
from hunter_core.execution.meme.gates import parse_flag
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.quote import CurveReserves, quote_sell
from hunter_meme_executor.build import fee_bps
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, set_exit_intent
from hunter_risk_meme import ExitParams, MemeLimits

__all__ = [
    "BACKOFF_S",
    "ENV_CLOSE_ATA_ON_FULL_SELL",
    "LAMPORTS",
    "close_ata_on_full_sell",
    "exit_lock",
    "exit_params",
    "mark_blocked",
    "mark_sol",
]

logger = get_logger(__name__)
BACKOFF_S = (2, 4, 8, 16, 32, 60)
ENV_CLOSE_ATA_ON_FULL_SELL = "MEME_CLOSE_ATA_ON_FULL_SELL"
LAMPORTS = Decimal(1_000_000_000)


def close_ata_on_full_sell(env: Mapping[str, str]) -> bool:
    """T4.46 — OFF by default: a full sell closes the mint's ATA (rent back,
    R43) only when Everton sets ``MEME_CLOSE_ATA_ON_FULL_SELL=1`` in the VPS
    ``.env``. Review of 5bbae3ab: safe, but a systematic close error would park
    every position at simulation, and the first mainnet close is the only
    real test — a change to the real sell transaction is his flag."""
    return parse_flag(env.get(ENV_CLOSE_ATA_ON_FULL_SELL), default=False)


def exit_params(params: Mapping[str, Any], lim: MemeLimits) -> ExitParams:
    """The rule-set's ``target_x``/``trailing_pct``/``max_hold_s`` as the
    position carries them, the profile's numbers for whatever is missing."""
    trailing = Decimal(str(params.get("trailing_pct", lim.trailing_from_peak_pct * 100))) / 100
    return ExitParams(
        target_multiple=Decimal(str(params.get("target_x", lim.target_multiple))),
        trailing_from_peak_pct=trailing if 0 < trailing < 1 else lim.trailing_from_peak_pct,
        time_stop_s=int(params.get("max_hold_s", lim.time_stop_s)),
    )


def mark_sol(ctx: ExecutorContext, reserves: CurveReserves, tokens: int) -> Decimal | None:
    """Net SOL of selling everything now (fees and the network fee out), or
    ``None`` when the curve no longer trades. ``Decimal(0)`` when the proceeds
    do not even cover the fees — a number, because the curve *is* readable."""
    if reserves.complete or tokens <= 0:
        return None
    try:
        quote = quote_sell(
            reserves,
            tokens,
            fee_bps(ctx.chain.global_account()),
            max_slippage_bps=int(ctx.config.limits.max_slippage_pct * 10_000),
        )
    except ValueError:
        return Decimal(0)
    net = Decimal(quote.net_proceeds) / LAMPORTS - ctx.config.limits.network_fee_sol
    return max(Decimal(0), net)


def exit_lock(ctx: ExecutorContext, position_id: str) -> asyncio.Lock:
    """T4.63: the tick (``exits.manage_position``) and the event path
    (``exits.sell_on_event``) serialize on this — and re-read the row once
    inside, so the second one in finds the position closed and sends nothing."""
    return ctx.state.exit_locks.setdefault(position_id, asyncio.Lock())


async def mark_blocked(
    ctx: ExecutorContext, position: OpenPosition, reason: str, block: str, now: datetime
) -> None:
    """Record a named, non-silent exit refusal — never a quiet skip."""
    intent: dict[str, Any] = {"reason": reason, "decided_at": now.isoformat(), "blocked": block}
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await set_exit_intent(session, position.id, intent, now=now)
    ctx.state.blocked_exits[position.id] = block
    ctx.state.exits_blocked += 1
    logger.warning(
        "meme_live_exit_blocked",
        position_id=position.id,
        mint=position.mint,
        reason=reason,
        blocked=block,
    )
