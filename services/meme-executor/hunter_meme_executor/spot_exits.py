"""T4.74-5 — the exits loop of the ``spot/1`` desk (design §4): every
``SPOT1_MARK_S`` each open position is **marked** by the Jupiter quote of its
whole lot (token → SOL, 50 bps — "what a full sell yields now"), then the pure
``decide_exit`` says ``emergency`` > ``sell_requested`` > ``stop`` > ``target``
> ``time`` or nothing, and a reason becomes one ``spot_orders`` row (``sell``,
attempt ``n``) → ``spot_leg`` (the only signature) → ``close_position`` with
the chain's lamports, ``exit->>'reason'`` set for ``closed_stats``.

A quote that fails keeps the old mark (``mark_reason = quote_failed:<type>``);
three in a row publish ``mark_stale_s``. A sell that fails backs off
``(2,4,8,16,32,60) s``, re-quotes on the next attempt, uses the panic
tolerance from the 3rd attempt (from the 1st for ``stop``/``emergency``), and
after ``MAX_EXIT_ATTEMPTS`` the position is ``blocked_exits[id]`` — still
marked, sold by hand (``meme_spot_swap.py`` + ``spot_desk_markets.py
--close-manual``). A refusal that is transient (Jupiter/RPC did not answer)
never spends that budget, but ``STUCK_AFTER_TRANSIENT`` of them in a row
publish ``stuck_exits[id]`` in the heartbeat (T4.74-7, A2). A sell left
``submitted_unconfirmed`` pins ``exit_order_id`` on the position: nothing else
is sold until ``spot_reconcile`` settles it by signature.

**The loop runs whenever the executor is live with its signer, whatever
``SPOT1_ENABLED`` says** (T4.74-7, A1): the flag gates entries only — a
position the reconcile opened after the flag went off is still marked and
sold (RISK_ENGINE §10). Inert without live or signer; a tick that raises is
counted, never propagated.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_meme_executor import spot_repo
from hunter_meme_executor.exit_common import exit_lock
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_config import SPOT_DECIDED_BY, SpotConfig
from hunter_meme_executor.spot_entries import spot_config_of, spot_stats_of
from hunter_meme_executor.spot_exit_repo import (
    PENDING_EXIT_STATUS,
    TRANSIENT_EXIT_REFUSALS,
    clear_exit_pending,
    sell_attempts,
    set_exit_pending,
)
from hunter_meme_executor.spot_exit_rules import (
    MAX_EXIT_ATTEMPTS,
    backoff_s,
    decide_exit,
    r_now,
    slippage_for,
)
from hunter_meme_executor.spot_repo import SpotPosition, insert_order, open_spot_positions, set_mark
from hunter_meme_executor.spot_send import spot_leg
from hunter_meme_executor.spot_send_rules import spot_client_order_id
from hunter_meme_executor.spot_settle import settle_closed
from hunter_meme_executor.spot_stats import SpotStats
from hunter_risk_meme.spot_profile import SPOT_LANE

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = [
    "MARK_SLIPPAGE_BPS",
    "STALE_AFTER_FAILURES",
    "STUCK_AFTER_TRANSIENT",
    "exits_active",
    "manage_position",
    "spot_exits_once",
]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
MARK_SLIPPAGE_BPS = 50
"""Design §4: the mark is the quote of the whole lot at the exit's own tolerance."""
STALE_AFTER_FAILURES = 3
STUCK_AFTER_TRANSIENT = 30
"""Consecutive transient sell refusals after which the position is published
as ``stuck_exits[id]`` (≈ 30 min at the 60 s rung) and logged once per 30."""


def exits_active(cfg: SpotConfig) -> bool:
    """Exits need the live executor and its signer — never ``SPOT1_ENABLED``
    (that flag gates entries only; ``main.py`` creates the task by this)."""
    return cfg.live and cfg.signer_present


async def spot_exits_once(ctx: ExecutorContext) -> None:
    """One pass (``main.py``, ``SPOT1_MARK_S``): one read of the open positions,
    no quote without one; nothing at all unless live with a signer."""
    cfg = spot_config_of(ctx)
    if not exits_active(cfg) or ctx.signer is None:
        return
    stats = spot_stats_of(ctx)
    now = utcnow()
    stats.last_exits_tick_at = now
    try:
        await _tick(ctx, cfg, stats, now)
    except Exception as exc:
        stats.tick_failures += 1
        ctx.state.rpc_errors += 1
        logger.exception("meme_spot_exits_tick_failed", error_type=type(exc).__name__)


