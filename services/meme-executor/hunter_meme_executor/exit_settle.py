"""Settling a sell: reconciling a ``submitted_unconfirmed`` attempt by
signature (VM5) and closing the position with the chain's numbers.

Split out of ``exits.py`` in T4.63 for the 350-line budget; the code is the
same the tick ran before — the event path (``event_exits.py``) reaches it
through ``exits.route_exit`` and never on its own. T4.90 added
``no_tokens_on_chain``: an empty wallet asks the chain about our own
"expired" sell before the named block (curve and PumpSwap alike).

T4.90b (the T4.90 audit's three holes):

- **A confirmed sell closes its position, whoever saw it confirm.** The 30 s
  reconcile (``main.reconcile_once``) confirms rows and never closed them; a
  crash between the confirmation and the close did the same. The fill comes
  back from JSONB as a dict and is parsed into a typed ``StoredSellFill``
  (``stored_fill``), never trusted loose. ``repair_confirmed_sells`` sweeps
  every such orphan on the reconcile tick (the spot lane's
  ``confirmed_sells_still_pending``, T4.74-5); ``settle_latest`` makes both
  exit doors close from a confirmed sell instead of building another one.
- **The ORDER's venue picks the decoder** (``reconcile_order``), never the
  position's venue today: a curve sell sent before the migration is a curve
  sale, and ``decode_pumpswap_fills``' payer-delta fallback would otherwise
  book any landed transaction as a PumpSwap one.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.execution.meme.journal import SubmitState
from hunter_core.execution.meme.submit import MemeSubmitter, SubmitPolicy
from hunter_core.logging import get_logger
from hunter_meme_executor.build import FillRecord, decode_fills
from hunter_meme_executor.context import ExecutorContext
from hunter_meme_executor.exit_common import exit_lock, is_launch_position, mark_blocked
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.pumpswap_settle import close_pumpswap, reconcile_pumpswap_sell
from hunter_meme_executor.repo import (
    OpenPosition,
    OrderRow,
    close_position,
    expired_sell_orders,
    open_position,
)
from hunter_meme_executor.repo_positions import (
    ConfirmedSell,
    confirmed_sells,
    positions_with_confirmed_sell,
)
from hunter_meme_executor.send_path import record_failed_onchain_fee
from hunter_meme_executor.stored_fill import (
    CURVE,
    PUMPSWAP,
    StoredSellFill,
    order_venue,
    parse_stored_sell_fill,
)

__all__ = [
    "close_from_fill",
    "no_tokens_on_chain",
    "reconcile_order",
    "reconcile_sell",
    "repair_confirmed_sells",
    "settle_latest",
]

logger = get_logger(__name__)
NO_TOKENS = "reconciliation_mismatch:no_tokens_on_chain"
UNSETTLED = "reconciliation_mismatch:confirmed_sell_unsettled"
CLOSE_FAILED = "reconciliation_mismatch:confirmed_sell_close_failed"
PENDING = ("admitted", "simulated", "submitted_unconfirmed")


async def settle_latest(
    ctx: ExecutorContext, position: OpenPosition, latest: OrderRow, reason: str, now: datetime
) -> bool:
    """The newest sell decides whether another may be built (``False``) or
    not (``True``): a pending one is asked of the chain with its own venue's
    decoder; a confirmed one already sold the tokens — the position closes from
    its stored fill, and if it cannot, the block is named. Caller holds ``exit_lock``."""
    if latest.status in PENDING:
        await reconcile_order(ctx, position, latest)
        return True
    if latest.status != "confirmed":
        return False
    if not await _settle_confirmed(ctx, position, now):
        await mark_blocked(ctx, position, reason, UNSETTLED, now)
    return True


async def reconcile_order(ctx: ExecutorContext, position: OpenPosition, order: OrderRow) -> bool:
    """Reconcile ``order`` with the decoder of the venue it was SENT to."""
    if order_venue(order.intent) == PUMPSWAP:
        return await reconcile_pumpswap_sell(ctx, position, order.client_order_id, order.id)
    return await reconcile_sell(ctx, position, order.client_order_id, order.id)


async def no_tokens_on_chain(
    ctx: ExecutorContext, position: OpenPosition, reason: str, now: datetime
) -> None:
    """T4.90 — the wallet holds none of a position the ledger holds open.
    T4.90b: a sell already ``confirmed`` explains it — close from its fill.
    Otherwise only one ``failed`` row can hide a sell that landed:
    ``blockhash_expired_never_landed`` (every other failure was refused or
    landed with an error, moving nothing). Each such sell of this position — not
    only the latest: a retry on a stale balance can fail on top of it (Astra) —
    is asked of the chain once more with its own venue's decoder, never re-sent,
    never re-signed. Anything else is the named block, as before."""
    if await _settle_confirmed(ctx, position, now):
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        expired = await expired_sell_orders(session, position.proposal_id)
    for order in expired:
        if await reconcile_order(ctx, position, order):
            logger.warning(
                "meme_live_exit_expired_sell_had_landed", position_id=position.id, order_id=order.id
            )
            return
    await mark_blocked(ctx, position, reason, NO_TOKENS, now)


async def repair_confirmed_sells(ctx: ExecutorContext) -> None:
    """T4.90b — every open position a confirmed sell already emptied is closed
    from that sell's stored fill, under the position's lock, re-read inside it.
    Reads rows only: nothing is asked of the chain, nothing is sent. One
    position that cannot be settled never stops the others (review M1): a
    raise here would end ``reconcile_once`` and, through ``forever``, every loop."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        position_ids = await positions_with_confirmed_sell(session)
    for position_id in position_ids:
        try:
            async with exit_lock(ctx, position_id):
                async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                    position = await open_position(session, position_id)
                if position is not None and await _settle_confirmed(ctx, position, utcnow()):
                    logger.warning("meme_live_orphan_sell_settled", position_id=position_id)
        except Exception as exc:
            ctx.state.settle_errors += 1
            logger.warning(
                "meme_live_orphan_repair_failed",
                position_id=position_id,
                error_type=type(exc).__name__,
            )


