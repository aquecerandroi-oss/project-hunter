"""The money-moving half of ``meme_spot_swap.py --apply`` (T4.73): quote,
verify, simulate with the balance invariant, sign, send, confirm — one
``meme_treasury_swaps`` row per leg, advanced in place. Mirrors
``hunter_meme_executor.treasury_send`` exactly, generalized to a mint pair
where exactly one side is native SOL (``--apply``'s own limit — see
``meme_spot_swap.py``'s docstring).

T4.73b (``.claude/state/review-T4.73.md``): the invariant reads the
**simulated post-state** (``simulation.accounts``, the same
``treasury_send.simulated_balances`` parser) — never two live reads of the
same balance (finding 1); a confirmation that is still ``pending`` after
``CONFIRM_ATTEMPTS`` leaves the row ``submitted`` and returns that status, so
the caller can never treat it as a fill of zero (finding 2); every row write
commits on its own, so an exception after ``sendTransaction`` cannot roll the
``submitted`` row back (finding 3); the impact cap runs here, for every leg
(finding 5). Astra's second opinion on that diff added two more: the
signature is **derived locally** (base58 of the ed25519 signature bytes — a
Solana transaction id is exactly that) and the row is ``submitted`` with it
**before** the broadcast, so a ``sendTransaction`` that raises after relaying
(HTTP timeout) can never be recorded as ``failed`` without a signature; and a
sell leg's ``filled`` is the SOL that landed (lamports), not the token delta.
"""

from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from meme_ops_db import record_event
from meme_spot_swap_db import (
    insert_row,
    mark_confirmed,
    mark_failed,
    mark_refused,
    mark_simulated,
    mark_submitted,
)
from meme_spot_swap_rules import (
    check_buy_with_sol,
    check_sell_for_sol,
    classify_impact_cap,
    from_atoms,
)

from hunter_core.execution.meme.signer import MemeSigner
from hunter_core.logging import get_logger
from hunter_exchanges.jupiter import JupiterClient
from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT
from hunter_exchanges.jupiter.versioned_tx import decode_versioned_transaction
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58encode,
    serialize_transaction,
)
from hunter_meme_executor.chain import ChainReader
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import TreasurySwapRefused, classify_submitted
from hunter_meme_executor.treasury_send import simulated_balances

__all__ = ["COMPONENT", "CONFIRM_ATTEMPTS", "CONFIRM_INTERVAL_S", "LegResult", "run_apply_leg"]

logger = get_logger(__name__)

COMPONENT = "meme_spot_swap"
CONFIRM_ATTEMPTS = 20
CONFIRM_INTERVAL_S = 1.0
WSOL_DECIMALS = 9
LAMPORTS = Decimal(1_000_000_000)


@dataclass(frozen=True, slots=True)
class LegResult:
    """``status`` is the row's final status as this process saw it:
    ``refused`` | ``failed`` | ``submitted`` (sent, not confirmed within the
    wait — reconcile by ``signature``) | ``confirmed``. ``filled`` is the
    other side's atoms actually received, ``0`` unless ``confirmed``."""

    status: str
    filled: int
    signature: str | None


def symbol(mint: str) -> str:
    return "SOL" if mint == WRAPPED_SOL_MINT else mint


def _reason(reason: str, *, input_mint: str, output_mint: str) -> str:
    return f"{reason}:{symbol(input_mint)}->{symbol(output_mint)}"


