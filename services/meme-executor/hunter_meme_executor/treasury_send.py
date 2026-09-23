"""T4.54 — the money-moving half of the treasury top-up: build the swap
through Jupiter, **verify** it instruction by instruction
(``treasury_verify``), simulate it with the **balance invariant**
(``treasury_rules.check_simulated_balances``), sign, send and confirm — one
``meme_treasury_swaps`` row advanced in place, never a second one.

Nothing here is reached unless ``treasury.treasury_once`` has already
passed every gate (flag, live, signer, kill switch, floor, interval, daily
cap) and validated the quote against the request.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import decode_versioned_transaction
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    serialize_transaction,
)
from hunter_meme_executor import treasury_db
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_alt import account_keys_for
from hunter_meme_executor.treasury_rules import (
    USDC_MINT,
    TreasurySwapRefused,
    check_simulated_balances,
    classify_quote_refusal,
    classify_submitted,
)
from hunter_meme_executor.treasury_verify import SwapIntent, verify_swap_transaction

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["CONFIRM_WAIT_CAP_S", "attempt_swap", "simulated_balances"]

logger = get_logger(__name__)

LAMPORTS = Decimal(1_000_000_000)
USDC_UNIT = Decimal(1_000_000)
CONFIRM_WAIT_CAP_S = 20
"""The confirm loop blocks the kill-switch tick; past this the row stays
``submitted`` and ``treasury_reconcile`` settles it next tick (fix C)."""


def simulated_balances(accounts: Sequence[Mapping[str, Any] | None]) -> tuple[int, int] | None:
    """``(wallet_lamports, usdc_atoms)`` from a ``jsonParsed`` post-simulation
    ``accounts`` pair ``[wallet, usdc_ata]``; ``None`` when either is missing
    or not the shape expected — the caller refuses, never guesses."""
    if len(accounts) != 2 or accounts[0] is None or accounts[1] is None:
        return None
    try:
        lamports = int(accounts[0]["lamports"])
        parsed = cast(Mapping[str, Any], accounts[1]["data"])["parsed"]
        amount = int(str(parsed["info"]["tokenAmount"]["amount"]))
    except (KeyError, TypeError, ValueError):
        return None
    return lamports, amount


async def attempt_swap(
    ctx: ExecutorContext, *, usdc_atoms: int, quote: JupiterQuote, wallet_sol: Decimal
) -> None:
    assert ctx.signer is not None
    cfg, state = ctx.config, ctx.state
    usdc_in = Decimal(usdc_atoms) / USDC_UNIT
    sol_out_quoted = Decimal(quote.out_amount) / LAMPORTS
    refusal = classify_quote_refusal(quote)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        if refusal is not None:
            await treasury_db.insert_refused(
                session,
                reason="sol_below_floor",
                refusal=refusal,
                usdc_in=usdc_in,
                sol_out_quoted=sol_out_quoted,
                price_impact_pct=quote.price_impact_pct,
                slippage_bps=cfg.treasury_max_slippage_bps,
                wallet_sol_before=wallet_sol,
            )
            state.treasury_last_attempt_reason = refusal
            return
        swap_id = await treasury_db.insert_quoted(
            session,
            reason="sol_below_floor",
            usdc_in=usdc_in,
            sol_out_quoted=sol_out_quoted,
            price_impact_pct=quote.price_impact_pct,
            slippage_bps=cfg.treasury_max_slippage_bps,
            wallet_sol_before=wallet_sol,
        )
    intent = SwapIntent(
        wallet=ctx.signer.pubkey,
        usdc_atoms=usdc_atoms,
        min_quoted_out_lamports=int(quote.out_amount),
        max_slippage_bps=cfg.treasury_max_slippage_bps,
    )
    try:
        swap_tx = await asyncio.to_thread(
            ctx.treasury_client.swap, quote=quote, user_public_key=ctx.signer.pubkey
        )
        raw_tx = base64.b64decode(swap_tx.swap_transaction_b64)
        decoded = decode_versioned_transaction(raw_tx)
        # T4.83: Jupiter reaches the route's accounts — and the mint of the
        # ``CreateIdempotent`` (index 18 in the real capture) — through address
        # lookup tables. Resolve them here (IO, one ``getMultipleAccounts`` at
        # ``finalized``, off the loop) and hand the resolved list to the pure
        # verifier, which then checks a loaded address exactly like a static
        # one. A table that cannot be read refuses the attempt by name.
        account_keys = await asyncio.to_thread(account_keys_for, ctx.chain.rpc, decoded.message)
        verified = verify_swap_transaction(
            decoded.message, intent=intent, account_keys=account_keys
        )
    except TreasurySwapRefused as exc:
        await _refuse(ctx, swap_id, exc.reason)
        return
    except Exception as exc:
        await _refuse(ctx, swap_id, f"swap_build_failed:{type(exc).__name__}")
        logger.warning("meme_treasury_swap_build_failed", error_type=type(exc).__name__)
        return
    logger.info(
        "meme_treasury_swap_verified",
        route=verified.route_kind,
        in_amount=verified.in_amount,
        quoted_out=verified.quoted_out_amount,
        slippage_bps=verified.slippage_bps,
        priority_fee_lamports=verified.priority_fee_lamports,
    )
    await _simulate_sign_and_send(
        ctx,
        swap_id,
        message_bytes=decoded.message_bytes,
        raw_tx=raw_tx,
        wallet_sol_before=wallet_sol,
        usdc_atoms=usdc_atoms,
        min_out_lamports=int(quote.other_amount_threshold),
    )


async def _refuse(ctx: ExecutorContext, swap_id: uuid.UUID, refusal: str) -> None:
    ctx.state.treasury_last_attempt_reason = refusal
    logger.warning("meme_treasury_swap_refused", refusal=refusal)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_refused(session, swap_id, refusal=refusal)


async def _simulate_sign_and_send(
    ctx: ExecutorContext,
    swap_id: uuid.UUID,
    *,
    message_bytes: bytes,
    raw_tx: bytes,
    wallet_sol_before: Decimal,
    usdc_atoms: int,
    min_out_lamports: int,
) -> None:
    assert ctx.signer is not None
    wallet = ctx.signer.pubkey
    usdc_ata = associated_token_address(wallet, USDC_MINT, token_program=TOKEN_PROGRAM_ID)
    try:
        before_wallet = await asyncio.to_thread(ctx.chain.wallet, wallet)
        before_usdc = await asyncio.to_thread(
            ctx.chain.token_account, wallet, USDC_MINT, TOKEN_PROGRAM_ID
        )
        simulation = await asyncio.to_thread(
            ctx.chain.rpc.simulate_transaction,
            raw_tx,
            sig_verify=False,
            accounts=(wallet, usdc_ata),
        )
    except Exception as exc:
        await _refuse(ctx, swap_id, f"simulation_unreadable:{type(exc).__name__}")
        return
    if not simulation.ok:
        await _refuse(ctx, swap_id, f"simulation_failed:{str(simulation.err)[:120]}")
        return
    after = simulated_balances(simulation.accounts)
    if after is None:
        await _refuse(ctx, swap_id, "simulation_accounts_unreadable")
        return
    invariant = check_simulated_balances(
        usdc_before_atoms=before_usdc.amount if before_usdc.exists else 0,
        usdc_after_atoms=after[1],
        usdc_in_atoms=usdc_atoms,
        sol_before_lamports=before_wallet.lamports,
        sol_after_lamports=after[0],
        min_out_lamports=min_out_lamports,
    )
    if invariant is not None:
        await _refuse(ctx, swap_id, invariant)
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_simulated(session, swap_id)

    signature_bytes = ctx.signer.sign(message_bytes)
    signed_tx = serialize_transaction((signature_bytes,), message_bytes)
    try:
        signature = await asyncio.to_thread(ctx.chain.rpc.send_transaction, signed_tx)
    except Exception as exc:
        ctx.state.rpc_errors += 1
        ctx.state.treasury_last_attempt_reason = f"send_failed:{type(exc).__name__}"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await treasury_db.mark_failed(session, swap_id)
        logger.error("meme_treasury_send_failed", error_type=type(exc).__name__)
        return
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_submitted(session, swap_id, signature=signature)
    ctx.state.last_signature = signature

    verdict = await _confirm(ctx, signature)
    if verdict == "failed":
        ctx.state.treasury_last_attempt_reason = "on_chain_error"
        async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
            await treasury_db.mark_failed(session, swap_id)
        logger.error("meme_treasury_swap_failed_on_chain", signature=signature)
        return
    if verdict == "pending":
        # Fix C: still ``submitted`` — counted as spent, settled by the reconcile.
        ctx.state.treasury_last_attempt_reason = "confirm_pending_reconcile"
        logger.warning("meme_treasury_confirm_pending", signature=signature)
        return
    try:
        wallet_after = await asyncio.to_thread(ctx.chain.wallet, wallet)
        wallet_sol_after = Decimal(wallet_after.lamports) / LAMPORTS
    except Exception:
        wallet_sol_after = wallet_sol_before
    sol_out_filled = max(Decimal(0), wallet_sol_after - wallet_sol_before)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await treasury_db.mark_confirmed(
            session, swap_id, sol_out_filled=sol_out_filled, wallet_sol_after=wallet_sol_after
        )
    ctx.state.treasury_last_swap_at = utcnow()
    ctx.state.treasury_last_attempt_reason = f"ok:{signature}"
    logger.info(
        "meme_treasury_swap_confirmed",
        signature=signature,
        usdc_in=str(Decimal(usdc_atoms) / USDC_UNIT),
        sol_out_filled=str(sol_out_filled),
    )


async def _confirm(ctx: ExecutorContext, signature: str) -> str:
    """``confirmed`` / ``failed`` (errored on chain) / ``pending`` when the
    bounded wait runs out — the row then stays ``submitted`` for the
    reconcile, never ``failed`` on a timeout alone."""
    attempts = max(1, min(int(ctx.config.confirm_timeout_s), CONFIRM_WAIT_CAP_S))
    for _ in range(attempts):
        try:
            statuses = await asyncio.to_thread(ctx.chain.rpc.get_signature_statuses, [signature])
        except Exception:
            await asyncio.sleep(1.0)
            continue
        verdict = classify_submitted(statuses[0] if statuses else None, age_s=0.0)
        if verdict != "pending":
            return verdict
        await asyncio.sleep(1.0)
    return "pending"
