"""The money-moving half of ``meme_spot_swap.py --apply`` (T4.73): quote,
verify, simulate with the balance invariant, sign, send, confirm — one
``meme_treasury_swaps`` row per leg, advanced in place. Mirrors
``hunter_meme_executor.treasury_send`` exactly, generalized to a mint pair
where exactly one side is native SOL (``--apply``'s own limit — see
``meme_spot_swap.py``'s docstring).
"""

from __future__ import annotations

import asyncio
import base64
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
from meme_spot_swap_rules import check_buy_with_sol, check_sell_for_sol, from_atoms

from hunter_core.execution.meme.signer import MemeSigner
from hunter_exchanges.jupiter import JupiterClient
from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT
from hunter_exchanges.jupiter.versioned_tx import decode_versioned_transaction
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    serialize_transaction,
)
from hunter_meme_executor.chain import ChainReader
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import TreasurySwapRefused, classify_submitted

__all__ = ["COMPONENT", "run_apply_leg", "symbol"]

COMPONENT = "meme_spot_swap"
CONFIRM_ATTEMPTS = 20
WSOL_DECIMALS = 9


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
) -> tuple[str, int]:
    """One signed, sent, confirmed swap where exactly one leg is native SOL.
    Returns ``(status, filled_atoms_of_the_other_side)``."""
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
    swap_id = await insert_row(
        conn,
        reason=_reason(reason, input_mint=input_mint, output_mint=output_mint),
        amount_in=amount_in_human,
        amount_out_quoted=Decimal(quote.out_amount),
        price_impact_pct=quote.price_impact_pct,
        slippage_bps=slippage_bps,
        wallet_sol_before=Decimal(chain.wallet(wallet).lamports) / Decimal(1_000_000_000),
        input_mint=input_mint,
        output_mint=output_mint,
        status="quoted",
    )
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
        await mark_refused(conn, swap_id, refusal=exc.reason)
        return "refused", 0
    sol_before = chain.wallet(wallet).lamports
    other_before = chain.token_account(wallet, other_mint, TOKEN_PROGRAM_ID).amount
    simulation = chain.rpc.simulate_transaction(
        raw_tx, sig_verify=False, accounts=(wallet, other_ata)
    )
    if not simulation.ok:
        await mark_refused(conn, swap_id, refusal=f"simulation_failed:{str(simulation.err)[:120]}")
        return "refused", 0
    sol_after = chain.wallet(wallet).lamports
    invariant = (
        check_buy_with_sol(
            sol_before=sol_before,
            sol_after=sol_after,
            token_before=other_before,
            token_after=other_before,
            sol_in=amount_atoms,
            min_token_out=int(quote.other_amount_threshold),
        )
        if is_buy
        else check_sell_for_sol(
            sol_before=sol_before,
            sol_after=sol_after,
            token_before=other_before,
            token_after=other_before,
            token_in=amount_atoms,
            min_sol_out=int(quote.other_amount_threshold),
        )
    )
    if invariant is not None:
        await mark_refused(conn, swap_id, refusal=invariant)
        return "refused", 0
    await mark_simulated(conn, swap_id)
    signature_bytes = signer.sign(decoded.message_bytes)
    signed_tx = serialize_transaction((signature_bytes,), decoded.message_bytes)
    signature = chain.rpc.send_transaction(signed_tx)
    await mark_submitted(conn, swap_id, signature=signature)
    verdict = "pending"
    for _ in range(CONFIRM_ATTEMPTS):
        statuses = chain.rpc.get_signature_statuses([signature])
        verdict = classify_submitted(statuses[0] if statuses else None, age_s=0.0)
        if verdict != "pending":
            break
        await asyncio.sleep(1.0)
    if verdict == "failed":
        await mark_failed(conn, swap_id)
        return "failed", 0
    filled = max(0, chain.token_account(wallet, other_mint, TOKEN_PROGRAM_ID).amount - other_before)
    wallet_sol_after = Decimal(chain.wallet(wallet).lamports) / Decimal(1_000_000_000)
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
    return "confirmed", filled
