"""Settling a curve sell: reconciling a ``submitted_unconfirmed`` attempt by
signature (VM5) and closing the position with the chain's numbers.

Split out of ``exits.py`` in T4.63 for the 350-line budget; the code is the
same the tick ran before — the event path (``event_exits.py``) reaches it
through ``exits.route_exit`` and never on its own. T4.90 added
``no_tokens_on_chain``: an empty wallet asks the chain about our own
"expired" sell before the named block (curve and PumpSwap alike).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from hunter_core.logging import get_logger
from hunter_meme_executor.build import FillRecord, decode_fills
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.exit_common import is_launch_position, mark_blocked
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.repo import OpenPosition, close_position, expired_sell_orders
from hunter_meme_executor.send_path import record_failed_onchain_fee

__all__ = ["close_from_fill", "no_tokens_on_chain", "reconcile_sell"]

logger = get_logger(__name__)
NO_TOKENS = "reconciliation_mismatch:no_tokens_on_chain"
Reconcile = Callable[[ExecutorContext, OpenPosition, str, str], Awaitable[bool]]


async def no_tokens_on_chain(
    ctx: ExecutorContext,
    position: OpenPosition,
    reason: str,
    now: datetime,
    *,
    reconcile: Reconcile | None = None,
) -> None:
    """T4.90 — the wallet holds none of a position the ledger holds open. Only
    one ``failed`` row can hide a sell that landed: ``blockhash_expired_never_landed``
    (every other failure was refused or landed with an error, moving nothing).
    Each such sell of this position — not only the latest: a retry on a stale
    balance can fail on top of it (Astra) — is asked of the chain once more,
    never re-sent, never re-signed; a landed one closes the position with that
    transaction's fill. Anything else is the named block, as before.
    ``reconcile`` is the venue's (curve by default, PumpSwap passes its own)."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        expired = await expired_sell_orders(session, position.proposal_id)
    settle = reconcile or reconcile_sell
    for order in expired:
        if await settle(ctx, position, order.client_order_id, order.id):
            logger.warning(
                "meme_live_exit_expired_sell_had_landed", position_id=position.id, order_id=order.id
            )
            return
    await mark_blocked(ctx, position, reason, NO_TOKENS, now)


async def reconcile_sell(
    ctx: ExecutorContext, position: OpenPosition, key: str, order_id: str
) -> bool:
    """A sell with a signature and no settlement is asked of the chain — never
    re-sent, never re-signed — and closes the position if it landed (``True``
    when this call closed it)."""
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
        return await close_from_fill(ctx, position, order_id, result.fill, reason)
    return False


async def close_from_fill(
    ctx: ExecutorContext, position: OpenPosition, order_id: str, fill: FillRecord, reason: str
) -> bool:
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
    return closed