async def _tick(ctx: ExecutorContext, cfg: SpotConfig, stats: SpotStats, now: datetime) -> None:
    await ctx.kill.refresh()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = await open_spot_positions(session)
    for position in positions:
        lock = exit_lock(ctx, position.id)
        if lock.locked():
            continue  # another path holds it (the reconcile settling this very one)
        async with lock:
            await manage_position(ctx, cfg, stats, position, now=now)


async def manage_position(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    stats: SpotStats,
    position: SpotPosition,
    *,
    now: datetime,
) -> None:
    mark = await _mark(ctx, stats, position, now)
    if _exit_pending(position):
        return  # a sell is on the chain; the reconcile owns this position
    if position.id in stats.blocked_exits:
        return  # design §4: marked, never re-sold by the loop
    until = stats.exit_backoff_until.get(position.id)
    if until is not None and now < until:
        return
    reason = decide_exit(
        position,
        mark,
        now,
        ctx.kill.effective,
        auto_close_on_emergency=ctx.config.auto_close_on_emergency,
    )
    if reason is None:
        return
    await _sell(ctx, cfg, stats, position, reason, mark, now=now)


def _exit_pending(position: SpotPosition) -> bool:
    intent = position.exit_intent or {}
    return intent.get("status") == PENDING_EXIT_STATUS


async def _mark(
    ctx: ExecutorContext, stats: SpotStats, position: SpotPosition, now: datetime
) -> Decimal | None:
    """The quote of the whole lot → ``set_mark``; on failure the old mark stays
    **on the row** (observability), the reason is written, the streak counted —
    and the rules get ``None``: a stop or a target is never decided on a
    number the market did not just confirm (Astra, T4.74-5 review); the
    ``time``/``emergency``/``sell_requested`` exits need no mark."""
    try:
        quote = await asyncio.to_thread(
            ctx.treasury_client.quote,
            input_mint=position.mint,
            output_mint=WRAPPED_SOL_MINT,
            amount=position.tokens,
            slippage_bps=MARK_SLIPPAGE_BPS,
        )
        mark = Decimal(int(quote.out_amount)) / LAMPORTS
        if mark <= 0:
            raise ValueError("quote_out_not_positive")
    except Exception as exc:
        failures = stats.mark_failures.get(position.id, 0) + 1
        stats.mark_failures[position.id] = failures
        stats.mark_ok_at.setdefault(position.id, now)
        reason = f"quote_failed:{type(exc).__name__}"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await set_mark(session, position.id, mark_sol=None, reason=reason, now=now)
        if failures == STALE_AFTER_FAILURES:
            logger.warning("meme_spot_mark_stale", position_id=position.id, failures=failures)
        return None
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await set_mark(session, position.id, mark_sol=mark, reason=None, now=now)
    stats.mark_failures.pop(position.id, None)
    stats.mark_ok_at[position.id] = now
    return mark


