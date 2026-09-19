"""Settling a curve sell: reconciling a ``submitted_unconfirmed`` attempt by
signature (VM5) and closing the position with the chain's numbers.

Split out of ``exits.py`` in T4.63 for the 350-line budget; the code is the
same the tick ran before — the event path (``event_exits.py``) reaches it
through ``exits.route_exit`` and never on its own.
"""

from __future__ import annotations

import asyncio

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from hunter_core.logging import get_logger
from hunter_meme_executor.build import FillRecord, decode_fills
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.exit_common import is_launch_position
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, close_position
from hunter_meme_executor.send_path import record_failed_onchain_fee

__all__ = ["close_from_fill", "reconcile_sell"]

logger = get_logger(__name__)


async def reconcile_sell(
    ctx: ExecutorContext, position: OpenPosition, key: str, order_id: str
) -> None:
    """A sell with a signature and no settlement is asked of the chain — never
    re-sent, never re-signed — and closes the position if it landed."""
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
    await record_failed_onchain_fee(ctx, key, result)  # T4.59: a landed error paid its fee
    if (
        result is not None
        and result.state is SubmitState.CONFIRMED
        and isinstance(result.fill, FillRecord)
    ):
        reason = str((position.exit_intent or {}).get("reason", "reconciled"))
        await close_from_fill(ctx, position, order_id, result.fill, reason)


async def close_from_fill(
    ctx: ExecutorContext, position: OpenPosition, order_id: str, fill: FillRecord, reason: str
) -> None:
    """Close with the decoded ``TradeEvent``: ``pnl = received − spent``, ``R = pnl / risk``."""
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
        if is_launch_position(position.params):
            ctx.launch.sells_total += 1  # T4.67b: the lane's own count
        ctx.state.blocked_exits.pop(position.id, None)
        if (fill.ata_rent_refund_lamports or 0) > 0:
            ctx.state.ata_closed += 1
