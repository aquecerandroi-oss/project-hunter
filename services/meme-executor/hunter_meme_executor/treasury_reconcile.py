"""T4.54b fix C — settle every ``submitted`` treasury swap before any new
attempt is sized, the way ``main.reconcile_once`` settles
``submitted_unconfirmed`` trades: a restart, a crash between
``sendTransaction`` and ``mark_*``, or a confirm wait that ran out never
re-sends anything — the chain is asked what became of the signature.

``getSignatureStatuses`` (``searchTransactionHistory``) for every pending
signature in one call; each row then follows ``treasury_rules.classify_submitted``:
``confirmed`` → ``getTransaction``'s ``meta`` gives the fill of **this
signature** (T4.84) and the row gets ``sol_out_filled``/``wallet_sol_after``;
``failed`` → the row is marked so, and the log says **which** failure it was
(``failed:blockhash_expired_never_landed`` or ``failed:on_chain_error``), and
it stops counting against the daily cap; ``pending`` → left alone, still counted as spent.

T4.84: this is also where an **ambiguous** send lands — one whose RPC answer
was lost (``treasury_send``). Such a row carries its locally derived signature
and is settled here like any other; it is never marked ``failed`` on a guess.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT
from hunter_meme_executor import treasury_db
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_send_rules import fill_from_transaction
from hunter_meme_executor.treasury_rules import classify_submitted

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_meme_executor.context import ExecutorContext
    from hunter_meme_executor.treasury_db import SubmittedSwap

__all__ = ["EXPIRED_REASON", "ON_CHAIN_ERROR_REASON", "landed_sol_fill", "reconcile_once"]

logger = get_logger(__name__)

LAMPORTS = Decimal(1_000_000_000)
EXPIRED_REASON = "failed:blockhash_expired_never_landed"
"""Never seen by the chain past ``SUBMITTED_MAX_AGE_S`` — the blockhash died."""
ON_CHAIN_ERROR_REASON = "failed:on_chain_error"
"""Landed and reverted: the USDC was not spent, the fee was."""


async def reconcile_once(ctx: ExecutorContext) -> None:
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        pending = await treasury_db.submitted_swaps(session)
    if not pending:
        return
    try:
        statuses = await asyncio.to_thread(
            ctx.chain.rpc.get_signature_statuses, [row.signature for row in pending]
        )
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning("meme_treasury_reconcile_unreadable", error_type=type(exc).__name__)
        return
    now = utcnow()
    answered = list(statuses)
    if len(answered) != len(pending):
        # T4.84 (Astra, review of this diff): an answer that does not line up
        # with the signatures asked about says nothing about the ones it left
        # out. Padding them with ``None`` condemned a row older than
        # ``SUBMITTED_MAX_AGE_S`` on no evidence — and a swap that really
        # landed would then leave the daily cap and the inflow. An answer of
        # another size cannot be trusted to line up at all: nothing is settled
        # this tick, every row stays ``submitted`` (still counted), ask again.
        ctx.state.rpc_errors += 1
        logger.warning(
            "meme_treasury_reconcile_answer_mismatch",
            asked=len(pending),
            answered=len(answered),
        )
        return
    for row, status in zip(pending, answered, strict=True):
        verdict = classify_submitted(status, age_s=(now - row.requested_at).total_seconds())
        if verdict == "pending":
            continue
        if verdict == "failed":
            reason = EXPIRED_REASON if status is None else ON_CHAIN_ERROR_REASON
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                await treasury_db.mark_failed(session, row.id)
            logger.warning(
                "meme_treasury_reconciled",
                swap=str(row.id),
                state="failed",
                reason=reason,
                signature=row.signature,
            )
            continue
        await _settle_landed(ctx, row, now)


async def landed_sol_fill(ctx: ExecutorContext, signature: str) -> Decimal | None:
    """T4.84 — the SOL a landed USDC -> SOL swap really added to the wallet,
    read from **this signature**'s ``getTransaction`` meta (the fee payer's
    lamport delta, ``spot_send_rules.fill_from_transaction``), the way
    ``spot_reconcile._settle_landed`` reads it. The wallet is shared with the
    ``spot/1`` lane and the meme lane, so a live balance delta would book
    their SOL (or their spend) as this swap's fill — and that number is the
    treasury inflow the daily-loss brake subtracts (§16.3).

    ``None`` when the meta is not served yet, unreadable, or contradicts the
    swap's own direction: the caller leaves the row ``submitted`` (counted
    against the daily cap) for the next reconcile tick — never a fill of zero,
    never a guess. Used by the confirm of ``treasury_send`` and by the
    reconcile alike, so both settle a landed swap with the same number.
    """
    assert ctx.signer is not None
    try:
        tx = await asyncio.to_thread(ctx.chain.rpc.get_transaction, signature)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        logger.warning(
            "meme_treasury_fill_unreadable", signature=signature, error_type=type(exc).__name__
        )
        return None
    landed = (
        None
        if tx is None
        else fill_from_transaction(tx, wallet=ctx.signer.pubkey, mint=WRAPPED_SOL_MINT)
    )
    if landed is None:
        logger.warning("meme_treasury_fill_not_visible", signature=signature)
        return None
    if landed.sol_delta_lamports <= 0:
        # A USDC -> SOL swap that landed cannot leave the wallet with less SOL
        # than it had, fees included. Left for a human; the row keeps counting
        # against the cap at its quoted size (the conservative side).
        logger.error(
            "meme_treasury_fill_inconsistent",
            signature=signature,
            sol_delta_lamports=landed.sol_delta_lamports,
        )
        return None
    return Decimal(landed.sol_delta_lamports) / LAMPORTS


async def _settle_landed(ctx: ExecutorContext, row: SubmittedSwap, now: datetime) -> None:
    sol_out_filled = await landed_sol_fill(ctx, row.signature)
    if sol_out_filled is None:
        return
    wallet_sol_after = row.wallet_sol_before + sol_out_filled
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_confirmed(
            session, row.id, sol_out_filled=sol_out_filled, wallet_sol_after=wallet_sol_after
        )
    ctx.state.treasury_last_swap_at = now
    logger.info(
        "meme_treasury_reconciled",
        swap=str(row.id),
        state="confirmed",
        signature=row.signature,
        sol_out_filled=str(sol_out_filled),
    )
