"""T4.67b — the launch buy after its ``admitted`` row exists and the kill switch
was re-read: sign, send, record, and open the ``launch`` position on a
confirmed fill. Moved verbatim out of ``launch_entries.py`` (T4.96, the
350-line budget) — the lane's order of steps is unchanged."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    MemeLiveTradingDisabled,
    MemeSubmitter,
)
from hunter_core.logging import get_logger
from hunter_meme_executor.build import FillRecord, decode_fills
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.launch_admission import launch_position_params
from hunter_meme_executor.launch_repo import buy_submitted_at
from hunter_meme_executor.launch_send import launch_submit_policy
from hunter_meme_executor.repo import insert_position
from hunter_meme_executor.send_path import record_send_result

if TYPE_CHECKING:
    from hunter_meme_executor.build import BuiltTrade
    from hunter_meme_executor.chain import CurveRead
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.launch_repo import LaunchCandidate

__all__ = ["submit_launch_buy"]

logger = get_logger(__name__)


async def submit_launch_buy(
    ctx: ExecutorContext,
    candidate: LaunchCandidate,
    built: BuiltTrade,
    *,
    key: str,
    order_id: str,
    curve: CurveRead,
    age_s: float,
) -> None:
    cfg, launch = ctx.config, ctx.config.launch
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
