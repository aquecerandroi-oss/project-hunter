"""The entry loop (1 s): approved live proposal → admission → quote → build →
verify → simulate → sign → send → confirm by ``TradeEvent`` → position.

One proposal, one attempt, one row. The order of refusals is the order of
cheapness and of authority: an approval past its TTL is refused before any
chain read (restart safety); the kill switch is re-read at the top of every
step; a chain read that fails **defers** (nothing written, the approval keeps
its TTL — §8.2 ``rpc_unreachable``); the engine's decision is written with every
check whether it approved or not — the conviction ladder (T4.61b/c,
``conviction.py``) is one of its inputs (check 26 and the ``conviction``
ceiling), never a verdict beside it; and only an approved decision reaches the
builder, whose bytes the submitter verifies and simulates before the key is
touched. The submitter runs in a thread: it is synchronous by design (T4.8) and
its journal writes block on this loop's own transactions (``journal_db``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_executor.admission import (
    AdmissionInputs,
    admit,
    curve_from,
    proposal_from,
    wallet_from,
)
from hunter_meme_executor.admission_context import build_admission_context
from hunter_meme_executor.auto_approve import auto_approve_once, reject_if_auto
from hunter_meme_executor.build import fee_bps
from hunter_meme_executor.chain import read_entry
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.conviction_read import conviction_for
from hunter_meme_executor.entry_submit import submit_entry_buy
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import (
    Candidate,
    insert_order,
    live_candidates,
    order_key,
    refuse_admitted_order,
)
from hunter_meme_executor.scope import (
    ScopeClaimRefused,
    buy_reserve_sol,
    claim_scope,
    lane_scope,
    requested_sol_of,
    scope_refusal,
)
from hunter_meme_executor.send_path import (
    build_entry_buy,
    curve_fee_accounts,
    priority_fee_for,
)
from hunter_meme_executor.treasury_inflow import ensure_anchor

__all__ = ["entries_once", "handle_candidate"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)


async def _refuse(
    ctx: ExecutorContext, candidate: Candidate, reason: str, admission: dict[str, object]
) -> None:
    now = utcnow()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        written = await insert_order(
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
        if written is None:  # T4.96: another pass owns this proposal's order; its word stands
            return
        await reject_if_auto(ctx, session, candidate, reason, now=now)
    ctx.state.record_refusal(reason)
    logger.warning(
        "meme_live_entry_refused", proposal_id=candidate.id, mint=candidate.mint, reason=reason
    )


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
    scope = await lane_scope(ctx, requested_sol=requested_sol_of(candidate.decision))
    if (late := scope_refusal(scope, cfg.limits.min_trade_sol)) is not None:
        await _refuse(ctx, candidate, *late)
        return
    pubkey = ctx.signer.pubkey
    try:
        # T4.55: the priority fee is read alongside the curve (bounded, cached,
        # the floor on failure) so the admission's fee check sees the real price.
        reads, fee = await asyncio.gather(
            asyncio.to_thread(read_entry, ctx.chain, candidate.mint, pubkey),
            priority_fee_for(ctx, curve_fee_accounts(candidate.mint)),
        )
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
    # T4.45: the rows, plus the two reads that keep a row the radar has not
    # written yet from becoming a refusal the market did not earn. Both fail
    # closed - a read that fails leaves the same ``None`` the table had.
    built = await build_admission_context(ctx, candidate.mint, reads.curve, now=now)
    positions, pending = built.positions, built.pending
    marks = sum((p.mark_sol or Decimal(0) for p in positions), Decimal(0))
    # T4.60: the anchor is net of today's treasury inflow, and the inflow is an
    # input of check 18 — neither is guessed when Postgres cannot answer.
    anchor = await ensure_anchor(ctx, now, Decimal(reads.wallet.lamports) / LAMPORTS + marks)
    inflow = ctx.treasury_inflow.inflow_sol
    if anchor is None or inflow is None:
        await _refuse(
            ctx, candidate, "day_anchor_unavailable", dict(ctx.treasury_inflow.describe())
        )
        return
    fees = fee_bps(global_account)
    reserve = buy_reserve_sol(cfg, fee, creates_ata=reads.creates_ata)  # T4.96: whole debit
    scope = None if scope is None else scope.for_buy(reserve, cfg.send.buy_slippage_bps())
    if (late := scope_refusal(scope, cfg.limits.min_trade_sol)) is not None:
        await _refuse(ctx, candidate, *late)
        return
    proposal = proposal_from(
        candidate,
        wallet_id=pubkey,
        limits=cfg.limits,
        priority_fee_sol=fee.fee_sol(cfg.compute_unit_limit),
        requested_cap_sol=None if scope is None else scope.requested_cap_sol,
    )
    # T4.61b/c: the size is a fraction of the cap decided by the evidence above
    # (``conviction.py``), handed to the engine as check 26 and the ``conviction``
    # ceiling. Off (the default) nothing is read and the size is flat.
    conviction = await conviction_for(
        ctx, built, reads.curve, proposal=proposal, limits=cfg.limits, now=now
    )
    inputs = AdmissionInputs(
        proposal=proposal,
        wallet=wallet_from(
            wallet_id=pubkey,
            now=now,
            balance=reads.wallet,
            positions=positions,
            pending=pending,
            anchor=anchor,
            limits=cfg.limits,
            treasury_inflow_today_sol=inflow,
            recent_losses=built.recent_losses,  # T4.78: check 28
        ),
        curve=curve_from(reads.curve),
        context=built.context,
        kill_switch=ctx.kill.inputs(),
        creates_ata=reads.creates_ata,
        curve_fee_pct=Decimal(fees.total) / Decimal(10_000),
        conviction=conviction.input,
    )
    decision = admit(inputs, cfg.limits, live_enabled=mode.live)
    if decision.checks and any(c.refusal == "daily_loss_cap_reached" for c in decision.checks):
        await ctx.kill.latch("daily_loss_cap_reached")
    admission = decision.to_jsonable()
    admission.update(built.extras)  # T4.45: what this admission read for itself
    admission["conviction"] = conviction.as_json()
    if scope is not None:
        admission["small_test"] = scope.as_json()
    if not decision.approved or decision.sizing is None:
        await _refuse(ctx, candidate, decision.first_refusal or "refused", admission)
        return
    try:
        blockhash, last_valid = await asyncio.to_thread(ctx.chain.blockhash)
        built = build_entry_buy(
            cfg,
            reads.curve,
            global_account,
            user=pubkey,
            budget_sol=decision.sizing.sol_final,
            fee=fee,
            blockhash=blockhash,
            last_valid_block_height=last_valid,
            creates_ata=reads.creates_ata,
        )
    except Exception as exc:
        await _refuse(ctx, candidate, f"build_failed:{type(exc).__name__}", admission)
        return
    intent = built.intent_json()
    intent["priority_fee"] = fee.as_json(cfg.compute_unit_limit)
    intent["sol_final"] = str(decision.sizing.sol_final)
    intent["conviction"] = conviction.as_json()
    intent["max_sol_cost_sol"] = str(Decimal(built.intent.sol_limit) / LAMPORTS)
    intent["scope_reserve_sol"] = str(Decimal(built.intent.sol_limit) / LAMPORTS + reserve)
    key = order_key(candidate.id, side="buy")
    try:
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await claim_scope(session, ctx, debit_sol=Decimal(intent["scope_reserve_sol"]))
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
    except ScopeClaimRefused as late:
        await _refuse(ctx, candidate, late.reason, {**admission, "small_test_claim": late.detail})
        return
    if order_id is None:
        return  # another pass already owns this key (idempotent on the proposal)
    # An approval is not a safe-conduct (§7, §9.5): the effective kill switch is
    # re-read between the admission and the signature, and a switch that moved in
    # between refuses the admitted row by name — nothing is signed, nothing is sent.
    await ctx.kill.refresh()
    if ctx.kill.blocks_entries:
        reason = "kill_switch_blocked_before_signing"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            refused_at = utcnow()
            await refuse_admitted_order(session, key, reason=reason, now=refused_at)
            await reject_if_auto(ctx, session, candidate, reason, now=refused_at)
        ctx.state.record_refusal(reason)
        logger.warning(
            "meme_live_entry_refused",
            proposal_id=candidate.id,
            mint=candidate.mint,
            reason=reason,
            kill_switch=ctx.kill.effective.value,
        )
        return
    await submit_entry_buy(ctx, candidate, built, key, order_id, now)


async def entries_once(ctx: ExecutorContext) -> None:
    now = utcnow()
    ctx.state.last_entries_tick_at = now
    await ctx.kill.refresh()
    # T4.28 stage 1: what the robot opens now is a live candidate of this same
    # tick — it goes through the admission below like any click would. Its clock
    # is read after the refresh above, so that wait counts against the proposal's
    # age too (T4.94: ``auto_approve_max_age_s``).
    await auto_approve_once(ctx, now=utcnow())
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await live_candidates(session, now=now)
    for candidate in candidates:
        ctx.state.entries_seen += 1
        # T4.52a: one sample per candidate, the first (and only, `live_candidates`
        # never re-offers a proposal with an order row) tick that sees it.
        ctx.state.pickup_lags.append((now - candidate.proposed_at).total_seconds())
        await handle_candidate(ctx, candidate, now=now)
