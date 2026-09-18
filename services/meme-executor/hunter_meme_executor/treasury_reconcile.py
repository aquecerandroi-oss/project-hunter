"""T4.54b fix C — settle every ``submitted`` treasury swap before any new
attempt is sized, the way ``main.reconcile_once`` settles
``submitted_unconfirmed`` trades: a restart, a crash between
``sendTransaction`` and ``mark_*``, or a confirm wait that ran out never
re-sends anything — the chain is asked what became of the signature.

``getSignatureStatuses`` (``searchTransactionHistory``) for every pending
signature in one call; each row then follows ``treasury_rules.classify_submitted``:
``confirmed`` → the wallet is re-read and the row gets ``sol_out_filled`` /
``wallet_sol_after``; ``failed`` → the row is marked so and stops counting
against the daily cap; ``pending`` → left alone, still counted as spent.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_meme_executor import treasury_db
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.treasury_rules import classify_submitted

if TYPE_CHECKING:
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["reconcile_once"]

logger = get_logger(__name__)

LAMPORTS = Decimal(1_000_000_000)


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
    padded = list(statuses)[: len(pending)]
    padded += [None] * (len(pending) - len(padded))
    for row, status in zip(pending, padded, strict=True):
        verdict = classify_submitted(status, age_s=(now - row.requested_at).total_seconds())
        if verdict == "pending":
            continue
        if verdict == "failed":
            async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
                await treasury_db.mark_failed(session, row.id)
            logger.warning("meme_treasury_reconciled", swap=str(row.id), state="failed")
            continue
        assert ctx.signer is not None
        try:
            wallet_after = await asyncio.to_thread(ctx.chain.wallet, ctx.signer.pubkey)
        except Exception as exc:
            # Landed, but the fill cannot be measured yet: next tick, same row.
            ctx.state.rpc_errors += 1
            logger.warning(
                "meme_treasury_reconcile_wallet_unreadable", error_type=type(exc).__name__
            )
            continue
        wallet_sol_after = Decimal(wallet_after.lamports) / LAMPORTS
        sol_out_filled = max(Decimal(0), wallet_sol_after - row.wallet_sol_before)
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
