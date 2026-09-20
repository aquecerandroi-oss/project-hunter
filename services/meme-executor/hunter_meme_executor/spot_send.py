"""T4.74-4 — ``spot_leg``: the one primitive of the ``spot/1`` desk that moves
money (design ``docs/design/spot1-lab-solana.md`` §5.1), for the buy
(SOL -> token) and the sell (token -> SOL) alike.

Mirrors ``treasury_send.attempt_swap`` and ``infra/scripts/meme_spot_swap_send.py``
(T4.73b) step by step — quote → ``POST /swap`` with the **capped** priority fee
→ ``verify_spot_swap_tx`` → ``priority_fee_above_cap`` on the verified
``limit × price`` → kill switch re-read (a buy is refused, a sell never is) →
``simulateTransaction`` with ``accounts = (wallet, token ATA)`` and the balance
invariant read from ``simulation.accounts`` → ``signer.sign`` (the **only**
signature of the lane) → the signature on the row **before** the broadcast →
``sendTransaction`` → a bounded confirm loop → ``confirmed`` with the deltas of
**this signature** (``getTransaction`` meta), or ``submitted_unconfirmed`` for
the reconcile (T4.74-5).

The findings of ``.claude/state/review-T4.73.md`` that must not recur: the
invariant reads the simulated post-state, never two live reads (1); a
confirmation still pending is never a fill of zero (2); one row write per
session, so nothing after the send can roll the ``submitted`` row back (3);
a send that raises keeps the signature on the row and is settled by it —
only ``SendDisabled`` (never relayed by construction) is ``failed``.
"""

from __future__ import annotations

import asyncio
import base64
from typing import TYPE_CHECKING, Any

from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import WRAPPED_SOL_MINT, decode_versioned_transaction
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58encode,
    serialize_transaction,
)
from hunter_exchanges.pumpfun.tx_rpc import SendDisabled
from hunter_meme_executor import spot_repo
from hunter_meme_executor.journal_db import WORKER_ROLE
from hunter_meme_executor.spot_send_rules import (
    ATA_RENT_LAMPORTS,
    LegResult,
    check_simulated_leg,
    fee_allowance_lamports,
    fill_from_transaction,
    quote_mismatch,
)
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import TreasurySwapRefused, classify_submitted
from hunter_meme_executor.treasury_send import simulated_balances

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote
    from hunter_meme_executor.chain import TokenAccountRead, WalletRead
    from hunter_meme_executor.context import ExecutorContext

__all__ = ["CONFIRM_ATTEMPTS_CAP", "CONFIRM_INTERVAL_S", "LegResult", "spot_leg"]

logger = get_logger(__name__)

CONFIRM_ATTEMPTS_CAP = 20
"""The confirm loop blocks the lane's loop; past this the row stays
``submitted_unconfirmed`` and the reconcile (T4.74-5) settles it by signature."""
CONFIRM_INTERVAL_S = 1.0


async def _refuse(
    ctx: ExecutorContext, order_id: str, reason: str, quote: JupiterQuote | None
) -> LegResult:
    logger.warning("meme_spot_leg_refused", order_id=order_id, reason=reason)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await spot_repo.mark_refused(session, order_id, reason=reason, now=utcnow())
    return LegResult("refused", reason, None, 0, 0, quote)


async def _fail(
    ctx: ExecutorContext, order_id: str, reason: str, quote: JupiterQuote, signature: str | None
) -> LegResult:
    logger.error("meme_spot_leg_failed", order_id=order_id, reason=reason, signature=signature)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await spot_repo.mark_failed(session, order_id, reason=reason, now=utcnow())
    return LegResult("failed", reason, signature, 0, 0, quote)


def _unconfirmed(reason: str, signature: str, quote: JupiterQuote, fee: int) -> LegResult:
    """The row stays ``submitted_unconfirmed``; the reconcile settles it by signature."""
    return LegResult("submitted_unconfirmed", reason, signature, 0, 0, quote, 0, fee)


