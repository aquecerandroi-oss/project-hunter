"""Settling a PumpSwap sell: reconciling it by signature and closing the
position with the chain's numbers — ``exit_settle``'s curve twin.

Split out of ``pumpswap_exit.py`` in T4.90b so ``exit_settle.reconcile_order``
can read every sell with the decoder of the venue the ORDER was sent to, with
no import cycle (``pumpswap_exit`` sends; this module only reads and closes).
A replayed ``confirmed`` row brings its fill back as JSON: parsed into a typed
``StoredSellFill`` (venue-checked), never accepted as a loose dict.
"""

from __future__ import annotations

import asyncio

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.pumpswap_build import PumpSwapFillRecord, decode_pumpswap_fills
from hunter_meme_executor.repo import OpenPosition, close_position
from hunter_meme_executor.stored_fill import PUMPSWAP, StoredSellFill, parse_stored_sell_fill

__all__ = ["close_pumpswap", "reconcile_pumpswap_sell"]


async def reconcile_pumpswap_sell(
    ctx: ExecutorContext, position: OpenPosition, key: str, order_id: str
) -> bool:
    """Asked of the chain — never re-sent, never re-signed — and closed if it
    landed (``True`` when this call closed the position)."""
    submitter = MemeSubmitter(
        rpc=ctx.chain.rpc,
        signer=None,
        journal=ctx.journal,
        verify=lambda _raw: None,
        decode_fill=decode_pumpswap_fills,
        policy=SubmitPolicy(allow_send=False, cluster=ctx.config.cluster),
        now=utcnow,
    )
    result = await asyncio.to_thread(submitter.reconcile, key)
    if result is None or result.state is not SubmitState.CONFIRMED:
        return False
    fill = result.fill
    if not isinstance(fill, PumpSwapFillRecord):
        fill = parse_stored_sell_fill(fill, venue=PUMPSWAP)  # T4.90b: a replayed row
    if fill is None:
        return False
    reason = str((position.exit_intent or {}).get("reason", "reconciled"))
    return await close_pumpswap(ctx, position, order_id, fill, reason)


async def close_pumpswap(
    ctx: ExecutorContext,
    position: OpenPosition,
    order_id: str,
    fill: PumpSwapFillRecord | StoredSellFill,
    reason: str,
) -> bool:
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
    return closed
