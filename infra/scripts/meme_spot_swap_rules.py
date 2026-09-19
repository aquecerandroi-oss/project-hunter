"""Pure rules of ``meme_spot_swap.py`` (T4.73): unit conversion and the two
caps a dry-run reports and ``--apply`` enforces. No network, no database, no
signer — split out so the CLI script itself stays under the 350-line budget
and this arithmetic is testable without a fixture or a mock.
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, InvalidOperation

from hunter_exchanges.jupiter.models import WRAPPED_SOL_MINT

__all__ = [
    "DEFAULT_AMOUNT_CAP_SOL_EQUIVALENT",
    "DEFAULT_MAX_IMPACT_PCT",
    "DEFAULT_WALLET_MIN_SOL_AFTER_SWAP",
    "ENV_WALLET_MIN_SOL_AFTER_SWAP",
    "HARD_CAP_SOL_EQUIVALENT",
    "SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS",
    "WALLET_FLOOR_FEE_ALLOWANCE_SOL",
    "WSOL_DECIMALS",
    "check_buy_with_sol",
    "check_sell_for_sol",
    "classify_amount_cap",
    "classify_impact_cap",
    "classify_wallet_floor",
    "from_atoms",
    "parse_wallet_floor",
    "sol_equivalent",
    "to_atoms",
]

DEFAULT_AMOUNT_CAP_SOL_EQUIVALENT = Decimal("0.05")
HARD_CAP_SOL_EQUIVALENT = Decimal("0.10")
"""T4.73b (review finding 4): the ceiling ``--i-know`` does **not** lift. A
typo ("0.7" for "0.07") with ``--i-know`` must never sign 0,7 of a 0,76 SOL
wallet; anything above this needs a code change, not a flag."""
DEFAULT_MAX_IMPACT_PCT = Decimal("1")
WSOL_DECIMALS = 9
ENV_WALLET_MIN_SOL_AFTER_SWAP = "MEME_WALLET_MIN_SOL_AFTER_SWAP"
DEFAULT_WALLET_MIN_SOL_AFTER_SWAP = Decimal("0.30")
"""T4.73b (review finding 4): what must remain in the wallet after a SOL
buy leg **and** its fee allowance — the treasury's own ``MEME_TREASURY_SOL_FLOOR``
default (0,30), spelled as a separate variable because this script must never
spend the wallet down to where the executor's top-up would have to kick in."""
WALLET_FLOOR_FEE_ALLOWANCE_SOL = Decimal("0.01")
SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS = 10_000_000
"""0,01 SOL: the same allowance ``treasury_rules`` uses for base fee + priority
fee + a possible intermediate-ATA rent — one leg of every swap this script
runs is always native SOL (§ below)."""


