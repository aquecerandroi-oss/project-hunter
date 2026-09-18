"""T4.54 — sizing math, quote validation, the effective target, refusal
reasons and the post-simulation balance invariant. Pure functions: no
network, no database, no signer, no chain (the transaction verifier has its
own file, ``test_treasury_verify.py``)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_exchanges.jupiter import JupiterQuote
from hunter_meme_executor.treasury_rules import (
    check_simulated_balances,
    classify_quote_refusal,
    effective_sol_target,
    should_attempt,
    size_first_pass,
    size_to_target,
    validate_quote,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def _quote(**overrides: object) -> JupiterQuote:
    base: dict[str, object] = {
        "input_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "output_mint": "So11111111111111111111111111111111111111112",
        "in_amount": Decimal("5000000"),
        "out_amount": Decimal("34215678"),
        "other_amount_threshold": Decimal("34044599"),  # floor(out × 0.995)
        "price_impact_pct": Decimal("0.0012"),
        "slippage_bps": 50,
        "route_labels": ("Whirlpool",),
        "raw": {},
    }
    base.update(overrides)
    return JupiterQuote(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------- sizing
def test_size_first_pass_is_the_smallest_of_the_three_caps() -> None:
    assert (
        size_first_pass(
            wallet_usdc_atoms=100_000_000,
            remaining_daily_cap_atoms=20_000_000,
            max_per_swap_atoms=25_000_000,
        )
        == 20_000_000
    )
    assert (
        size_first_pass(
            wallet_usdc_atoms=5_000_000,
            remaining_daily_cap_atoms=20_000_000,
            max_per_swap_atoms=25_000_000,
        )
        == 5_000_000
    )


def test_size_first_pass_never_negative() -> None:
    assert (
        size_first_pass(
            wallet_usdc_atoms=5_000_000, remaining_daily_cap_atoms=-1, max_per_swap_atoms=25_000_000
        )
        == 0
    )


def test_size_to_target_shrinks_to_what_is_needed() -> None:
    # price: 1 USDC atom -> ~6.84 SOL-lamport-atoms in this fixture's ratio
    # (34215678 lamports / 5000000 usdc-atoms). Wallet at 0.55 SOL, target 0.60:
    # needs only 0.05 SOL = 50_000_000 lamports, well under the 25 USDC cap.
    resized = size_to_target(
        first_pass_usdc_atoms=25_000_000,
        quote_in_amount_atoms=5_000_000,
        quote_out_amount_atoms=34_215_678,
        wallet_lamports=550_000_000,
        target_lamports=600_000_000,
    )
    assert 0 < resized < 25_000_000, "the target needs less than the first-pass cap"


def test_size_to_target_returns_zero_once_the_target_is_already_met() -> None:
    resized = size_to_target(
        first_pass_usdc_atoms=25_000_000,
        quote_in_amount_atoms=5_000_000,
        quote_out_amount_atoms=34_215_678,
        wallet_lamports=600_000_000,
        target_lamports=600_000_000,
    )
    assert resized == 0


def test_size_to_target_never_exceeds_the_first_pass_cap() -> None:
    resized = size_to_target(
        first_pass_usdc_atoms=1_000,
        quote_in_amount_atoms=5_000_000,
        quote_out_amount_atoms=34_215_678,
        wallet_lamports=0,
        target_lamports=10_000_000_000,
    )
    assert resized == 1_000


def test_size_to_target_handles_a_zero_output_quote_without_dividing_by_zero() -> None:
    assert (
        size_to_target(
            first_pass_usdc_atoms=1_000,
            quote_in_amount_atoms=5_000_000,
            quote_out_amount_atoms=0,
            wallet_lamports=0,
            target_lamports=1,
        )
        == 0
    )


# ---------------------------------------------------------------- refusals
def test_route_empty_is_refused() -> None:
    assert classify_quote_refusal(_quote(route_labels=())) == "route_empty"
    assert classify_quote_refusal(_quote(out_amount=Decimal(0))) == "route_empty"


def test_price_impact_above_one_percent_is_refused() -> None:
    assert classify_quote_refusal(_quote(price_impact_pct=Decimal("0.011"))) == (
        "price_impact_above_cap"
    )


def test_a_good_quote_is_not_refused() -> None:
    assert classify_quote_refusal(_quote()) is None


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"enabled": False}, "disabled"),
        ({"live": False}, "live_disabled"),
        ({"has_signer": False}, "no_signer"),
        ({"kill_blocked": True}, "kill_switch_latched"),
        ({"wallet_sol": Decimal("0.5")}, "sol_above_floor"),
        (
            {"last_attempt_at": NOW - timedelta(seconds=10), "min_interval_s": 600.0},
            "min_interval_not_elapsed",
        ),
        ({"usdc_spent_today": Decimal("50")}, "daily_cap_reached"),
    ],
)
def test_should_attempt_refuses_each_gate_by_name(kwargs: dict[str, object], expected: str) -> None:
    base: dict[str, object] = {
        "enabled": True,
        "live": True,
        "has_signer": True,
        "kill_blocked": False,
        "wallet_sol": Decimal("0.1"),
        "floor": Decimal("0.30"),
        "last_attempt_at": None,
        "min_interval_s": 600.0,
        "now": NOW,
        "usdc_spent_today": Decimal("0"),
        "daily_cap": Decimal("50"),
    }
    base.update(kwargs)
    assert should_attempt(**base) == expected  # type: ignore[arg-type]


def test_should_attempt_allows_when_every_gate_passes() -> None:
    assert (
        should_attempt(
            enabled=True,
            live=True,
            has_signer=True,
            kill_blocked=False,
            wallet_sol=Decimal("0.1"),
            floor=Decimal("0.30"),
            last_attempt_at=NOW - timedelta(hours=1),
            min_interval_s=600.0,
            now=NOW,
            usdc_spent_today=Decimal("0"),
            daily_cap=Decimal("50"),
        )
        is None
    )


# ------------------------------------------------------------- fix B: quote
_ASK = {
    "input_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "output_mint": "So11111111111111111111111111111111111111112",
    "amount_atoms": 5_000_000,
    "slippage_bps": 50,
}


def test_a_quote_that_matches_the_request_is_valid() -> None:
    assert validate_quote(_quote(), **_ASK) is None  # type: ignore[arg-type]


def test_the_real_quote_threshold_is_out_amount_times_one_minus_slippage_floored() -> None:
    # 18/09/2026 capture: outAmount 9487602, slippageBps 50 -> Jupiter said 9440164
    # (9440163.99 rounded up); the rule accepts anything >= the floor, 9440163.
    real = _quote(
        in_amount=Decimal(1_000_000),
        out_amount=Decimal(9_487_602),
        other_amount_threshold=Decimal(9_440_164),
        price_impact_pct=Decimal(0),
    )
    assert validate_quote(real, **{**_ASK, "amount_atoms": 1_000_000}) is None  # type: ignore[arg-type]
    short = _quote(
        in_amount=Decimal(1_000_000),
        out_amount=Decimal(9_487_602),
        other_amount_threshold=Decimal(9_440_162),
    )
    assert validate_quote(short, **{**_ASK, "amount_atoms": 1_000_000}) == (  # type: ignore[arg-type]
        "quote_mismatch:other_amount_threshold"
    )


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"in_amount": Decimal("21330000")}, "quote_mismatch:in_amount"),
        ({"input_mint": "So11111111111111111111111111111111111111112"}, "quote_mismatch:mints"),
        ({"output_mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}, "quote_mismatch:mints"),
        ({"slippage_bps": 10_000}, "quote_mismatch:slippage_bps"),
        ({"other_amount_threshold": Decimal(1)}, "quote_mismatch:other_amount_threshold"),
    ],
)
def test_a_quote_that_drifts_from_the_request_is_refused_by_name(
    overrides: dict[str, object], expected: str
) -> None:
    assert validate_quote(_quote(**overrides), **_ASK) == expected  # type: ignore[arg-type]


# ----------------------------------------------------------- fix E: target
def test_a_target_below_the_wallet_ceiling_is_kept() -> None:
    assert effective_sol_target(
        configured_target_sol=Decimal("0.60"),
        wallet_max_sol=Decimal("0.72"),
        max_sol_per_trade=Decimal("0.02"),
    ) == (Decimal("0.60"), None)


def test_a_target_above_the_wallet_ceiling_is_capped_and_named() -> None:
    assert effective_sol_target(
        configured_target_sol=Decimal("1.0"),
        wallet_max_sol=Decimal("0.72"),
        max_sol_per_trade=Decimal("0.02"),
    ) == (Decimal("0.70"), "target_above_wallet_max")


# ----------------------------------------- fix A (2): simulated balances
_BAL = {
    "usdc_before_atoms": 21_330_000,
    "usdc_after_atoms": 20_330_000,
    "usdc_in_atoms": 1_000_000,
    "sol_before_lamports": 680_000_000,
    "sol_after_lamports": 689_380_000,  # + 9_440_164 threshold - ~60_000 fees
    "min_out_lamports": 9_440_164,
}


def test_a_simulation_that_spends_exactly_the_request_passes() -> None:
    assert check_simulated_balances(**_BAL) is None


def test_a_simulation_that_drains_more_usdc_than_requested_is_refused() -> None:
    assert check_simulated_balances(**{**_BAL, "usdc_after_atoms": 0}) == (
        "simulation_usdc_overspent"
    )


def test_a_simulation_that_hands_back_less_sol_than_the_threshold_is_refused() -> None:
    assert check_simulated_balances(**{**_BAL, "sol_after_lamports": 679_000_000}) == (
        "simulation_sol_short"
    )
