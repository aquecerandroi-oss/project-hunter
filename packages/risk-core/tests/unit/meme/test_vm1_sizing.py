"""VM1 — sizing: the minimum of the ceilings, the binding constraint published,
stable tie-break, two distinct counterfactuals, the multiplier on the final
size and the minimum revalidated after it (§5, §11)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import CAP_ORDER, MemeKillSwitchInputs, OpenMemePosition, PendingMemeIntent

from .factories import (
    context,
    decide,
    limits,
    proposal,
    wallet,
)

pytestmark = pytest.mark.unit

OTHER = "So11111111111111111111111111111111111111112"


def test_the_requested_ceiling_wins_when_it_is_the_smallest() -> None:
    decision = decide(p=proposal(requested_sol=Decimal("0.01")))
    assert decision.approved and decision.sizing is not None
    assert decision.sizing.binding_constraint == "requested"
    assert decision.sizing.sol_final == Decimal("0.01")
    assert decision.sizing.tied_limits == ()


def test_the_trade_cap_bites_a_larger_request() -> None:
    decision = decide(p=proposal(requested_sol=Decimal("0.5")))
    assert decision.approved and decision.sizing is not None
    assert decision.sizing.binding_constraint == "trade_cap"
    assert decision.sizing.sol_final == Decimal("0.05")


def test_five_positions_of_0_05_do_not_fit_under_a_daily_cap_of_0_20() -> None:
    """VM2's arithmetic in the pure engine: open positions commit their whole spend."""
    open_positions = tuple(
        OpenMemePosition(
            position_id=f"o{i}",
            mint=OTHER,
            sol_spent=Decimal("0.05"),
            token_amount=1,
            mark_sol=Decimal("0.05"),
        )
        for i in range(3)
    )
    pending = (PendingMemeIntent(proposal_id="q", mint=OTHER, reserved_sol=Decimal("0.05")),)
    decision = decide(
        w=wallet(positions=open_positions, pending_intents=pending, sol_balance=Decimal("0.8")),
        lim=limits(max_open_positions=10),
    )
    assert decision.sizing is not None
    assert decision.sizing.binding_constraint == "daily_cap"
    assert decision.sizing.sol_final == Decimal("0")
    assert "below_min_sol" in decision.refusals


def test_ties_are_broken_in_the_declared_order_and_published() -> None:
    decision = decide(
        p=proposal(requested_sol=Decimal("0.05")), lim=limits(max_sol_per_trade=Decimal("0.05"))
    )
    assert decision.sizing is not None
    assert decision.sizing.binding_constraint == "requested"
    assert "trade_cap" in decision.sizing.tied_limits
    assert "mint_cap" in decision.sizing.tied_limits
    assert CAP_ORDER.index("requested") < CAP_ORDER.index("trade_cap")


def test_the_warning_multiplier_acts_on_the_final_size() -> None:
    warning = decide(ks=MemeKillSwitchInputs(wallet=KillSwitchState.WARNING))
    plain = decide()
    assert warning.sizing is not None and plain.sizing is not None
    assert warning.sizing.kill_switch_multiplier == Decimal("0.5")
    assert warning.sizing.sol_final == plain.sizing.sol_final / 2
    assert warning.sizing.size_without_multipliers.sol == plain.sizing.sol_final


def test_the_two_counterfactuals_are_distinct() -> None:
    decision = decide(ctx=context(organic_volume_1m_sol=Decimal("2")))  # 1 % of 2 = 0.02
    assert decision.sizing is not None
    assert decision.sizing.binding_constraint == "participation"
    assert decision.sizing.sol_final == Decimal("0.02")
    assert decision.sizing.size_without_participation.sol == Decimal("0.05")
    assert decision.sizing.size_without_multipliers.sol == Decimal("0.02")


def test_a_reduced_size_below_the_minimum_is_rejected_never_rounded_up() -> None:
    decision = decide(
        p=proposal(requested_sol=Decimal("0.0015")),
        ks=MemeKillSwitchInputs(wallet=KillSwitchState.WARNING),
    )
    assert decision.sizing is not None
    assert decision.sizing.sol_final == Decimal("0.00075")
    assert "below_min_sol" in decision.refusals


def test_impact_is_exact_from_the_reserves() -> None:
    decision = decide(
        p=proposal(requested_sol=Decimal("5")),
        lim=limits(max_sol_per_trade=Decimal("1"), max_exposure_per_mint_sol=Decimal("1")),
    )
    assert decision.sizing is not None
    # 0.5 % of 36.4 SOL virtual, pre-fee ⇒ 0.182 × 1.0125 total.
    assert decision.sizing.binding_constraint == "impact"
    assert decision.sizing.sol_final == Decimal("0.184275")
    assert decision.sizing.price_impact_pct == Decimal("0.005")


def test_max_sol_cost_carries_the_slippage_into_the_instruction() -> None:
    decision = decide(p=proposal(requested_sol=Decimal("0.01"), max_slippage_pct=Decimal("0.01")))
    assert decision.sizing is not None
    assert decision.sizing.max_sol_cost_sol == Decimal("0.0101")


def test_available_sol_is_net_of_reservations_rent_and_fixed_costs() -> None:
    w = wallet(
        sol_balance=Decimal("0.05"),
        day_start_sol_equity=Decimal("0.05"),
        peak_sol_equity=Decimal("0.05"),
        pending_intents=(
            PendingMemeIntent(proposal_id="q", mint=OTHER, reserved_sol=Decimal("0.02")),
        ),
        rent_reserved_sol=Decimal("0.01"),
    )
    decision = decide(w=w, lim=limits(max_open_positions=5))
    assert decision.sizing is not None
    assert decision.sizing.binding_constraint == "available"
    expected = Decimal("0.02") - decision.sizing.fixed_costs_sol
    assert decision.sizing.sol_final == expected