def to_atoms(amount: Decimal, decimals: int) -> int:
    """Human units -> the mint's smallest unit, rounded down (never request
    more than what was typed)."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    if decimals < 0:
        raise ValueError("decimals must not be negative")
    scaled = amount * (Decimal(10) ** decimals)
    return int(scaled.to_integral_value(rounding=ROUND_DOWN))


def from_atoms(amount: int, decimals: int) -> Decimal:
    return Decimal(amount) / (Decimal(10) ** decimals)


def sol_equivalent(
    *,
    input_mint: str,
    output_mint: str,
    amount: Decimal,
    quote_out_atoms: int | None,
) -> Decimal | None:
    """The size in SOL the ``--amount`` cap is measured against.

    ``--from SOL``: the amount itself. ``--to SOL`` (selling a token for
    SOL): the quote's own ``out_amount`` in lamports, once a quote exists —
    ``None`` before that (the caller must not size a cap it cannot compute
    yet). Neither leg SOL (token -> token): ``None`` — this script refuses to
    guess a SOL-equivalent of an arbitrary pair rather than under-guard it;
    see ``classify_amount_cap``.
    """
    if input_mint == WRAPPED_SOL_MINT:
        return amount
    if output_mint == WRAPPED_SOL_MINT:
        if quote_out_atoms is None:
            return None
        return from_atoms(quote_out_atoms, WSOL_DECIMALS)
    return None


def classify_amount_cap(
    amount_sol_equivalent: Decimal | None,
    *,
    i_know: bool,
    cap: Decimal = DEFAULT_AMOUNT_CAP_SOL_EQUIVALENT,
    hard_cap: Decimal = HARD_CAP_SOL_EQUIVALENT,
) -> str | None:
    """A refusal reason, or ``None`` to proceed. Fails closed: a pair with no
    SOL leg (so no computable SOL-equivalent) is refused unless ``i_know``,
    exactly like an amount over the soft cap. The hard cap is checked first
    and ignores ``i_know`` (T4.73b)."""
    if amount_sol_equivalent is None:
        return None if i_know else "amount_cap_requires_a_sol_leg_or_i_know"
    if amount_sol_equivalent > hard_cap:
        return f"amount_above_hard_cap:{amount_sol_equivalent}>{hard_cap}"
    if amount_sol_equivalent > cap and not i_know:
        return f"amount_above_cap:{amount_sol_equivalent}>{cap}"
    return None


def classify_wallet_floor(
    *,
    wallet_sol: Decimal,
    amount_sol: Decimal,
    floor: Decimal = DEFAULT_WALLET_MIN_SOL_AFTER_SWAP,
    fee_allowance_sol: Decimal = WALLET_FLOOR_FEE_ALLOWANCE_SOL,
) -> str | None:
    """T4.73b (review finding 4): a SOL buy leg must leave
    ``wallet - amount - fee_allowance >= floor``; ``--i-know`` does not lift it."""
    remaining = wallet_sol - amount_sol - fee_allowance_sol
    if remaining < floor:
        return f"wallet_below_floor_after_swap:{remaining}<{floor}"
    return None


def parse_wallet_floor(raw: str | None) -> Decimal:
    """``MEME_WALLET_MIN_SOL_AFTER_SWAP`` -> Decimal; unset -> the default;
    anything unparseable or non-positive raises ``ValueError`` (fail closed —
    the caller refuses, never falls back to a smaller floor)."""
    if raw is None or not raw.strip():
        return DEFAULT_WALLET_MIN_SOL_AFTER_SWAP
    try:
        value = Decimal(raw.strip())
    except InvalidOperation as exc:
        raise ValueError(f"{ENV_WALLET_MIN_SOL_AFTER_SWAP} is not a decimal") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{ENV_WALLET_MIN_SOL_AFTER_SWAP} must be positive")
    return value


def classify_impact_cap(
    price_impact_pct: Decimal, *, max_impact_pct: Decimal = DEFAULT_MAX_IMPACT_PCT
) -> str | None:
    """``price_impact_pct`` is Jupiter's own field — a **fraction**, confirmed
    live in T4.54b (``docs/RISK_ENGINE_MEME.md`` §16.1 item 6); ``max_impact_pct``
    is the CLI's human percentage (default ``1`` meaning 1%)."""
    limit_fraction = max_impact_pct / Decimal(100)
    if price_impact_pct > limit_fraction:
        return f"price_impact_above_cap:{price_impact_pct}>{limit_fraction}"
    return None


def check_buy_with_sol(
    *,
    sol_before: int,
    sol_after: int,
    token_before: int,
    token_after: int,
    sol_in: int,
    min_token_out: int,
    fee_allowance_lamports: int = SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS,
) -> str | None:
    """``equity = cash + positions`` for a SOL -> token leg: the simulated
    post-state may spend at most ``sol_in`` (plus fees) and must hand back at
    least the quote's minimum token out."""
    if sol_after < sol_before - sol_in - fee_allowance_lamports:
        return "simulation_sol_overspent"
    if token_after < token_before + min_token_out:
        return "simulation_token_short"
    return None


def check_sell_for_sol(
    *,
    sol_before: int,
    sol_after: int,
    token_before: int,
    token_after: int,
    token_in: int,
    min_sol_out: int,
    fee_allowance_lamports: int = SIMULATION_SOL_FEE_ALLOWANCE_LAMPORTS,
) -> str | None:
    """The mirror, for a token -> SOL leg (the round trip's sell side, and
    the treasury's own USDC -> SOL invariant generalized to any mint)."""
    if token_after < token_before - token_in:
        return "simulation_token_overspent"
    if sol_after < sol_before + min_sol_out - fee_allowance_lamports:
        return "simulation_sol_short"
    return None
