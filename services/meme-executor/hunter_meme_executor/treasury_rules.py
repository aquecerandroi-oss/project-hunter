"""T4.54 — the treasury top-up's pure rules: sizing, quote validation, the
effective SOL target, refusal classification and the post-simulation balance
invariant. No network, no database, no signer; every function here is a
plain value in, a plain value (or a named refusal) out, so the math can be
proven without a chain or a fixture.

The instruction-by-instruction verifier of the built transaction lives in
``treasury_verify`` (T4.54b); the orchestration these compose into is
``hunter_meme_executor.treasury`` (``docs/RISK_ENGINE_MEME.md`` §16).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hunter_exchanges.jupiter import JupiterQuote

__all__ = [
    "JUP_PROGRAM_ID",
    "MAX_PRICE_IMPACT_FRACTION",
    "SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS",
    "SUBMITTED_MAX_AGE_S",
    "USDC_MINT",
    "TreasurySwapRefused",
    "check_simulated_balances",
    "classify_quote_refusal",
    "classify_submitted",
    "effective_sol_target",
    "should_attempt",
    "size_first_pass",
    "size_to_target",
    "validate_quote",
]

JUP_PROGRAM_ID = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

MAX_PRICE_IMPACT_FRACTION = Decimal("0.01")
"""Cap on Jupiter's ``priceImpactPct`` — despite the name the field is a
**fraction**, not a percentage: a real 2 000 000 USDC quote (18/09/2026,
``lite-api.jup.ag/swap/v1/quote``) reported ``0.00333`` while its
``outAmount`` sat 0,34 % below the 1 USDC spot price; a percentage would have
read ``0.33``. So ``0.01`` here is **1 %**. Quotes for the treasury's sizes
(≤ 25 USDC) report ``0`` or ~``1e-6``."""

SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS = 10_000_000
"""0,01 SOL: the most the wallet may be short of ``sol_before +
other_amount_threshold`` after the simulated swap — base fee (5 000) plus the
priority fee (``treasury_verify.MAX_PRIORITY_FEE_LAMPORTS``, 0,005 SOL) plus
rent for an intermediate ATA a multi-hop route may create."""


SUBMITTED_MAX_AGE_S = 180.0
"""A ``submitted`` row the chain has never seen after this long is dead: a
blockhash is valid for ~60–90 s, and ``getSignatureStatuses`` with
``searchTransactionHistory`` finds anything that landed."""


class TreasurySwapRefused(Exception):
    """Named refusal; the caller never signs whatever failed verification."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"treasury_swap_refused:{reason}")


def size_first_pass(
    *, wallet_usdc_atoms: int, remaining_daily_cap_atoms: int, max_per_swap_atoms: int
) -> int:
    """The largest attempt allowed before the quote's own price is known."""
    return max(0, min(wallet_usdc_atoms, remaining_daily_cap_atoms, max_per_swap_atoms))