async def spot_leg(
    ctx: ExecutorContext,
    *,
    order_id: str,
    input_mint: str,
    output_mint: str,
    amount_atoms: int,
    slippage_bps: int,
    max_priority_fee_lamports: int,
    quote: JupiterQuote | None = None,
) -> LegResult:
    """One leg where exactly one side is native SOL, over an ``admitted`` row.
    ``quote`` lets the caller hand in the quote the admission already fetched
    (the row's ``quote`` is then the one that built the transaction); a sell
    re-quotes on every attempt by passing ``None``."""
    assert ctx.signer is not None, "spot_leg needs the process signer"
    is_buy = input_mint == WRAPPED_SOL_MINT
    if is_buy == (output_mint == WRAPPED_SOL_MINT):
        return await _refuse(ctx, order_id, "leg_needs_exactly_one_sol_side", None)
    wallet = ctx.signer.pubkey
    other_mint = output_mint if is_buy else input_mint
    client = ctx.treasury_client
    if quote is None:
        try:
            quote = await asyncio.to_thread(
                client.quote,
                input_mint=input_mint,
                output_mint=output_mint,
                amount=amount_atoms,
                slippage_bps=slippage_bps,
            )
        except Exception as exc:
            return await _refuse(ctx, order_id, f"quote_failed:{type(exc).__name__}", None)
    mismatch = quote_mismatch(quote, input_mint, output_mint, amount_atoms)
    if mismatch is not None:
        return await _refuse(ctx, order_id, mismatch, quote)
    intent = SpotSwapIntent(
        wallet=wallet,
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount=amount_atoms,
        min_quoted_out=int(quote.out_amount),
        max_slippage_bps=slippage_bps,
    )
    try:
        swap_tx = await asyncio.to_thread(
            client.swap,
            quote=quote,
            user_public_key=wallet,
            max_priority_fee_lamports=max_priority_fee_lamports,
        )
        raw_tx = base64.b64decode(swap_tx.swap_transaction_b64)
        decoded = decode_versioned_transaction(raw_tx)
        verified = verify_spot_swap_tx(decoded.message, intent=intent)
    except TreasurySwapRefused as exc:
        return await _refuse(ctx, order_id, exc.reason, quote)
    except Exception as exc:
        return await _refuse(ctx, order_id, f"swap_build_failed:{type(exc).__name__}", quote)
    fee = verified.priority_fee_lamports
    if fee > max_priority_fee_lamports:
        return await _refuse(ctx, order_id, f"priority_fee_above_cap:{fee}", quote)
    logger.info(
        "meme_spot_leg_verified",
        order_id=order_id,
        side="buy" if is_buy else "sell",
        route=verified.route_kind,
        in_amount=verified.in_amount,
        quoted_out=verified.quoted_out_amount,
        priority_fee_lamports=fee,
        ata_creates=verified.ata_creates,
    )
    other_ata = associated_token_address(wallet, other_mint, token_program=TOKEN_PROGRAM_ID)
    try:
        before_wallet, before_token = await _balances(ctx, wallet, other_mint)
        simulation = await asyncio.to_thread(
            ctx.chain.rpc.simulate_transaction,
            raw_tx,
            sig_verify=False,
            accounts=(wallet, other_ata),
        )
    except Exception as exc:
        return await _refuse(ctx, order_id, f"simulation_unreadable:{type(exc).__name__}", quote)
    if not simulation.ok:
        return await _refuse(ctx, order_id, f"simulation_failed:{str(simulation.err)[:120]}", quote)
    after = simulated_balances(simulation.accounts)
    if after is None:
        return await _refuse(ctx, order_id, "simulation_accounts_unreadable", quote)
    allowance = fee_allowance_lamports(
        ata_creates=verified.ata_creates,
        priority_fee_lamports=fee,
        transient_ata=1 if (verified.wraps_sol or verified.unwraps_sol) else 0,
    )
    invariant = check_simulated_leg(
        is_buy=is_buy,
        sol_before=before_wallet.lamports,
        sol_after=after[0],
        token_before=before_token.amount if before_token.exists else 0,
        token_after=after[1],
        amount_atoms=amount_atoms,
        min_out=int(quote.other_amount_threshold),
        fee_allowance_lamports=allowance,
    )
    if invariant is not None:
        return await _refuse(ctx, order_id, invariant, quote)
    # The last read before the signature, after every wait on the RPC (design
    # §5.1; Astra: a switch that moves during the simulation must still stop a
    # buy). A sell is an exit and is never blocked by a switch (RISK_ENGINE §10).
    await ctx.kill.refresh()
    if is_buy and ctx.kill.blocks_entries:
        return await _refuse(ctx, order_id, "kill_switch_blocked_before_signing", quote)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await spot_repo.mark_simulated(session, order_id, now=utcnow())

    # --- the only signature of the lane; the row carries it before the broadcast
    signature_bytes = ctx.signer.sign(decoded.message_bytes)
    signed_tx = serialize_transaction((signature_bytes,), decoded.message_bytes)
    signature = b58encode(signature_bytes)
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        recorded = await spot_repo.mark_submitted(
            session,
            order_id,
            signature=signature,
            last_valid_block_height=swap_tx.last_valid_block_height,
            now=utcnow(),
        )
    if not recorded:
        return await _fail(ctx, order_id, "row_not_ready", quote, None)
    ctx.state.last_signature = signature
    try:
        relayed = await asyncio.to_thread(ctx.chain.rpc.send_transaction, signed_tx)
    except SendDisabled:
        return await _fail(ctx, order_id, "send_disabled", quote, signature)
    except Exception as exc:
        # Ambiguous: the RPC may have relayed it before answering. Never ``failed``.
        ctx.state.rpc_errors += 1
        logger.error("meme_spot_send_unknown", signature=signature, error_type=type(exc).__name__)
        return _unconfirmed(f"send_unknown:{type(exc).__name__}", signature, quote, fee)
    if relayed != signature:
        logger.warning("meme_spot_signature_mismatch", local=signature, rpc=relayed)
    logger.info("meme_spot_leg_submitted", order_id=order_id, signature=signature)

    verdict = await _confirm(ctx, signature)
    if verdict == "failed":
        return await _fail(ctx, order_id, "on_chain_error", quote, signature)
    if verdict != "confirmed":
        logger.warning("meme_spot_confirm_pending", order_id=order_id, signature=signature)
        return _unconfirmed("confirm_pending_reconcile", signature, quote, fee)
    try:
        tx = await asyncio.to_thread(ctx.chain.rpc.get_transaction, signature)
    except Exception as exc:
        logger.error(
            "meme_spot_fill_unreadable", signature=signature, error_type=type(exc).__name__
        )
        return _unconfirmed(f"confirm_fill_unreadable:{type(exc).__name__}", signature, quote, fee)
    landed = None if tx is None else fill_from_transaction(tx, wallet=wallet, mint=other_mint)
    if tx is None or landed is None:
        # Confirmed by status, not yet served by getTransaction (or a meta this
        # module cannot read): the reconcile re-reads by signature — never a fill of zero.
        logger.warning("meme_spot_fill_not_visible", order_id=order_id, signature=signature)
        return _unconfirmed("fill_not_visible", signature, quote, fee)
    sol_delta, token_delta = landed.sol_delta_lamports, landed.token_delta_atoms
    # A buy spends SOL and lands tokens; a sell gives tokens and lands SOL. A
    # confirmed transaction whose own meta says otherwise is left to the
    # reconcile (Astra: never a spend of zero turned into a ticket).
    consistent = (
        (token_delta > 0 and sol_delta < 0) if is_buy else (sol_delta > 0 and token_delta < 0)
    )
    if not consistent:
        logger.warning("meme_spot_fill_inconsistent", order_id=order_id, signature=signature)
        return _unconfirmed("fill_inconsistent", signature, quote, fee)
    filled = token_delta if is_buy else sol_delta
    ata_rent = ATA_RENT_LAMPORTS if is_buy and landed.ata_created else 0
    fill: dict[str, Any] = {
        "signature": signature,
        "side": "buy" if is_buy else "sell",
        "source": "transaction_meta",
        "sol_delta_lamports": sol_delta,
        "token_before_atoms": landed.token_before_atoms,
        "token_after_atoms": landed.token_after_atoms,
        "filled_atoms": filled,
        "ata_rent_lamports": ata_rent,
        "priority_fee_lamports": fee,
        "network_fee_lamports": landed.network_fee_lamports,
        "quoted_out_atoms": int(quote.out_amount),
        "confirmed_at": utcnow().isoformat(),
    }
    async with role_session(ctx.session_factory, db_role=WORKER_ROLE) as session:
        await spot_repo.mark_confirmed(session, order_id, fill=fill, now=utcnow())
    logger.info(
        "meme_spot_leg_confirmed",
        order_id=order_id,
        signature=signature,
        filled_atoms=filled,
        sol_delta_lamports=sol_delta,
    )
    return LegResult("confirmed", None, signature, filled, sol_delta, quote, ata_rent, fee)


async def _balances(
    ctx: ExecutorContext, wallet: str, mint: str
) -> tuple[WalletRead, TokenAccountRead]:
    balance = await asyncio.to_thread(ctx.chain.wallet, wallet)
    token = await asyncio.to_thread(ctx.chain.token_account, wallet, mint, TOKEN_PROGRAM_ID)
    return balance, token


async def _confirm(ctx: ExecutorContext, signature: str) -> str:
    """``confirmed`` / ``failed`` / ``pending`` after at most ``CONFIRM_ATTEMPTS_CAP``
    reads one second apart; a read that raises is one attempt spent, never a verdict."""
    attempts = max(1, min(int(ctx.config.confirm_timeout_s), CONFIRM_ATTEMPTS_CAP))
    for _ in range(attempts):
        try:
            statuses = await asyncio.to_thread(ctx.chain.rpc.get_signature_statuses, [signature])
        except Exception:
            await asyncio.sleep(CONFIRM_INTERVAL_S)
            continue
        verdict = classify_submitted(statuses[0] if statuses else None, age_s=0.0)
        if verdict != "pending":
            return verdict
        await asyncio.sleep(CONFIRM_INTERVAL_S)
    return "pending"
