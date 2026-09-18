"""The entry loop (1 s): approved live proposal → admission → quote → build →
verify → simulate → sign → send → confirm by ``TradeEvent`` → position.

One proposal, one attempt, one row. The order of refusals is the order of
cheapness and of authority: an approval past its TTL is refused before any
chain read (restart safety); the kill switch is re-read at the top of every
step; a chain read that fails **defers** (nothing written, the approval keeps
its TTL — §8.2 ``rpc_unreachable``); the engine's decision is written with every
check whether it approved or not; the conviction ladder (T4.61b,
``conviction.py``) sizes the request the engine judges and may refuse on top of
an approval (``entry_after_drop``, ``conviction_too_low``), never approve; and
only an approved decision reaches the builder, whose bytes the submitter
verifies and simulates before the key is touched. The submitter runs in a thread: it is synchronous by design (T4.8)
and its journal writes block on this loop's own transactions (``journal_db``).
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
from hunter_meme_executor.admission import (
    AdmissionInputs,
    admit,
    curve_from,
    proposal_from,
    wallet_from,
)
from hunter_meme_executor.admission_context import build_admission_context
from hunter_meme_executor.auto_approve import auto_approve_once, reject_if_auto
from hunter_meme_executor.build import BuiltTrade, FillRecord, decode_fills, fee_bps
from hunter_meme_executor.chain import read_entry
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.conviction_read import apply_ladder, conviction_for
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import (
    Candidate,
    insert_order,
    insert_position,
    live_candidates,
    order_key,
    refuse_admitted_order,
)
from hunter_meme_executor.scope import ScopeUse, read_scope_use, requested_sol_of
from hunter_meme_executor.send_path import (
    build_entry_buy,
    curve_fee_accounts,
    priority_fee_for,
    record_send_result,
    submit_policy,
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
        await reject_if_auto(ctx, session, candidate, reason, now=now)
    ctx.state.entries_refused += 1
    ctx.state.last_refusal = reason
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
    scope: ScopeUse | None = None
    small = mode.gates.small_test if mode.gates is not None else None
    if small is not None:
        # The written scope is two counters against the ledger (trades sent, SOL
        # taken) and a clamp: the last buy never overshoots ``max_total_sol``.
        requested = requested_sol_of(candidate.decision)
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            scope = await read_scope_use(session, small, requested_sol=requested)
        if scope.exhausted is not None:
            await _refuse(ctx, candidate, "small_test_scope_exhausted", scope.as_json())
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
    proposal = proposal_from(
        candidate,
        wallet_id=pubkey,
        limits=cfg.limits,
        priority_fee_sol=fee.fee_sol(cfg.compute_unit_limit),
        requested_cap_sol=None if scope is None else scope.requested_cap_sol,
    )
    # T4.61b: the size is a fraction of the cap decided by the evidence above
    # (``conviction.py``); the engine then sizes from that request, never above
    # it. Off (the default) the ladder is only written, and the size is flat.
    ladder = await conviction_for(
        ctx, built, reads.curve, proposal=proposal, limits=cfg.limits, now=now
    )
    inputs = AdmissionInputs(
        proposal=apply_ladder(proposal, ladder),
        wallet=wallet_from(
            wallet_id=pubkey,
            now=now,
            balance=reads.wallet,
            positions=positions,
            pending=pending,
            anchor=anchor,
            limits=cfg.limits,
            treasury_inflow_today_sol=inflow,
        ),
        curve=curve_from(reads.curve),
        context=built.context,
        kill_switch=ctx.kill.inputs(),
        creates_ata=reads.creates_ata,
        curve_fee_pct=Decimal(fees.total) / Decimal(10_000),
    )
    decision = admit(inputs, cfg.limits, live_enabled=mode.live)
    if decision.checks and any(c.refusal == "daily_loss_cap_reached" for c in decision.checks):
        await ctx.kill.latch("daily_loss_cap_reached")
    admission = decision.to_jsonable()
    admission.update(built.extras)  # T4.45: what this admission read for itself
    admission["conviction"] = ladder.as_json()
    if scope is not None:
        admission["small_test"] = scope.as_json()
    if not decision.approved or decision.sizing is None:
        await _refuse(ctx, candidate, decision.first_refusal or "refused", admission)
        return
    if ladder.refusal is not None:  # the engine's checks are on record; the ladder says no
        await _refuse(ctx, candidate, ladder.refusal, admission)
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
    intent["conviction"] = ladder.as_json()
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
            refused_at = utcnow()
            await refuse_admitted_order(session, key, reason=reason, now=refused_at)
            await reject_if_auto(ctx, session, candidate, reason, now=refused_at)
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
        policy=submit_policy(cfg, ctx.chain.rpc),
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
    await record_send_result(ctx, key, result)
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
    # T4.28 stage 1: what the robot opens now is a live candidate of this same
    # tick — it goes through the admission below like any click would.
    await auto_approve_once(ctx, now=now)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        candidates = await live_candidates(session, now=now)
    for candidate in candidates:
        ctx.state.entries_seen += 1
        # T4.52a: one sample per candidate, the first (and only, `live_candidates`
        # never re-offers a proposal with an order row) tick that sees it.
        ctx.state.pickup_lags.append((now - candidate.proposed_at).total_seconds())
        await handle_candidate(ctx, candidate, now=now)