async def run_apply_leg(
    conn: Any,
    chain: ChainReader,
    client: JupiterClient,
    signer: MemeSigner,
    *,
    reason: str,
    input_mint: str,
    output_mint: str,
    amount_atoms: int,
    slippage_bps: int,
    max_impact_pct: Decimal,
) -> LegResult:
    """One signed, sent, confirmed swap where exactly one leg is native SOL."""
    wallet = signer.pubkey
    is_buy = input_mint == WRAPPED_SOL_MINT
    other_mint = output_mint if is_buy else input_mint
    other_ata = associated_token_address(wallet, other_mint, token_program=TOKEN_PROGRAM_ID)
    quote = client.quote(
        input_mint=input_mint,
        output_mint=output_mint,
        amount=amount_atoms,
        slippage_bps=slippage_bps,
    )
    amount_in_human = from_atoms(amount_atoms, WSOL_DECIMALS) if is_buy else Decimal(amount_atoms)
    impact_refusal = classify_impact_cap(quote.price_impact_pct, max_impact_pct=max_impact_pct)
    swap_id = await insert_row(
        conn,
        reason=_reason(reason, input_mint=input_mint, output_mint=output_mint),
        amount_in=amount_in_human,
        amount_out_quoted=Decimal(quote.out_amount),
        price_impact_pct=quote.price_impact_pct,
        slippage_bps=slippage_bps,
        wallet_sol_before=Decimal(chain.wallet(wallet).lamports) / LAMPORTS,
        input_mint=input_mint,
        output_mint=output_mint,
        status="quoted",
    )
    if impact_refusal is not None:
        return await _refuse(conn, swap_id, impact_refusal)
    intent = SpotSwapIntent(
        wallet=wallet,
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount=amount_atoms,
        min_quoted_out=int(quote.out_amount),
        max_slippage_bps=slippage_bps,
    )
    try:
        swap_tx = client.swap(quote=quote, user_public_key=wallet)
        raw_tx = base64.b64decode(swap_tx.swap_transaction_b64)
        decoded = decode_versioned_transaction(raw_tx)
        verify_spot_swap_tx(decoded.message, intent=intent)
    except TreasurySwapRefused as exc:
        return await _refuse(conn, swap_id, exc.reason)
    except Exception as exc:
        return await _refuse(conn, swap_id, f"swap_build_failed:{type(exc).__name__}")

    # --- simulate with the post-state of [wallet, other ATA] and check the invariant
    sol_before = chain.wallet(wallet).lamports
    token_before = chain.token_account(wallet, other_mint, TOKEN_PROGRAM_ID).amount
    try:
        simulation = chain.rpc.simulate_transaction(
            raw_tx, sig_verify=False, accounts=(wallet, other_ata)
        )
    except Exception as exc:
        return await _refuse(conn, swap_id, f"simulation_unreadable:{type(exc).__name__}")
    if not simulation.ok:
        return await _refuse(conn, swap_id, f"simulation_failed:{str(simulation.err)[:120]}")
    after = simulated_balances(simulation.accounts)
    if after is None:
        return await _refuse(conn, swap_id, "simulation_accounts_unreadable")
    sol_after, token_after = after
    invariant = (
        check_buy_with_sol(
            sol_before=sol_before,
            sol_after=sol_after,
            token_before=token_before,
            token_after=token_after,
            sol_in=amount_atoms,
            min_token_out=int(quote.other_amount_threshold),
        )
        if is_buy
        else check_sell_for_sol(
            sol_before=sol_before,
            sol_after=sol_after,
            token_before=token_before,
            token_after=token_after,
            token_in=amount_atoms,
            min_sol_out=int(quote.other_amount_threshold),
        )
    )
    if invariant is not None:
        return await _refuse(conn, swap_id, invariant)
    await mark_simulated(conn, swap_id)

    # --- sign; the row is ``submitted`` with the local signature BEFORE the broadcast
    signature_bytes = signer.sign(decoded.message_bytes)
    signed_tx = serialize_transaction((signature_bytes,), decoded.message_bytes)
    signature = b58encode(signature_bytes)
    await mark_submitted(conn, swap_id, signature=signature)
    try:
        relayed = chain.rpc.send_transaction(signed_tx)
    except Exception as exc:
        # Ambiguous: the RPC may have relayed it before answering. Never
        # ``failed`` — the row keeps its signature; reconcile by it.
        logger.error(
            "meme_spot_swap_send_unknown", signature=signature, error_type=type(exc).__name__
        )
        return LegResult("submitted", 0, signature)
    if relayed != signature:
        logger.warning("meme_spot_swap_signature_mismatch", local=signature, rpc=relayed)
    logger.info("meme_spot_swap_submitted", signature=signature)

    # --- confirm; anything but a clean verdict leaves the row ``submitted``
    try:
        verdict = await _confirm(chain, signature)
    except Exception as exc:
        logger.error(
            "meme_spot_swap_confirm_unreadable",
            signature=signature,
            error_type=type(exc).__name__,
        )
        return LegResult("submitted", 0, signature)
    if verdict == "failed":
        await mark_failed(conn, swap_id)
        logger.error("meme_spot_swap_failed_on_chain", signature=signature)
        return LegResult("failed", 0, signature)
    if verdict != "confirmed":
        logger.warning("meme_spot_swap_confirm_pending", signature=signature)
        return LegResult("submitted", 0, signature)
    lamports_after = chain.wallet(wallet).lamports
    filled = (
        max(0, chain.token_account(wallet, other_mint, TOKEN_PROGRAM_ID).amount - token_before)
        if is_buy
        else max(0, lamports_after - sol_before)  # a sell fills in SOL, net of fees
    )
    wallet_sol_after = Decimal(lamports_after) / LAMPORTS
    await mark_confirmed(
        conn, swap_id, amount_out_filled=Decimal(filled), wallet_sol_after=wallet_sol_after
    )
    await record_event(
        conn,
        component=COMPONENT,
        level="info",
        event="swap_confirmed",
        message=f"{reason}: {symbol(input_mint)}->{symbol(output_mint)} signature={signature}",
        data={"signature": signature, "input_mint": input_mint, "output_mint": output_mint},
    )
    await conn.commit()
    return LegResult("confirmed", filled, signature)


async def _refuse(conn: Any, swap_id: Any, refusal: str) -> LegResult:
    await mark_refused(conn, swap_id, refusal=refusal)
    logger.warning("meme_spot_swap_refused", refusal=refusal)
    return LegResult("refused", 0, None)


async def _confirm(chain: ChainReader, signature: str) -> str:
    verdict = "pending"
    for _ in range(CONFIRM_ATTEMPTS):
        statuses = chain.rpc.get_signature_statuses([signature])
        verdict = classify_submitted(statuses[0] if statuses else None, age_s=0.0)
        if verdict != "pending":
            break
        await asyncio.sleep(CONFIRM_INTERVAL_S)
    return verdict
