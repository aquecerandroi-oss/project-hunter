"""Selling a migrated position on PumpSwap — the exit door ``exits.py`` used
to refuse by name (``pumpswap_sell_not_implemented``, T4.8/T4.11) now built
(T4.29a). Same journal, idempotency and kill-switch path as the curve exit
(``exits.py``'s ``_sell``/``_reconcile_sell``): verify → simulate → sign →
send, one client-order key per attempt, a ``submitted_unconfirmed`` sell
reconciled before any new one. The only two differences are the builder
(``pumpswap_build.build_pumpswap_sell``) and the refusal name when the
canonical pool does not exist yet: ``pumpswap_pool_not_found`` — never
silently falls back to the old blanket refusal.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
)
from hunter_core.logging import get_logger
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID, WSOL_MINT
from hunter_meme_executor.chain import PoolRead
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.exit_common import BACKOFF_S, mark_blocked
from hunter_meme_executor.exit_settle import no_tokens_on_chain, settle_latest
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.pumpswap_build import (
    PumpSwapFillRecord,
    build_pumpswap_sell,
    decode_pumpswap_fills,
)
from hunter_meme_executor.pumpswap_settle import close_pumpswap
from hunter_meme_executor.repo import (
    OpenPosition,
    insert_order,
    latest_sell_order,
    order_key,
    set_exit_intent,
)
from hunter_meme_executor.send_path import priority_fee_for, record_send_result, submit_policy

__all__ = ["handle_migrated_position"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)


async def handle_migrated_position(
    ctx: ExecutorContext, position: OpenPosition, reason: str, now: datetime
) -> None:
    assert ctx.signer is not None
    pool_read = await asyncio.to_thread(ctx.chain.pool, position.mint)
    if pool_read is None:
        await mark_blocked(ctx, position, reason, "pumpswap_pool_not_found", now)
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        latest = await latest_sell_order(session, position.proposal_id)
    # T4.90b: a pending sell is read with ITS venue's decoder (a curve sell sent
    # before the migration stays a curve sale); a confirmed one closes, never resold.
    if latest is not None and await settle_latest(ctx, position, latest, reason, now):
        return
    intent = position.exit_intent or {}
    raw_next = intent.get("next_attempt_at")
    retry_due = raw_next is None or datetime.fromisoformat(str(raw_next)) <= now
    if latest is not None and not retry_due:
        return
    attempt = 1 if latest is None else latest.attempt + 1
    await _sell(ctx, position, pool_read, reason, attempt, now)


async def _sell(
    ctx: ExecutorContext,
    position: OpenPosition,
    pool_read: PoolRead,
    reason: str,
    attempt: int,
    now: datetime,
) -> None:
    assert ctx.signer is not None
    cfg, pubkey = ctx.config, ctx.signer.pubkey
    fee = await priority_fee_for(ctx, (PUMPSWAP_PROGRAM_ID, pool_read.address))  # T4.55
    try:
        mint_account = await asyncio.to_thread(ctx.chain.rpc.get_account, position.mint)
        if mint_account is None:
            await mark_blocked(ctx, position, reason, "reconciliation_mismatch:mint_not_found", now)
            return
        base_token_program = mint_account.owner
        base_account = await asyncio.to_thread(
            ctx.chain.token_account, pubkey, position.mint, base_token_program
        )
        config = await asyncio.to_thread(ctx.chain.pumpswap_global_config)
        blockhash, last_valid = await asyncio.to_thread(ctx.chain.blockhash)
        wsol_account = await asyncio.to_thread(
            ctx.chain.token_account, pubkey, WSOL_MINT, TOKEN_PROGRAM_ID
        )
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning(
            "meme_live_pumpswap_exit_rpc_unreachable",
            position_id=position.id,
            error_type=type(exc).__name__,
        )
        return
    tokens = min(position.tokens, base_account.amount)
    if tokens <= 0:  # T4.90: our own "expired" sell may have landed — ask the chain first
        await no_tokens_on_chain(ctx, position, reason, now)
        return
    try:
        built = build_pumpswap_sell(
            pool_read,
            config,
            user=pubkey,
            base_token_program=base_token_program,
            token_amount=tokens,
            max_slippage_bps=cfg.send.exit_slippage_bps(reason),
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            compute_unit_limit=cfg.compute_unit_limit,
            compute_unit_price_micro_lamports=fee.micro_lamports,
            creates_wsol_ata=not wsol_account.exists,
        )
    except Exception as exc:
        await mark_blocked(ctx, position, reason, f"build_failed:{type(exc).__name__}", now)
        return
    key = order_key(position.proposal_id, side="sell", attempt=attempt)
    intent_json = built.intent_json()
    intent_json["exit_reason"] = reason
    intent_json["priority_fee"] = fee.as_json(cfg.compute_unit_limit)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        order_id = await insert_order(
            session,
            proposal_id=position.proposal_id,
            side="sell",
            client_order_id=key,
            attempt=attempt,
            status="admitted",
            reason=None,
            intent=intent_json,
            admission={"exit_always_allowed": True, "reason": reason, "venue": "pumpswap"},
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
        decode_fill=decode_pumpswap_fills,
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
        "meme_live_pumpswap_exit_settled",
        position_id=position.id,
        state=result.state,
        reason=result.reason,
    )
    if result.state is SubmitState.CONFIRMED and isinstance(result.fill, PumpSwapFillRecord):
        await close_pumpswap(ctx, position, order_id, result.fill, reason)
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
