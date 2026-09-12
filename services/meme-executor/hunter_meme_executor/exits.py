"""The exit loop: mark every open position honestly, fire the rules of §6, sell on
the curve — or say by name why it cannot.

- **The mark is what a full sell would net now**, fees and network fee included,
  from the curve read this second; without a readable curve the position keeps
  ``mark_reason`` and no number (never a fabricated mark).
- **Precedence** is ``hunter_risk_meme.exits.decide_exit``'s: the operator's
  ``sell_now`` (``sell_requested_at``, set through ``POST /meme/live/...``), the
  owner-enabled ``emergency_auto_close``, the creator dump (the radar's
  ``creator_sold``), the venue leaving (complete/migrated), target, trailing,
  time stop.
- **After ``complete = true`` the curve refuses trades** and the only exit is the
  PumpSwap pool, which T4.8 did not build: the intent is recorded as
  ``blocked:pumpswap_sell_not_implemented``, the position stays ``open`` with its
  last honest mark and the heartbeat carries it as a blocked exit — never sold quietly.
- **A ``submitted_unconfirmed`` sell is reconciled before any new one** (VM5); a
  ``failed`` one is retried with backoff under a new ``:exit:{n}`` key, never re-signed.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.db.session import role_session
from hunter_core.domain.enums import KillSwitchState
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
    SubmitPolicy,
)
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.quote import quote_sell
from hunter_meme_executor.build import FillRecord, build_sell, decode_fills, fee_bps, reserves_of
from hunter_meme_executor.chain import CurveRead
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import (
    OpenPosition,
    close_position,
    insert_order,
    latest_sell_order,
    open_positions,
    order_key,
    set_exit_intent,
    token_context,
    update_mark,
)
from hunter_risk_meme import ExitParams, PositionForExit, decide_exit

__all__ = ["exits_once", "manage_position"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
BACKOFF_S = (2, 4, 8, 16, 32, 60)


def _params(position: OpenPosition, ctx: ExecutorContext) -> ExitParams:
    p, lim = position.params, ctx.config.limits
    trailing = Decimal(str(p.get("trailing_pct", lim.trailing_from_peak_pct * 100))) / 100
    return ExitParams(
        target_multiple=Decimal(str(p.get("target_x", lim.target_multiple))),
        trailing_from_peak_pct=trailing if 0 < trailing < 1 else lim.trailing_from_peak_pct,
        time_stop_s=int(p.get("max_hold_s", lim.time_stop_s)),
    )


def _mark(ctx: ExecutorContext, read: CurveRead, tokens: int) -> Decimal | None:
    """Net SOL of selling everything now, or ``None`` when the curve no longer trades."""
    if read.account.complete or tokens <= 0:
        return None
    try:
        quote = quote_sell(
            reserves_of(read),
            tokens,
            fee_bps(ctx.chain.global_account()),
            max_slippage_bps=int(ctx.config.limits.max_slippage_pct * 10_000),
        )
    except ValueError:
        return Decimal(0)
    net = Decimal(quote.net_proceeds) / LAMPORTS - ctx.config.limits.network_fee_sol
    return max(Decimal(0), net)


async def _blocked(
    ctx: ExecutorContext, position: OpenPosition, reason: str, block: str, now: datetime
) -> None:
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


def _retry_due(position: OpenPosition, now: datetime) -> bool:
    intent = position.exit_intent or {}
    raw = intent.get("next_attempt_at")
    return raw is None or datetime.fromisoformat(str(raw)) <= now


async def manage_position(ctx: ExecutorContext, position: OpenPosition, *, now: datetime) -> None:
    if ctx.signer is None:
        return
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
    mark = None if read is None else _mark(ctx, read, position.tokens)
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
        _params(position, ctx),
        sell_now=position.sell_requested_at is not None,
        creator_dump=token.creator_sold is True,
        emergency_auto_close=(
            ctx.kill.effective is KillSwitchState.EMERGENCY and ctx.config.auto_close_on_emergency
        ),
    )
    if reason is None:
        return
    if migrated or complete or read is None:
        await _blocked(
            ctx,
            position,
            reason,
            "pumpswap_sell_not_implemented" if migrated else "curve_complete_awaiting_migration",
            now,
        )
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        latest = await latest_sell_order(session, position.proposal_id)
    if latest is not None and latest.status in ("admitted", "simulated", "submitted_unconfirmed"):
        await _reconcile_sell(ctx, position, latest.client_order_id, latest.id, now)
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
        await _blocked(ctx, position, reason, "reconciliation_mismatch:no_tokens_on_chain", now)
        return
    try:
        built = build_sell(
            read,
            global_account,
            user=pubkey,
            token_amount=tokens,
            max_slippage_bps=int(cfg.limits.max_slippage_pct * 10_000),
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            compute_unit_limit=cfg.compute_unit_limit,
            compute_unit_price_micro_lamports=cfg.compute_unit_price_micro_lamports,
        )
    except Exception as exc:
        await _blocked(ctx, position, reason, f"build_failed:{type(exc).__name__}", now)
        return
    key = order_key(position.proposal_id, side="sell", attempt=attempt)
    intent = built.intent_json()
    intent["exit_reason"] = reason
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
        policy=SubmitPolicy(
            allow_send=cfg.live and ctx.chain.rpc.allow_send,
            cluster=cfg.cluster,
            confirm_timeout_s=cfg.confirm_timeout_s,
        ),
        now=utcnow,
    )
    approval = ApprovedSubmission(
        key, now + timedelta(seconds=cfg.limits.reservation_ttl_s), built.message, last_valid
    )
    try:
        result = await asyncio.to_thread(submitter.submit, approval)
    except MemeLiveTradingDisabled:
        return
    if result.signature:
        ctx.state.last_signature = result.signature
    logger.info(
        "meme_live_exit_settled", position_id=position.id, state=result.state, reason=result.reason
    )
    if result.state is SubmitState.CONFIRMED and isinstance(result.fill, FillRecord):
        await _close(ctx, position, order_id, result.fill, reason)
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


async def _reconcile_sell(
    ctx: ExecutorContext, position: OpenPosition, key: str, order_id: str, now: datetime
) -> None:
    submitter = MemeSubmitter(
        rpc=ctx.chain.rpc,
        signer=None,
        journal=ctx.journal,
        verify=lambda _raw: None,
        decode_fill=decode_fills,
        policy=SubmitPolicy(allow_send=False, cluster=ctx.config.cluster),
        now=utcnow,
    )
    result = await asyncio.to_thread(submitter.reconcile, key)
    if (
        result is not None
        and result.state is SubmitState.CONFIRMED
        and isinstance(result.fill, FillRecord)
    ):
        reason = str((position.exit_intent or {}).get("reason", "reconciled"))
        await _close(ctx, position, order_id, result.fill, reason)


async def _close(
    ctx: ExecutorContext, position: OpenPosition, order_id: str, fill: FillRecord, reason: str
) -> None:
    payload = fill.as_json()
    payload["reason"] = reason
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        closed = await close_position(
            session,
            position.id,
            exit_order_id=order_id,
            exit_at=fill.block_time or utcnow(),
            exit_payload=payload,
            sol_received_lamports=fill.sell_net_lamports,
            sol_spent_lamports=position.sol_spent_lamports,
            initial_risk_sol=position.initial_risk_sol,
            now=utcnow(),
        )
    if closed:
        ctx.state.exits_confirmed += 1
        ctx.state.blocked_exits.pop(position.id, None)


async def exits_once(ctx: ExecutorContext) -> None:
    now = utcnow()
    ctx.state.last_exits_tick_at = now
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = await open_positions(session)
    for position in positions:
        await manage_position(ctx, position, now=now)