async def _settle_confirmed(ctx: ExecutorContext, position: OpenPosition, now: datetime) -> bool:
    """``True`` when a confirmed sell decided the position: closed from its
    stored fill — or, when the close itself raises (a CHECK the chain's
    second-precision ``block_time`` cannot satisfy: ``exit_at > entry_at``), blocked
    by name. No exit time is invented to get past the database."""
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        sells = await confirmed_sells(session, position.proposal_id)
    for sell in sells:
        fill = _stored_fill_of(sell)
        if fill is None:
            continue
        reason = str(sell.intent.get("exit_reason") or "reconciled")
        close = close_pumpswap if fill.venue == PUMPSWAP else close_from_fill
        try:
            return await close(ctx, position, sell.order_id, fill, reason)
        except Exception as exc:
            ctx.state.settle_errors += 1
            logger.error(
                "meme_live_confirmed_sell_close_failed",
                position_id=position.id,
                order_id=sell.order_id,
                error_type=type(exc).__name__,
            )
            await _block_once(ctx, position, reason, f"{CLOSE_FAILED}:{type(exc).__name__}", now)
            return True
    return False


async def _block_once(
    ctx: ExecutorContext, position: OpenPosition, reason: str, block: str, now: datetime
) -> None:
    """The named block, written once — a retry every 30 s must not recount it."""
    if (position.exit_intent or {}).get("blocked") == block:
        ctx.state.blocked_exits.setdefault(position.id, block)
        return
    await mark_blocked(ctx, position, reason, block, now)


def _stored_fill_of(sell: ConfirmedSell) -> StoredSellFill | None:
    """The row's fill, typed, of this order's venue and of its own transaction."""
    fill = parse_stored_sell_fill(sell.fill, venue=order_venue(sell.intent))
    if fill is None or fill.signature != sell.tx_signature:
        logger.error("meme_live_confirmed_sell_fill_unusable", order_id=sell.order_id)
        return None
    return fill


async def reconcile_sell(
    ctx: ExecutorContext, position: OpenPosition, key: str, order_id: str
) -> bool:
    """A curve sell with a signature and no settlement is asked of the chain —
    never re-sent, never re-signed — and closes the position if it landed
    (``True`` when this call closed it)."""
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
    if result is None or result.state is not SubmitState.CONFIRMED:
        return False
    fill = result.fill
    if not isinstance(fill, FillRecord):
        fill = parse_stored_sell_fill(fill, venue=CURVE)  # T4.90b: a replayed row
    if fill is None:
        return False
    reason = str((position.exit_intent or {}).get("reason", "reconciled"))
    return await close_from_fill(ctx, position, order_id, fill, reason)


async def close_from_fill(
    ctx: ExecutorContext,
    position: OpenPosition,
    order_id: str,
    fill: FillRecord | StoredSellFill,
    reason: str,
) -> bool:
    """Close with the chain's numbers: ``pnl = received − spent``, ``R = pnl / risk``."""
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
