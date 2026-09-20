"""T4.67b — the launch loop: a ``launch_v0/*`` proposal → the fast profile →
a prebuilt buy, in the second after the ``create`` (EXP-M18).

Runs only with ``MEME_LAUNCH_LANE=on`` **and** the live flag on: any other
combination is inert (no query, no row, ``launch_lane_mode`` says why). One
proposal, one attempt, one row — the same invariants as ``entries.py``: an
approval past its age is refused before any chain read, the kill switch is
re-read at the top of the loop and again between the admission and the
signature, every admission is written whether it approved or not, only an
approved decision reaches the builder, the buy's ``client_order_id`` is
``meme:{proposal_id}`` (idempotent on the proposal). What is different is
declared: the quote is read ``processed`` (the admission is told so), the
context comes from what exists at t+1 s (``launch_admission.py``), the
blockhash comes from the cache, the priority fee is lifted to the launch floor,
the buy tolerance is the launch's, and the proposal is **claimed** as ``live``
in the same transaction that writes the order (``launch_repo.py``).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
)
from hunter_core.logging import get_logger
from hunter_meme_executor.admission import AdmissionInputs, admit_launch, curve_from, wallet_from
from hunter_meme_executor.build import FillRecord, build_buy, decode_fills, fee_bps
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.launch_admission import (
    launch_context,
    launch_position_params,
    launch_proposal,
)
from hunter_meme_executor.launch_repo import (
    LaunchCandidate,
    buy_submitted_at,
    claim_launch_proposal,
    launch_candidates,
)
from hunter_meme_executor.launch_send import launch_priority_fee, launch_submit_policy
from hunter_meme_executor.repo import (
    insert_order,
    insert_position,
    order_key,
    participation_used_sol,
    pending_attempts,
    refuse_admitted_order,
    token_context,
)
from hunter_meme_executor.send_path import curve_fee_accounts, priority_fee_for, record_send_result
from hunter_meme_executor.spot_brake import brake_positions, spot_pending_intents
from hunter_meme_executor.treasury_inflow import ensure_anchor

__all__ = ["handle_launch_candidate", "launch_entries_once", "launch_inert_reason"]

logger = get_logger(__name__)
LAMPORTS = Decimal(1_000_000_000)
QUOTE_COMMITMENT = "processed"


def launch_inert_reason(ctx: ExecutorContext) -> str | None:
    """Why the lane does nothing even though the flag may read ``on``."""
    launch = ctx.config.launch
    if not launch.enabled:
        return f"lane_{launch.mode}"
    if ctx.signer is None or not ctx.mode.live:
        return "meme_live_disabled"
    return None


async def _refuse(
    ctx: ExecutorContext, candidate: LaunchCandidate, reason: str, admission: dict[str, Any]
) -> None:
    """Claim + refused row in one transaction; a claim that lost writes nothing."""
    now = utcnow()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        if not await claim_launch_proposal(session, candidate.id, now=now):
            ctx.launch.claim_lost_total += 1
            return
        await insert_order(
            session,
            proposal_id=candidate.id,
            side="buy",
            client_order_id=order_key(candidate.id, side="buy"),
            attempt=1,
            status="refused",
            reason=reason,
            intent={"lane": "launch"},
            admission=admission,
            now=now,
        )
    ctx.launch.record_refusal(reason)
    ctx.state.entries_refused += 1
    ctx.state.last_refusal = reason
    logger.warning(
        "meme_launch_entry_refused", proposal_id=candidate.id, mint=candidate.mint, reason=reason
    )


async def handle_launch_candidate(
    ctx: ExecutorContext, candidate: LaunchCandidate, *, now: datetime
) -> None:
    cfg, launch = ctx.config, ctx.config.launch
    ctx.launch.seen_total += 1
    age_s = (now - candidate.candidate.proposed_at).total_seconds()
    if age_s > launch.max_age_s:
        await _refuse(ctx, candidate, "launch_proposal_stale", {"proposal_age_s": age_s})
        return
    if ctx.signer is None or not ctx.mode.live:
        return  # inert: nothing written (``launch_inert_reason``)
    if ctx.state.program_divergence is not None:
        await _refuse(ctx, candidate, "program_upgraded", {"detail": ctx.state.program_divergence})
        return
    if ctx.kill.blocks_entries:
        await _refuse(ctx, candidate, "kill_switch_blocked", ctx.kill.describe())
        return
    pubkey = ctx.signer.pubkey
    try:
        # The quote (``processed``), the balance and the fee, in parallel: one
        # round trip, not three. ``Global`` is the minute cache.
        curve, wallet, choice = await asyncio.gather(
            asyncio.to_thread(ctx.chain.curve, candidate.mint, commitment=QUOTE_COMMITMENT),
            asyncio.to_thread(ctx.chain.wallet, pubkey),
            priority_fee_for(ctx, curve_fee_accounts(candidate.mint)),
        )
        global_account = await asyncio.to_thread(ctx.chain.global_account)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning(
            "meme_launch_rpc_unreachable", proposal_id=candidate.id, error_type=type(exc).__name__
        )
        return
    if curve is None:
        await _refuse(ctx, candidate, "curve_not_found", {"mint": candidate.mint})
        return
    ctx.state.wallet_lamports, ctx.state.wallet_read_at = wallet.lamports, wallet.observed_at
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        positions = await brake_positions(session)  # T4.74: memes + launch + spot, one brake
        pending = await pending_attempts(session)
        pending.extend(await spot_pending_intents(session))  # a spot buy in flight reserves too
        used = await participation_used_sol(session, candidate.mint, now=now)
    token = None
    try:  # the row is optional here (its own session: a failure must not poison the rest)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            token = await token_context(session, candidate.mint, now=now)
    except Exception as exc:
        logger.warning("meme_launch_token_context_failed", error_type=type(exc).__name__)
    marks = sum((p.mark_sol or Decimal(0) for p in positions), Decimal(0))
    anchor = await ensure_anchor(ctx, now, Decimal(wallet.lamports) / LAMPORTS + marks)
    inflow = ctx.treasury_inflow.inflow_sol
    if anchor is None or inflow is None:
        await _refuse(
            ctx, candidate, "day_anchor_unavailable", dict(ctx.treasury_inflow.describe())
        )
        return
    fee = launch_priority_fee(
        choice,
        launch_floor=launch.priority_floor_micro_lamports,
        max_sol=cfg.send.priority_fee_max_sol,
        compute_unit_limit=cfg.compute_unit_limit,
    )
    context, extras = launch_context(
        candidate, token, curve, global_account, participation_used_sol=used, now=now
    )
    fees = fee_bps(global_account)
    inputs = AdmissionInputs(
        proposal=launch_proposal(
            candidate,
            wallet_id=pubkey,
            limits=cfg.limits,
            launch=launch,
            priority_fee_sol=fee.fee_sol(cfg.compute_unit_limit),
        ),
        wallet=wallet_from(
            wallet_id=pubkey,
            now=now,
            balance=wallet,
            positions=positions,
            pending=pending,
            anchor=anchor,
            limits=cfg.limits,
            treasury_inflow_today_sol=inflow,
        ),
        curve=curve_from(curve),
        context=context,
        kill_switch=ctx.kill.inputs(),
        creates_ata=True,
        curve_fee_pct=Decimal(fees.total) / Decimal(10_000),
    )
    decision = admit_launch(
        inputs, cfg.limits, launch.profile(cfg.limits), live_enabled=ctx.mode.live
    )
    if any(c.refusal == "daily_loss_cap_reached" for c in decision.checks):
        await ctx.kill.latch("daily_loss_cap_reached")
    admission = decision.to_jsonable()
    admission["launch"] = {**extras, "config": launch.as_json(cfg.limits)}
    if not decision.approved or decision.sizing is None:
        await _refuse(ctx, candidate, decision.first_refusal or "refused", admission)
        return
    cached = await asyncio.to_thread(ctx.launch.blockhash.for_signing, ctx.chain, now=utcnow())
    if cached is None:
        await _refuse(ctx, candidate, "blockhash_unavailable", admission)
        return
    try:
        built = build_buy(
            curve,
            global_account,
            user=pubkey,
            budget_sol=decision.sizing.sol_final,
            max_slippage_bps=launch.buy_slippage_bps(),
            blockhash=cached.blockhash,
            last_valid_block_height=cached.last_valid_block_height,
            compute_unit_limit=cfg.compute_unit_limit,
            compute_unit_price_micro_lamports=fee.micro_lamports,
            creates_ata=True,
        )
    except Exception as exc:
        await _refuse(ctx, candidate, f"build_failed:{type(exc).__name__}", admission)
        return
    intent = built.intent_json()
    intent["lane"] = "launch"
    intent["priority_fee"] = fee.as_json(cfg.compute_unit_limit)
    intent["sol_final"] = str(decision.sizing.sol_final)
    intent["max_sol_cost_sol"] = str(Decimal(built.intent.sol_limit) / LAMPORTS)
    intent["blockhash_age_s"] = round(cached.age_s(utcnow()), 3)
    intent["skip_simulation"] = launch.skip_simulation
    key = order_key(candidate.id, side="buy")
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        if not await claim_launch_proposal(session, candidate.id, now=now):
            ctx.launch.claim_lost_total += 1
            return
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
    await ctx.kill.refresh()
    if ctx.kill.blocks_entries:
        reason = "kill_switch_blocked_before_signing"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await refuse_admitted_order(session, key, reason=reason, now=utcnow())
        ctx.launch.record_refusal(reason)
        ctx.state.entries_refused += 1
        ctx.state.last_refusal = reason
        return
    submitter = MemeSubmitter(
        rpc=ctx.chain.rpc,
        signer=ctx.signer,
        journal=ctx.journal,
        verify=built.verify,
        decode_fill=decode_fills,
        policy=launch_submit_policy(cfg, launch, ctx.chain.rpc),
        now=utcnow,
    )
    approval = ApprovedSubmission(
        key,
        utcnow() + timedelta(seconds=cfg.limits.reservation_ttl_s),
        built.message,
        built.last_valid_block_height,
    )
    try:
        result = await asyncio.to_thread(submitter.submit, approval)
    except MemeLiveTradingDisabled:
        ctx.state.last_refusal = "meme_live_disabled"
        return
    await record_send_result(ctx, key, result)
    if result.signature:
        ctx.state.last_signature = result.signature
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        submitted = await buy_submitted_at(session, key)
    if submitted is not None:
        ms = (submitted - candidate.candidate.proposed_at).total_seconds() * 1000
        ctx.launch.record_submit_latency_ms(ms)
    logger.info(
        "meme_launch_entry_settled",
        proposal_id=candidate.id,
        state=result.state,
        reason=result.reason,
        proposal_age_s=round(age_s, 3),
    )
    if result.state is not SubmitState.CONFIRMED or not isinstance(result.fill, FillRecord):
        if result.state is SubmitState.FAILED:
            ctx.launch.record_refusal(f"send_failed:{result.reason.split(':')[0]}")
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
            params=launch_position_params(candidate, curve),
            now=utcnow(),
        )
    ctx.state.entries_confirmed += 1
    ctx.launch.buys_total += 1
    ctx.event_exits_wake.set()  # subscribe to this curve now: the exits are seconds away


async def launch_entries_once(ctx: ExecutorContext) -> None:
    """One pass of the launch loop (``main.py``, ``config.loop_s`` with the
    proposal wake-up). Inert unless ``on`` + live; the blockhash cache is kept
    warm here so the buy signs without a fetch."""
    if launch_inert_reason(ctx) is not None:
        return
    now = utcnow()
    await asyncio.to_thread(ctx.launch.blockhash.refresh_if_stale, ctx.chain, now=now)
    await ctx.kill.refresh()
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await launch_candidates(session, now=now)
    for candidate in candidates:
        ctx.state.pickup_lags.append((now - candidate.candidate.proposed_at).total_seconds())
        await handle_launch_candidate(ctx, candidate, now=utcnow())
