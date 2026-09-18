"""T4.54 — the treasury top-up's pure rules: sizing, refusal classification and
the transaction-shape verifier. No network, no database, no signer; every
function here is a plain value in, a plain value (or a named refusal) out, so
the sizing math and the allowlist can be proven without a chain or a fixture.

See ``hunter_meme_executor.treasury`` for the orchestration these compose
into and the doctrine they enforce (``docs/RISK_ENGINE_MEME.md`` new §).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)

if TYPE_CHECKING:
    from hunter_exchanges.jupiter import JupiterQuote
    from hunter_exchanges.jupiter.versioned_tx import VersionedMessage

__all__ = [
    "JUP_PROGRAM_ID",
    "MAX_PRICE_IMPACT_PCT",
    "TREASURY_ALLOWED_PROGRAMS",
    "TreasurySwapRefused",
    "classify_quote_refusal",
    "should_attempt",
    "size_first_pass",
    "size_to_target",
    "verify_swap_transaction",
]

JUP_PROGRAM_ID = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
MAX_PRICE_IMPACT_PCT = Decimal("0.01")
_ZERO_BLOCKHASH_B58 = "1" * 32

TREASURY_ALLOWED_PROGRAMS = frozenset(
    {
        JUP_PROGRAM_ID,
        TOKEN_PROGRAM_ID,
        TOKEN_2022_PROGRAM_ID,
        ASSOCIATED_TOKEN_PROGRAM_ID,
        SYSTEM_PROGRAM_ID,
        COMPUTE_BUDGET_PROGRAM_ID,
    }
)


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


def classify_quote_refusal(
    quote: JupiterQuote, *, max_price_impact_pct: Decimal = MAX_PRICE_IMPACT_PCT
) -> str | None:
    if not quote.route_labels or quote.out_amount <= 0:
        return "route_empty"
    if quote.price_impact_pct > max_price_impact_pct:
        return "price_impact_above_cap"
    return None


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


def verify_swap_transaction(
    message: VersionedMessage, *, wallet: str, allowed_programs: frozenset[str] | None = None
) -> None:
    """§9.1's discipline, as far as a versioned/ALT transaction allows it
    (module docstring, ``jupiter/versioned_tx.py``): the wallet is the sole
    signer and fee payer, and every instruction's program is on the
    allowlist — one behind a lookup table is refused, never trusted."""
    allowed = allowed_programs or TREASURY_ALLOWED_PROGRAMS
    if message.num_required_signatures != 1:
        raise TreasurySwapRefused("more_than_one_signer")
    if not message.static_account_keys or message.static_account_keys[0] != wallet:
        raise TreasurySwapRefused("fee_payer_not_wallet")
    if message.recent_blockhash == _ZERO_BLOCKHASH_B58:
        raise TreasurySwapRefused("blockhash_missing")
    for instruction in message.instructions:
        program_id = message.program_id(instruction.program_id_index)
        if program_id is None:
            raise TreasurySwapRefused("program_via_lookup_table")
        if program_id not in allowed:
            raise TreasurySwapRefused(f"program_not_allowed:{program_id}")