def size_to_target(
    *,
    first_pass_usdc_atoms: int,
    quote_in_amount_atoms: int,
    quote_out_amount_atoms: int,
    wallet_lamports: int,
    target_lamports: int,
) -> int:
    """Shrink ``first_pass_usdc_atoms`` to what the quote's own price says is
    needed to reach ``target_lamports`` — never overshoot the target."""
    needed_lamports = max(0, target_lamports - wallet_lamports)
    if needed_lamports == 0 or quote_out_amount_atoms <= 0:
        return 0
    needed_usdc_atoms = -(-needed_lamports * quote_in_amount_atoms // quote_out_amount_atoms)
    return max(0, min(first_pass_usdc_atoms, needed_usdc_atoms))


def effective_sol_target(
    *, configured_target_sol: Decimal, wallet_max_sol: Decimal, max_sol_per_trade: Decimal
) -> tuple[Decimal, str | None]:
    """T4.54b fix E — the target a top-up may fill the wallet to.

    The entry gate refuses every trade while ``wallet_sol > wallet_max_sol``
    (``wallet_over_max_sol``, §3.1 check 17), so a target above
    ``wallet_max_sol - max_sol_per_trade`` would buy SOL the desk could never
    spend and park the wallet above its own ceiling until someone intervened.
    Returns ``(target, None)`` when the configured target fits, or
    ``(cap, "target_above_wallet_max")`` when it had to be lowered — the
    caller sizes to the cap and logs the refusal reason once.
    """
    cap = wallet_max_sol - max_sol_per_trade
    if configured_target_sol <= cap:
        return configured_target_sol, None
    return cap, "target_above_wallet_max"


def validate_quote(
    quote: JupiterQuote,
    *,
    input_mint: str,
    output_mint: str,
    amount_atoms: int,
    slippage_bps: int,
) -> str | None:
    """T4.54b fix B — the quote must describe the swap that was asked for.

    Everything the transaction builder will read back from ``quote.raw`` is
    pinned here first: mints, ``inAmount`` (a quote for a bigger amount would
    drain more USDC than the row records), ``slippageBps`` (what Jupiter puts
    in the instruction) and ``otherAmountThreshold`` — the on-chain minimum
    out must be at least ``outAmount × (1 − slippage)`` rounded down, or the
    tolerance Jupiter enforces is looser than the one it quoted.
    """
    if quote.input_mint != input_mint or quote.output_mint != output_mint:
        return "quote_mismatch:mints"
    if quote.in_amount != amount_atoms:
        return "quote_mismatch:in_amount"
    if quote.slippage_bps != slippage_bps:
        return "quote_mismatch:slippage_bps"
    floor_out = int(quote.out_amount) * (10_000 - slippage_bps) // 10_000
    if quote.other_amount_threshold < floor_out:
        return "quote_mismatch:other_amount_threshold"
    return None


def classify_quote_refusal(
    quote: JupiterQuote, *, max_price_impact: Decimal = MAX_PRICE_IMPACT_FRACTION
) -> str | None:
    if not quote.route_labels or quote.out_amount <= 0:
        return "route_empty"
    if quote.price_impact_pct > max_price_impact:
        return "price_impact_above_cap"
    return None


def check_simulated_balances(
    *,
    usdc_before_atoms: int,
    usdc_after_atoms: int,
    usdc_in_atoms: int,
    sol_before_lamports: int,
    sol_after_lamports: int,
    min_out_lamports: int,
    fee_allowance_lamports: int = SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS,
) -> str | None:
    """T4.54b fix A (second half) — ``equity = cash + Σ positions`` applied
    before the signature: the simulated post-state may spend at most the
    requested USDC and must hand back at least the quote's minimum SOL, less
    fees. This is what bounds an instruction the verifier could only decode
    from the tail (``treasury_verify``): whatever the route plan says, the
    chain's own dry run has to agree with the row that will be recorded."""
    if usdc_after_atoms < usdc_before_atoms - usdc_in_atoms:
        return "simulation_usdc_overspent"
    if sol_after_lamports < sol_before_lamports + min_out_lamports - fee_allowance_lamports:
        return "simulation_sol_short"
    return None


def classify_submitted(
    status: Mapping[str, Any] | None, *, age_s: float, max_age_s: float = SUBMITTED_MAX_AGE_S
) -> str:
    """T4.54b fix C — what a ``getSignatureStatuses`` entry means for a
    ``submitted`` row: ``confirmed`` (landed), ``failed`` (errored on chain,
    or unseen past ``max_age_s``) or ``pending`` (keep counting it as spent,
    look again next tick)."""
    if status is None:
        return "failed" if age_s > max_age_s else "pending"
    if status.get("err") is not None:
        return "failed"
    if status.get("confirmationStatus") in ("confirmed", "finalized"):
        return "confirmed"
    return "pending"


def should_attempt(
    *,
    enabled: bool,
    live: bool,
    has_signer: bool,
    kill_blocked: bool,
    wallet_sol: Decimal,
    floor: Decimal,
    last_attempt_at: datetime | None,
    min_interval_s: float,
    now: datetime,
    usdc_spent_today: Decimal,
    daily_cap: Decimal,
) -> str | None:
    """A refusal reason, or ``None`` to size and quote a swap."""
    if not enabled:
        return "disabled"
    if not live:
        return "live_disabled"
    if not has_signer:
        return "no_signer"
    if kill_blocked:
        return "kill_switch_latched"
    if wallet_sol >= floor:
        return "sol_above_floor"
    if last_attempt_at is not None and (now - last_attempt_at).total_seconds() < min_interval_s:
        return "min_interval_not_elapsed"
    if usdc_spent_today >= daily_cap:
        return "daily_cap_reached"
    return None