async def _sell(
    ctx: ExecutorContext,
    cfg: SpotConfig,
    stats: SpotStats,
    position: SpotPosition,
    reason: str,
    mark: Decimal | None,
    *,
    now: datetime,
) -> None:
    attempts = stats.exit_attempts.get(position.id)
    if attempts is None:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            seeded = await sell_attempts(session, position.id)
        attempts = seeded.attempts
        stats.exit_hard_failures[position.id] = seeded.hard_failures
    if stats.exit_hard_failures.get(position.id, 0) >= MAX_EXIT_ATTEMPTS:
        _block(stats, position.id, reason, attempts)
        return
    attempt = attempts + 1
    stats.exit_attempts[position.id] = attempt
    slippage = slippage_for(
        attempt, reason, normal_bps=cfg.exit_slippage_bps, panic_bps=cfg.panic_slippage_bps
    )
    r = r_now(position, mark)
    intent: dict[str, Any] = {
        "lane": SPOT_LANE,
        "side": "sell",
        "input_mint": position.mint,
        "output_mint": WRAPPED_SOL_MINT,
        "amount_atoms": position.tokens,
        "slippage_bps": slippage,
        "max_priority_fee_lamports": cfg.priority_fee_max_lamports,
        "reason": reason,
        "attempt": attempt,
        "mark_sol": None if mark is None else str(mark),
        "r_now": None if r is None else str(r),
        "market_symbol": position.market_symbol,
    }
    admission = {
        "decided_by": SPOT_DECIDED_BY,
        "exit_reason": reason,
        "attempt": attempt,
        **ctx.kill.describe(),
    }
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        order_id = await insert_order(
            session,
            signal_id=position.signal_id,
            market_symbol=position.market_symbol,
            mint=position.mint,
            side="sell",
            client_order_id=spot_client_order_id(position.id, side="sell", attempt=attempt),
            attempt=attempt,
            status="admitted",
            reason=None,
            intent=intent,
            admission=admission,
            quote=None,
            position_id=position.id,
            now=now,
        )
    if order_id is None:
        return  # that attempt's key already exists (a restart mid-attempt): next tick, n + 1
    # The position names its in-flight sell **before** the leg: whatever the
    # process dies between, the reconcile finds the pair (order, position) by
    # ``exit_order_id`` and settles it from the row — never a second sell.
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        taken = await set_exit_pending(
            session, position.id, order_id=order_id, reason=reason, attempt=attempt, now=now
        )
    if not taken:
        # The row is no longer ``open`` (closed by the reconcile or by
        # ``--close-manual`` since the read): nothing is sold on its behalf —
        # a second lot of the same mint in the wallet is not this position.
        logger.warning("meme_spot_exit_position_gone", position_id=position.id, order_id=order_id)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await spot_repo.mark_refused(session, order_id, reason="position_not_open", now=now)
        return
    logger.info(
        "meme_spot_exit_decided",
        position_id=position.id,
        market=position.market_symbol,
        reason=reason,
        attempt=attempt,
        slippage_bps=slippage,
        r_now=intent["r_now"],
    )
    result = await spot_leg(
        ctx,
        order_id=order_id,
        input_mint=position.mint,
        output_mint=WRAPPED_SOL_MINT,
        amount_atoms=position.tokens,
        slippage_bps=slippage,
        max_priority_fee_lamports=cfg.priority_fee_max_lamports,
    )
    if result.signature:
        stats.last_signature = result.signature
    if result.status == "confirmed":
        exit_payload = {
            "reason": reason,
            "attempt": attempt,
            "order_id": order_id,
            "signature": result.signature,
            "slippage_bps": slippage,
            "filled_lamports": result.filled_atoms,
            "sol_delta_lamports": result.sol_delta_lamports,
            "priority_fee_lamports": result.priority_fee_lamports,
            "mark_sol_at_decision": intent["mark_sol"],
            "r_now_at_decision": intent["r_now"],
            "quoted_out_lamports": None if result.quote is None else int(result.quote.out_amount),
        }
        await settle_closed(
            ctx, cfg, stats, position, order_id=order_id, exit_payload=exit_payload, now=utcnow()
        )
        return
    if result.status == "submitted_unconfirmed":
        logger.warning(
            "meme_spot_exit_unconfirmed", position_id=position.id, order_id=order_id, reason=reason
        )
        return  # the marker stays; ``spot_reconcile`` settles it by signature
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        outcome = f"{result.status}:{result.reason or ''}"
        await clear_exit_pending(session, position.id, order_id=order_id, outcome=outcome, now=now)
    stats.exit_backoff_until[position.id] = now + timedelta(seconds=backoff_s(attempt))
    transient = (result.reason or "").startswith(TRANSIENT_EXIT_REFUSALS)
    hard = stats.exit_hard_failures.get(position.id, 0) + (0 if transient else 1)
    stats.exit_hard_failures[position.id] = hard
    streak = stats.record_transient_refusal(
        position.id, result.reason or "", transient=transient, stuck_after=STUCK_AFTER_TRANSIENT
    )
    if streak and streak % STUCK_AFTER_TRANSIENT == 0:  # rate-limited: once per 30
        logger.error(
            "meme_spot_exit_stuck", position_id=position.id, streak=streak, reason=result.reason
        )
    logger.warning(
        "meme_spot_exit_failed",
        position_id=position.id,
        attempt=attempt,
        status=result.status,
        reason=result.reason,
        transient=transient,
        hard_failures=hard,
        transient_streak=streak,
    )
    if hard >= MAX_EXIT_ATTEMPTS:
        _block(stats, position.id, reason, attempt)


def _block(stats: SpotStats, position_id: str, reason: str, attempts: int) -> None:
    if position_id not in stats.blocked_exits:
        logger.error("meme_spot_exit_blocked", position_id=position_id, attempts=attempts)
    stats.blocked_exits[position_id] = reason
