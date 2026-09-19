"""The exit loop: mark every open position honestly, fire the rules of §6, sell on
the curve — or say by name why it cannot.

- **The mark is what a full sell would net now**, fees and network fee included,
  from the curve read this second; without a readable curve the position keeps
  ``mark_reason`` and no number (never a fabricated mark).
- **Precedence** is ``hunter_risk_meme.exits.decide_exit``'s: the operator's
  ``sell_now`` (``sell_requested_at``, set through ``POST /meme/live/...``), the
  owner-enabled ``emergency_auto_close``, the creator dump (the sale **seen on
  the chain** by the radar's 15 s watch, ``creator_sold_seen_at`` of ``0038``, or
  the minute tape's ``creator_sold``), the venue leaving, target, trailing, time stop.
- **After ``complete = true`` the curve refuses trades.** A migrated position
  (``position.migrated`` or ``meme_tokens.migrated_at``) is routed to
  ``pumpswap_exit.handle_migrated_position`` (T4.29a: builds and sends a real
  PumpSwap ``sell``); a curve marked ``complete`` but not yet seen as migrated
  stays ``blocked:curve_complete_awaiting_migration`` until it is. A migrated
  mint whose canonical pool cannot be found is ``blocked:pumpswap_pool_not_found``
  — never sold quietly, never silently retried into the old blanket refusal.
- **A ``submitted_unconfirmed`` sell is reconciled before any new one** (VM5); a
  ``failed`` one is retried with backoff under a new ``:exit:{n}`` key, never re-signed.
- **T4.63 — two paths, one sell.** ``manage_position`` is the tick; ``sell_on_event``
  is the event runtime's door (``event_exits.py``) when ``decide_exit`` fired on a
  WS curve update. Both take the position's ``exit_lock``, re-read the row inside
  it (closed meanwhile ⇒ nothing) and go through the same ``route_exit`` → ``_sell``
  with a **fresh** ``CurveRead`` for the build — so an event exit and a tick exit for
  the same position never both send (CITIZEN, 18/09/2026, was lost between two ticks).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.db.session import role_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
)
from hunter_core.logging import get_logger
from hunter_meme_executor.build import FillRecord, build_sell, decode_fills, reserves_of
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.exit_common import (
    BACKOFF_S,
    LAMPORTS,
    close_ata_on_full_sell,
    exit_lock,
    exit_params,
    mark_blocked,
    mark_sol,
)
from hunter_meme_executor.exit_settle import close_from_fill, reconcile_sell
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.pumpswap_exit import handle_migrated_position
from hunter_meme_executor.repo import (
    OpenPosition,
    insert_order,
    latest_sell_order,
    open_position,
    open_positions,
    order_key,
    set_exit_intent,
    token_context,
    update_mark,
)
from hunter_meme_executor.send_path import (
    curve_fee_accounts,
    priority_fee_for,
    record_send_result,
    submit_policy,
)
from hunter_risk_meme import PositionForExit, decide_exit

__all__ = ["exits_once", "manage_position", "route_exit", "sell_on_event"]

logger = get_logger(__name__)


def _retry_due(position: OpenPosition, now: datetime) -> bool:
    intent = position.exit_intent or {}
    raw = intent.get("next_attempt_at")
    return raw is None or datetime.fromisoformat(str(raw)) <= now


async def _reload(ctx: ExecutorContext, position_id: str) -> OpenPosition | None:
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        return await open_position(session, position_id)


async def manage_position(ctx: ExecutorContext, position: OpenPosition, *, now: datetime) -> None:
    if ctx.signer is None:
        return
    async with exit_lock(ctx, position.id):
        fresh = await _reload(ctx, position.id)
        if fresh is None:
            return  # closed by the event path while this tick waited (T4.63)
        await _manage_locked(ctx, fresh, now=now)


async def _manage_locked(ctx: ExecutorContext, position: OpenPosition, *, now: datetime) -> None:
    try:
        read = await asyncio.to_thread(ctx.chain.curve, position.mint)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await update_mark(
                session,
                position.id,
                mark_sol=None,
                source="solana_rpc",
                reason=f"rpc_unreachable:{type(exc).__name__}",
                migrated=position.migrated,
                now=now,
            )
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        token = await token_context(session, position.mint)
    migrated = position.migrated or token.migrated_at is not None
    complete = read is not None and read.account.complete
    mark = None if read is None else mark_sol(ctx, reserves_of(read), position.tokens)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await update_mark(
            session,
            position.id,
            mark_sol=mark,
            source="solana_rpc",
            reason=None
            if mark is not None
            else ("curve_complete" if complete else "curve_not_found"),
            migrated=migrated,
            now=now,
        )
    peak = max(position.high_water_sol or Decimal(0), mark or Decimal(0))
    reason = decide_exit(
        PositionForExit(
            position_id=position.id,
            mint=position.mint,
            entry_at=position.entry_at,
            sol_spent=Decimal(position.sol_spent_lamports) / LAMPORTS,
            token_amount=max(1, position.tokens),
            peak_mark_sol=peak,
            migrated=migrated,
            curve_complete=complete,
        ),
        mark,
        now,
        exit_params(position.params, ctx.config.limits),
        sell_now=position.sell_requested_at is not None,
        creator_dump=position.creator_dump_seen(token.creator_sold),
        emergency_auto_close=(
            ctx.kill.effective is KillSwitchState.EMERGENCY and ctx.config.auto_close_on_emergency
        ),
    )
    if reason is None:
        return
    await route_exit(ctx, position, read, reason, migrated=migrated, complete=complete, now=now)


async def sell_on_event(
    ctx: ExecutorContext, position_id: str, reason: str, *, now: datetime
) -> None:
    """T4.63: ``decide_exit`` fired on a WS update — sell through the same door
    as the tick, under the same lock, with a fresh ``CurveRead`` for the build."""
    if ctx.signer is None:
        return
    async with exit_lock(ctx, position_id):
        position = await _reload(ctx, position_id)
        if position is None:
            return
        try:
            read = await asyncio.to_thread(ctx.chain.curve, position.mint)
        except Exception as exc:
            ctx.state.rpc_errors += 1
            logger.warning(
                "meme_live_exit_rpc_unreachable",
                position_id=position_id,
                error_type=type(exc).__name__,
            )
            return
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            token = await token_context(session, position.mint)
        migrated = position.migrated or token.migrated_at is not None
        complete = read is not None and read.account.complete
        await route_exit(ctx, position, read, reason, migrated=migrated, complete=complete, now=now)


async def route_exit(
    ctx: ExecutorContext,
    position: OpenPosition,
    read: CurveRead | None,
    reason: str,
    *,
    migrated: bool,
    complete: bool,
    now: datetime,
) -> None:
    """The venue, the pending attempt, the backoff — then one ``_sell``. Caller
    holds ``exit_lock`` and ``position`` was re-read under it."""
    if migrated:
        await handle_migrated_position(ctx, position, reason, now)
        return
    if complete or read is None:
        await mark_blocked(ctx, position, reason, "curve_complete_awaiting_migration", now)
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        latest = await latest_sell_order(session, position.proposal_id)
    if latest is not None and latest.status in ("admitted", "simulated", "submitted_unconfirmed"):
        await reconcile_sell(ctx, position, latest.client_order_id, latest.id)
        return
    if latest is not None and not _retry_due(position, now):
        return
    attempt = 1 if latest is None else latest.attempt + 1
    await _sell(ctx, position, read, reason, attempt, now)


async def _sell(
    ctx: ExecutorContext,
    position: OpenPosition,
    read: CurveRead,
    reason: str,
    attempt: int,
    now: datetime,
) -> None:
    assert ctx.signer is not None
    cfg, pubkey = ctx.config, ctx.signer.pubkey
    # T4.55: the fee of the moment (bounded, cached, the floor on failure), read
    # before the blockhash so the read never eats into the blockhash's validity.
    fee = await priority_fee_for(ctx, curve_fee_accounts(position.mint))
    try:
        account = await asyncio.to_thread(
            ctx.chain.token_account, pubkey, position.mint, read.token_program
        )
        global_account = await asyncio.to_thread(ctx.chain.global_account)
        blockhash, last_valid = await asyncio.to_thread(ctx.chain.blockhash)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning(
            "meme_live_exit_rpc_unreachable", position_id=position.id, error_type=type(exc).__name__
        )
        return
    tokens = min(position.tokens, account.amount)
    if tokens <= 0:
        await mark_blocked(ctx, position, reason, "reconciliation_mismatch:no_tokens_on_chain", now)
        return
    # T4.55: a sell tolerates more than a buy (5 %; 15 % on a creator dump / rug —
    # R56 §2, ``6003 TooLittleSolReceived`` at 1 %).
    try:
        built = build_sell(
            read,
            global_account,
            user=pubkey,
            token_amount=tokens,
            max_slippage_bps=cfg.send.exit_slippage_bps(reason),
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            compute_unit_limit=cfg.compute_unit_limit,
            compute_unit_price_micro_lamports=fee.micro_lamports,
            wallet_token_balance=account.amount,
            close_ata_on_full_sell=close_ata_on_full_sell(os.environ),
        )
    except Exception as exc:
        await mark_blocked(ctx, position, reason, f"build_failed:{type(exc).__name__}", now)
        return
    key = order_key(position.proposal_id, side="sell", attempt=attempt)
    intent = built.intent_json()
    intent["exit_reason"] = reason
    intent["priority_fee"] = fee.as_json(cfg.compute_unit_limit)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        order_id = await insert_order(
            session,
            proposal_id=position.proposal_id,
            side="sell",
            client_order_id=key,
            attempt=attempt,
            status="admitted",
            reason=None,
            intent=intent,
            admission={"exit_always_allowed": True, "reason": reason},
            now=now,
        )
        await set_exit_intent(
            session,
            position.id,
            {"reason": reason, "decided_at": now.isoformat(), "attempt": attempt, "order_key": key},
            now=now,
        )
    if order_id is None:
        return
    submitter = MemeSubmitter(
        rpc=ctx.chain.rpc,
        signer=ctx.signer,
        journal=ctx.journal,
        verify=built.verify,
        decode_fill=decode_fills,
        policy=submit_policy(cfg, ctx.chain.rpc),
        now=utcnow,
    )
    approval = ApprovedSubmission(
        key, now + timedelta(seconds=cfg.limits.reservation_ttl_s), built.message, last_valid
    )
    try:
        result = await asyncio.to_thread(submitter.submit, approval)
    except MemeLiveTradingDisabled:
        return
    await record_send_result(ctx, key, result)
    if result.signature:
        ctx.state.last_signature = result.signature
    logger.info(
        "meme_live_exit_settled", position_id=position.id, state=result.state, reason=result.reason
    )
    if result.state is SubmitState.CONFIRMED and isinstance(result.fill, FillRecord):
        await close_from_fill(ctx, position, order_id, result.fill, reason)
    elif result.state is SubmitState.FAILED:
        delay = BACKOFF_S[min(attempt - 1, len(BACKOFF_S) - 1)]
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await set_exit_intent(
                session,
                position.id,
                {
                    "reason": reason,
                    "decided_at": now.isoformat(),
                    "attempt": attempt,
                    "failed": result.reason,
                    "next_attempt_at": (utcnow() + timedelta(seconds=delay)).isoformat(),
                },
                now=utcnow(),
            )


async def exits_once(ctx: ExecutorContext) -> None:
    now = utcnow()
    ctx.state.last_exits_tick_at = now
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = await open_positions(session)
    for position in positions:
        await manage_position(ctx, position, now=now)
