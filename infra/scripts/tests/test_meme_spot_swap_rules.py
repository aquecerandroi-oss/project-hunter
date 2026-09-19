"""``meme_spot_swap_rules.py`` (T4.73) — pure unit conversion and the two caps
a dry-run reports and ``--apply`` enforces. No network, no database.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from meme_spot_swap_rules import (  # noqa: E402
    check_buy_with_sol,
    check_sell_for_sol,
    classify_amount_cap,
    classify_impact_cap,
    from_atoms,
    sol_equivalent,
    to_atoms,
)

WSOL = "So11111111111111111111111111111111111111112"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"


def test_to_atoms_rounds_down_and_refuses_non_positive() -> None:
    assert to_atoms(Decimal("0.02"), 9) == 20_000_000
    assert to_atoms(Decimal("1.0000001"), 6) == 1_000_000  # 7th decimal dropped, never rounded up
    with pytest.raises(ValueError):
        to_atoms(Decimal("0"), 9)


def test_from_atoms_is_to_atoms_inverse_within_scale() -> None:
    assert from_atoms(20_000_000, 9) == Decimal("0.02")


def test_sol_equivalent_uses_the_sol_leg_whichever_side_it_is() -> None:
    assert sol_equivalent(
        input_mint=WSOL, output_mint=WIF, amount=Decimal("0.02"), quote_out_atoms=None
    ) == Decimal("0.02")
    assert sol_equivalent(
        input_mint=WIF, output_mint=WSOL, amount=Decimal("0"), quote_out_atoms=20_000_000
    ) == Decimal("0.02")
    assert (
        sol_equivalent(
            input_mint=WIF, output_mint="OTHER", amount=Decimal("1"), quote_out_atoms=None
        )
        is None
    )


def test_amount_cap_refuses_above_the_default_unless_i_know() -> None:
    assert classify_amount_cap(Decimal("0.05"), i_know=False) is None
    refusal = classify_amount_cap(Decimal("0.06"), i_know=False)
    assert refusal is not None and refusal.startswith("amount_above_cap:")
    assert classify_amount_cap(Decimal("0.06"), i_know=True) is None
    # T4.73b: ``--i-know`` lifts the soft cap only; 5 SOL hits the hard cap
    refusal = classify_amount_cap(Decimal("5"), i_know=True)
    assert refusal is not None and refusal.startswith("amount_above_hard_cap:")


def test_amount_cap_fails_closed_with_no_sol_leg_unless_i_know() -> None:
    assert classify_amount_cap(None, i_know=False) == "amount_cap_requires_a_sol_leg_or_i_know"
    assert classify_amount_cap(None, i_know=True) is None


def test_impact_cap_reads_jupiters_fraction_against_a_human_percentage() -> None:
    assert classify_impact_cap(Decimal("0.005"), max_impact_pct=Decimal("1")) is None
    refusal = classify_impact_cap(Decimal("0.02"), max_impact_pct=Decimal("1"))
    assert refusal is not None and refusal.startswith("price_impact_above_cap:")


def test_check_buy_with_sol_catches_overspend_and_shortfall() -> None:
    assert (
        check_buy_with_sol(
            sol_before=1_000_000_000,
            sol_after=980_000_000,
            token_before=0,
            token_after=1_000,
            sol_in=20_000_000,
            min_token_out=900,
        )
        is None
    )
    assert (
        check_buy_with_sol(
            sol_before=1_000_000_000,
            sol_after=900_000_000,
            token_before=0,
            token_after=1_000,
            sol_in=20_000_000,
            min_token_out=900,
            fee_allowance_lamports=0,
        )
        == "simulation_sol_overspent"
    )
    assert (
        check_buy_with_sol(
            sol_before=1_000_000_000,
            sol_after=980_000_000,
            token_before=0,
            token_after=100,
            sol_in=20_000_000,
            min_token_out=900,
        )
        == "simulation_token_short"
    )


def test_check_sell_for_sol_catches_overspend_and_shortfall() -> None:
    assert (
        check_sell_for_sol(
            sol_before=0,
            sol_after=19_000_000,
            token_before=1_000_000,
            token_after=0,
            token_in=1_000_000,
            min_sol_out=18_000_000,
        )
        is None
    )
    assert (
        check_sell_for_sol(
            sol_before=0,
            sol_after=19_000_000,
            token_before=1_000_000,
            token_after=0,
            token_in=500_000,
            min_sol_out=18_000_000,
        )
        == "simulation_token_overspent"
    )
    assert (
        check_sell_for_sol(
            sol_before=0,
            sol_after=1_000,
            token_before=1_000_000,
            token_after=0,
            token_in=1_000_000,
            min_sol_out=18_000_000,
            fee_allowance_lamports=0,
        )
        == "simulation_sol_short"
    )


# --- T4.73b, review finding 4: a hard cap ``--i-know`` cannot lift, and a wallet floor


def test_hard_cap_is_not_lifted_by_i_know() -> None:
    from meme_spot_swap_rules import HARD_CAP_SOL_EQUIVALENT

    assert HARD_CAP_SOL_EQUIVALENT == Decimal("0.10")
    assert classify_amount_cap(Decimal("0.10"), i_know=True) is None
    refusal = classify_amount_cap(Decimal("0.7"), i_know=True)  # the "0.07" typo of the review
    assert refusal is not None and refusal.startswith("amount_above_hard_cap:")
    refusal = classify_amount_cap(Decimal("0.11"), i_know=False)
    assert refusal is not None and refusal.startswith("amount_above_hard_cap:")


def test_wallet_floor_keeps_amount_plus_fee_allowance_above_the_floor() -> None:
    from meme_spot_swap_rules import classify_wallet_floor

    # 0.76 - 0.02 - 0.01 = 0.73 >= 0.30
    assert (
        classify_wallet_floor(
            wallet_sol=Decimal("0.76"), amount_sol=Decimal("0.02"), floor=Decimal("0.30")
        )
        is None
    )
    # 0.32 - 0.02 - 0.01 = 0.29 < 0.30
    refusal = classify_wallet_floor(
        wallet_sol=Decimal("0.32"), amount_sol=Decimal("0.02"), floor=Decimal("0.30")
    )
    assert refusal == "wallet_below_floor_after_swap:0.29<0.30"
    # exactly on the floor passes
    assert (
        classify_wallet_floor(
            wallet_sol=Decimal("0.33"), amount_sol=Decimal("0.02"), floor=Decimal("0.30")
        )
        is None
    )


def test_wallet_floor_env_defaults_to_0_30_and_refuses_garbage() -> None:
    from meme_spot_swap_rules import ENV_WALLET_MIN_SOL_AFTER_SWAP, parse_wallet_floor

    assert ENV_WALLET_MIN_SOL_AFTER_SWAP == "MEME_WALLET_MIN_SOL_AFTER_SWAP"
    assert parse_wallet_floor(None) == Decimal("0.30")
    assert parse_wallet_floor("0.5") == Decimal("0.5")
    with pytest.raises(ValueError):
        parse_wallet_floor("abc")
    with pytest.raises(ValueError):
        parse_wallet_floor("-1")
    with pytest.raises(ValueError):
        parse_wallet_floor("0")
