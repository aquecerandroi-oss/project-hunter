"""Quote + verify a Jupiter swap for ``meme_spot_swap.py`` (T4.73): reads a
mint's on-chain decimals, fetches a quote, classifies the two caps and,
with a public key (``--user`` in a dry-run, the signer's own in ``--apply``),
builds and verifies the unsigned transaction before anything signs it.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from meme_spot_swap_rules import (
    classify_amount_cap,
    classify_impact_cap,
    from_atoms,
    sol_equivalent,
)

from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT, JupiterQuote, JupiterSwapTransaction
from hunter_exchanges.jupiter.versioned_tx import decode_versioned_transaction
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
from hunter_meme_executor.spot_alt import account_keys_for
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import TreasurySwapRefused

__all__ = [
    "JupiterClientLike",
    "Plan",
    "Refused",
    "build_plan",
    "format_plan",
    "read_mint_decimals",
]


class JupiterClientLike(Protocol):
    """The two ``JupiterClient`` methods this module calls — a fake test
    client only needs to match this shape, not the real network client."""

    def quote(
        self, *, input_mint: str, output_mint: str, amount: int, slippage_bps: int
    ) -> JupiterQuote: ...

    def swap(self, *, quote: JupiterQuote, user_public_key: str) -> JupiterSwapTransaction: ...


WSOL_DECIMALS = 9


class Refused(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def read_mint_decimals(rpc: SolanaTxRpcClient, mint: str) -> int:
    """SPL ``Mint`` layout: ``decimals`` is the single byte at offset 44
    (mintAuthorityOption 4 + mintAuthority 32 + supply 8), true of Token and
    Token-2022's shared base layout."""
    if mint == WRAPPED_SOL_MINT:
        return WSOL_DECIMALS
    snapshot = rpc.get_account(mint, commitment="confirmed")
    if snapshot is None:
        raise Refused(f"mint_not_found:{mint}")
    raw = base64.b64decode(snapshot.data_base64)
    if len(raw) < 45:
        raise Refused(f"mint_account_too_short:{mint}")
    return raw[44]


@dataclass(frozen=True, slots=True)
class Plan:
    input_mint: str
    output_mint: str
    amount_atoms: int
    quote: JupiterQuote
    amount_cap_refusal: str | None
    impact_refusal: str | None
    verify_reason: str | None  # None with no pubkey; "" means it verified


def build_plan(
    client: JupiterClientLike,
    *,
    input_mint: str,
    output_mint: str,
    amount_atoms: int,
    slippage_bps: int,
    max_impact_pct: Decimal,
    i_know: bool,
    wallet_pubkey: str | None,
    rpc: SolanaTxRpcClient | None = None,
) -> Plan:
    quote = client.quote(
        input_mint=input_mint,
        output_mint=output_mint,
        amount=amount_atoms,
        slippage_bps=slippage_bps,
    )
    amount_sol = (
        from_atoms(amount_atoms, WSOL_DECIMALS) if input_mint == WRAPPED_SOL_MINT else Decimal(0)
    )
    equivalent = sol_equivalent(
        input_mint=input_mint,
        output_mint=output_mint,
        amount=amount_sol,
        quote_out_atoms=int(quote.out_amount) if output_mint == WRAPPED_SOL_MINT else None,
    )
    amount_refusal = classify_amount_cap(equivalent, i_know=i_know)
    impact_refusal = classify_impact_cap(quote.price_impact_pct, max_impact_pct=max_impact_pct)
    verify_reason: str | None = None
    if wallet_pubkey is not None:
        verify_reason = _verify(
            client,
            quote,
            rpc=rpc,
            wallet_pubkey=wallet_pubkey,
            input_mint=input_mint,
            output_mint=output_mint,
            amount_atoms=amount_atoms,
            slippage_bps=slippage_bps,
        )
    return Plan(
        input_mint=input_mint,
        output_mint=output_mint,
        amount_atoms=amount_atoms,
        quote=quote,
        amount_cap_refusal=amount_refusal,
        impact_refusal=impact_refusal,
        verify_reason=verify_reason,
    )


def _verify(
    client: JupiterClientLike,
    quote: JupiterQuote,
    *,
    rpc: SolanaTxRpcClient | None,
    wallet_pubkey: str,
    input_mint: str,
    output_mint: str,
    amount_atoms: int,
    slippage_bps: int,
) -> str:
    try:
        swap_tx = client.swap(quote=quote, user_public_key=wallet_pubkey)
        decoded = decode_versioned_transaction(base64.b64decode(swap_tx.swap_transaction_b64))
        intent = SpotSwapIntent(
            wallet=wallet_pubkey,
            input_mint=input_mint,
            output_mint=output_mint,
            in_amount=amount_atoms,
            min_quoted_out=int(quote.out_amount),
            max_slippage_bps=slippage_bps,
        )
        # T4.81: the lookup tables are resolved from the chain first — without
        # an RPC a route that uses them can only be reported unverifiable.
        keys = None if rpc is None else account_keys_for(rpc, decoded.message)
        verify_spot_swap_tx(decoded.message, intent=intent, account_keys=keys)
        return ""
    except TreasurySwapRefused as exc:
        return exc.reason
    except Exception as exc:  # network/parse failure -- report, never crash the dry-run
        return f"verify_unavailable:{type(exc).__name__}"


def format_plan(plan: Plan, *, in_decimals: int, out_decimals: int) -> str:
    lines = [
        f"quote {plan.input_mint} -> {plan.output_mint}",
        f"  in={from_atoms(plan.amount_atoms, in_decimals)} ({plan.amount_atoms} atoms)",
        f"  out~={from_atoms(int(plan.quote.out_amount), out_decimals)} "
        f"threshold={from_atoms(int(plan.quote.other_amount_threshold), out_decimals)}",
        f"  route={' -> '.join(plan.quote.route_labels) or '(empty)'}",
        f"  price_impact_pct={plan.quote.price_impact_pct}",
        f"  amount_cap: {'ok' if plan.amount_cap_refusal is None else plan.amount_cap_refusal}",
        f"  impact_cap: {'ok' if plan.impact_refusal is None else plan.impact_refusal}",
    ]
    if plan.verify_reason is None:
        lines.append("  verify: skipped (no --user)")
    elif plan.verify_reason == "":
        lines.append("  verify: OK")
    else:
        lines.append(f"  verify: REFUSED {plan.verify_reason}")
    return "\n".join(lines)
