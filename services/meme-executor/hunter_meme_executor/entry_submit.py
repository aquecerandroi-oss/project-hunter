"""The entry buy after its ``admitted`` row exists and the kill switch was
re-read: sign, send, record, and open the position on a confirmed fill. Moved
verbatim out of ``entries.py`` (T4.96, the 350-line budget) — the order of the
steps is unchanged; ``launch_submit.py`` is the launch lane's twin."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
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
from hunter_meme_executor.repo import insert_position
from hunter_meme_executor.send_path import record_send_result, submit_policy

if TYPE_CHECKING:
    from hunter_meme_executor.build import BuiltTrade
    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.repo import Candidate

__all__ = ["submit_entry_buy"]

logger = get_logger(__name__)


async def submit_entry_buy(
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
    ctx.event_exits_wake.set()  # T4.63: subscribe to this curve now, not on the next sync
