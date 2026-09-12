"""The entry loop (1 s): approved live proposal → admission → quote → build →
verify → simulate → sign → send → confirm by ``TradeEvent`` → position.

One proposal, one attempt, one row. The order of refusals is the order of
cheapness and of authority: an approval past its TTL is refused before any
chain read (restart safety); the kill switch is re-read at the top of every
step; a chain read that fails **defers** (nothing written, the approval keeps
its TTL — §8.2 ``rpc_unreachable``); the engine's decision is written with every
check whether it approved or not; and only an approved decision reaches the
builder, whose bytes the submitter verifies and simulates before the key is
touched. The submitter runs in a thread: it is synchronous by design (T4.8)
and its journal writes block on this loop's own transactions (``journal_db``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
    SubmitPolicy,
)
from hunter_core.logging import get_logger
from hunter_meme_executor.admission import (
    AdmissionInputs,
    admit,
    context_from,
    creates_ata,
    curve_from,
    day_start_utc,
    proposal_from,
    wallet_from,
)
from hunter_meme_executor.build import BuiltTrade, FillRecord, build_buy, decode_fills, fee_bps
from hunter_meme_executor.chain import CurveRead, TokenAccountRead, WalletRead
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import (
    Candidate,
    count_live_buys,
    insert_order,
    insert_position,
    live_candidates,
    open_positions,
    order_key,
    participation_used_sol,
    pending_attempts,
    refuse_admitted_order,
    token_context,
)

__all__ = ["entries_once", "handle_candidate"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class ChainReads:
    curve: CurveRead
    wallet: WalletRead
    token_account: TokenAccountRead
    creates_ata: bool


def _read_chain(ctx: ExecutorContext, mint: str, pubkey: str) -> ChainReads | None:
    curve = ctx.chain.curve(mint)
    if curve is None:
        return None
    wallet = ctx.chain.wallet(pubkey)
    account = ctx.chain.token_account(pubkey, mint, curve.token_program)
    return ChainReads(curve, wallet, account, creates_ata(account))


async def _refuse(
    ctx: ExecutorContext, candidate: Candidate, reason: str, admission: dict[str, object]
) -> None:
    now = utcnow()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await insert_order(
            session,
            proposal_id=candidate.id,
            side="buy",
            client_order_id=order_key(candidate.id, side="buy"),
            attempt=1,
            status="refused",
            reason=reason,
            intent={},
            admission=admission,
            now=now,
        )
    ctx.state.entries_refused += 1
    ctx.state.last_refusal = reason
    logger.warning(
        "meme_live_entry_refused", proposal_id=candidate.id, mint=candidate.mint, reason=reason
    )


async def _ensure_anchor(ctx: ExecutorContext, now: datetime, equity: Decimal) -> None:
    """Persist today's São Paulo midnight equity once; raise the peak when it grows."""
    start = day_start_utc(now)
    anchor = ctx.kill.anchor
    if anchor is None or anchor.day_start_utc != start:
        await ctx.kill.anchor_day(start, equity)
        return
    await ctx.kill.raise_peak(equity)


async def handle_candidate(ctx: ExecutorContext, candidate: Candidate, *, now: datetime) -> None:
    cfg, mode = ctx.config, ctx.mode
    if candidate.decided_at + timedelta(seconds=cfg.approval_ttl_s) < now:
        await _refuse(
            ctx, candidate, "approval_expired", {"decided_at": candidate.decided_at.isoformat()}
        )
        return
    if ctx.signer is None or not mode.live:
        await _refuse(ctx, candidate, "meme_live_disabled", {"live": mode.live})
        return
    if ctx.state.program_divergence is not None:  # T4.8b: never sign against an unknown program
        await _refuse(ctx, candidate, "program_upgraded", {"detail": ctx.state.program_divergence})
        return
    if cfg.small_test_max_trades is not None:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            done = await count_live_buys(session)
        if done >= cfg.small_test_max_trades:
            await _refuse(
                ctx,
                candidate,
                "small_test_scope_exhausted",
                {"max_trades": cfg.small_test_max_trades},
            )
            return
    pubkey = ctx.signer.pubkey
    try:
        reads = await asyncio.to_thread(_read_chain, ctx, candidate.mint, pubkey)
        global_account = await asyncio.to_thread(ctx.chain.global_account)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning(
            "meme_live_rpc_unreachable", proposal_id=candidate.id, error_type=type(exc).__name__
        )
        return
    if reads is None:
        await _refuse(ctx, candidate, "curve_not_found", {"mint": candidate.mint})
        return
    ctx.state.wallet_lamports, ctx.state.wallet_read_at = (
        reads.wallet.lamports,
        reads.wallet.observed_at,
    )
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        token = await token_context(session, candidate.mint)
        positions = await open_positions(session)
        pending = await pending_attempts(session)
        used = await participation_used_sol(session, candidate.mint, now=now)
    marks = sum((p.mark_sol or Decimal(0) for p in positions), Decimal(0))
    await _ensure_anchor(ctx, now, Decimal(reads.wallet.lamports) / LAMPORTS + marks)
    anchor = ctx.kill.anchor
    if anchor is None:
        await _refuse(ctx, candidate, "day_anchor_unavailable", {})
        return
    fees = fee_bps(global_account)
    inputs = AdmissionInputs(
        proposal=proposal_from(
            candidate, wallet_id=pubkey, limits=cfg.limits, priority_fee_sol=cfg.priority_fee_sol
        ),
        wallet=wallet_from(
            wallet_id=pubkey,
            now=now,
            balance=reads.wallet,
            positions=positions,
            pending=pending,
            anchor=anchor,
            limits=cfg.limits,
        ),
        curve=curve_from(reads.curve),
        context=context_from(candidate.mint, token, participation_used_sol=used, now=now),
        kill_switch=ctx.kill.inputs(),
        creates_ata=reads.creates_ata,
        curve_fee_pct=Decimal(fees.total) / Decimal(10_000),
    )
    decision = admit(inputs, cfg.limits, live_enabled=mode.live)
    if decision.checks and any(c.refusal == "daily_loss_cap_reached" for c in decision.checks):
        await ctx.kill.latch("daily_loss_cap_reached")
    admission = decision.to_jsonable()
    if not decision.approved or decision.sizing is None:
        await _refuse(ctx, candidate, decision.first_refusal or "refused", admission)
        return
    try:
        blockhash, last_valid = await asyncio.to_thread(ctx.chain.blockhash)
        built = build_buy(
            reads.curve,
            global_account,
            user=pubkey,
            budget_sol=decision.sizing.sol_final,
            max_slippage_bps=int(cfg.limits.max_slippage_pct * 10_000),
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            compute_unit_limit=cfg.compute_unit_limit,
            compute_unit_price_micro_lamports=cfg.compute_unit_price_micro_lamports,
            creates_ata=reads.creates_ata,
        )
    except Exception as exc:
        await _refuse(ctx, candidate, f"build_failed:{type(exc).__name__}", admission)
        return
    intent = built.intent_json()
    intent["sol_final"] = str(decision.sizing.sol_final)
    intent["max_sol_cost_sol"] = str(Decimal(built.intent.sol_limit) / LAMPORTS)
    key = order_key(candidate.id, side="buy")
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        order_id = await insert_order(
            session,
            proposal_id=candidate.id,
            side="buy",
            client_order_id=key,
            attempt=1,
            status="admitted",
            reason=None,
            intent=intent,
            admission=admission,
            now=now,
        )
    if order_id is None:
        return  # another pass already owns this key (idempotent on the proposal)
    # An approval is not a safe-conduct (§7, §9.5): the effective kill switch is
    # re-read between the admission and the signature, and a switch that moved in
    # between refuses the admitted row by name — nothing is signed, nothing is sent.
    await ctx.kill.refresh()
    if ctx.kill.blocks_entries:
        reason = "kill_switch_blocked_before_signing"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await refuse_admitted_order(session, key, reason=reason, now=utcnow())
        ctx.state.entries_refused += 1
        ctx.state.last_refusal = reason
        logger.warning(
            "meme_live_entry_refused",
            proposal_id=candidate.id,
            mint=candidate.mint,
            reason=reason,
            kill_switch=ctx.kill.effective.value,
        )
        return
    await _submit_and_record(ctx, candidate, built, key, order_id, now)


async def _submit_and_record(
    ctx: ExecutorContext,
    candidate: Candidate,
    built: BuiltTrade,
    key: str,
    order_id: str,
    now: datetime,
) -> None:
    cfg = ctx.config
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
        key,
        now + timedelta(seconds=cfg.limits.reservation_ttl_s),
        built.message,
        built.last_valid_block_height,
    )
    try:
        result = await asyncio.to_thread(submitter.submit, approval)
    except MemeLiveTradingDisabled:
        ctx.state.last_refusal = "meme_live_disabled"
        return
    if result.signature:
        ctx.state.last_signature = result.signature
    logger.info(
        "meme_live_entry_settled",
        proposal_id=candidate.id,
        state=result.state,
        reason=result.reason,
    )
    if result.state is not SubmitState.CONFIRMED or not isinstance(result.fill, FillRecord):
        return
    fill = result.fill
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await insert_position(
            session,
            proposal_id=candidate.id,
            entry_order_id=order_id,
            mint=candidate.mint,
            entry_at=fill.block_time or utcnow(),
            entry=fill.as_json(),
            tokens=fill.event.token_amount,
            sol_spent_lamports=fill.buy_total_lamports,
            params={
                "size_sol": str(candidate.decision.get("size_sol")),
                "target_x": str(candidate.decision.get("target_x")),
                "trailing_pct": str(candidate.decision.get("trailing_pct")),
                "max_hold_s": candidate.decision.get("max_hold_s"),
                "decided_by": candidate.decided_by,
            },
            now=utcnow(),
        )
    ctx.state.entries_confirmed += 1


async def entries_once(ctx: ExecutorContext) -> None:
    now = utcnow()
    ctx.state.last_entries_tick_at = now
    await ctx.kill.refresh()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await live_candidates(session, now=now)
    for candidate in candidates:
        ctx.state.entries_seen += 1
        await handle_candidate(ctx, candidate, now=now)
