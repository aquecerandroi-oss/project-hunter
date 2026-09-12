"""§4 as a table: every check has a passing and a failing case, every refusal name
of the doctrine is produced by at least one case, and every check is recorded
even after the first refusal.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import (
    REFUSAL_NAMES,
    MemeKillSwitchInputs,
    OpenMemePosition,
    PendingMemeIntent,
)

from .factories import (
    AS_OF,
    MINT,
    context,
    curve,
    decide,
    limits,
    proposal,
    wallet,
)

pytestmark = pytest.mark.unit

CHECK_NAMES = (
    "kill_switch",
    "wallet_status",
    "live_gate",
    "program_allowed",
    "quote_supported",
    "identity_match",
    "state_freshness",
    "token_age",
    "curve_progress",
    "creator_behaviour",
    "bundled_share",
    "top10_share",
    "mayhem_policy",
    "rug_history",
    "duplicate_position",
    "concurrent_positions",
    "wallet_cap",
    "daily_loss",
    "slippage_cap",
    "fee_caps",
    "participation",
    "price_impact",
    "sizing",
    "sol_available",
    "exposure_after",
)

OTHER = "So11111111111111111111111111111111111111112"
POSITION = OpenMemePosition(
    position_id="pos",
    mint=MINT,
    sol_spent=Decimal("0.05"),
    token_amount=10,
    mark_sol=Decimal("0.05"),
)

FAILING = {
    "kill_switch_blocked": {"ks": MemeKillSwitchInputs(system=KillSwitchState.TRADING_DISABLED)},
    "daily_loss_cap_latched": {"ks": MemeKillSwitchInputs(daily_loss_latched=True)},
    "wallet_inactive": {"w": wallet(is_active=False)},
    "agent_disabled": {"p": proposal(agent_enabled=False)},
    "marks_incomplete": {"w": wallet(marks_complete=False)},
    "meme_live_disabled": {"p": proposal(mode="live"), "live_enabled": False},
    "program_not_allowed": {"p": proposal(program=OTHER)},
    "unsupported_quote": {"p": proposal(quote="USDC")},
    "identity_mismatch": {"c": curve(mint=OTHER)},
    "curve_state_undated": {"c": curve(observed_at=None)},
    "curve_state_stale": {"c": curve(observed_at=AS_OF - timedelta(seconds=6))},
    "curve_state_clock_skew": {"c": curve(observed_at=AS_OF + timedelta(seconds=3))},
    "commitment_too_weak": {"c": curve(commitment="processed")},
    "token_too_young": {"ctx": context(token_created_at=AS_OF - timedelta(seconds=10))},
    "token_too_old": {"ctx": context(token_created_at=AS_OF - timedelta(seconds=601))},
    "token_age_unknown": {"ctx": context(token_age_source=None)},
    "progress_below_window": {"c": curve(real_token_reserves=793_100_000_000_000 - 1)},
    "progress_above_window": {"c": curve(real_token_reserves=793_100_000_000_000 // 4)},
    "curve_complete": {"c": curve(complete=True)},
    "progress_denominator_missing": {"ctx": context(initial_real_token_reserves=None)},
    "creator_net_seller": {"ctx": context(creator_net_sol=Decimal("-0.5"))},
    "creator_flow_unknown": {"ctx": context(creator_net_sol=None)},
    "bundled_share_above_cap": {"ctx": context(bundled_share_pct=Decimal("0.21"))},
    "bundled_share_unmeasurable": {"ctx": context(bundled_share_pct=None)},
    "top10_share_above_cap": {"ctx": context(top10_share_pct=Decimal("0.26"))},
    "top10_share_unknown": {"ctx": context(top10_share_pct=None)},
    "holder_denominator_invalid": {"ctx": context(holder_denominator_valid=False)},
    "mayhem_not_allowed": {
        "c": curve(is_mayhem_mode=True),
        "ctx": context(mayhem_agent_state_known=True, mayhem_policy_approved=False),
    },
    "mayhem_state_unknown": {"c": curve(is_mayhem_mode=True)},
    "token_rugged_no_reentry": {"ctx": context(mint_rugged=True)},
    "rug_cooldown_active": {"ctx": context(rug_cooldown_until=AS_OF + timedelta(seconds=60))},
    "duplicate_position": {"w": wallet(positions=(POSITION,))},
    "max_open_positions": {
        "w": wallet(
            pending_intents=tuple(
                PendingMemeIntent(proposal_id=f"q{i}", mint=OTHER, reserved_sol=Decimal("0.01"))
                for i in range(3)
            )
        )
    },
    "wallet_over_max_sol": {"w": wallet(sol_balance=Decimal("2.5"))},
    "wallet_unrecognized_holdings": {"w": wallet(unrecognized_holdings=(OTHER,))},
    "daily_loss_cap_reached": {
        "w": wallet(sol_balance=Decimal("0.8"), day_start_sol_equity=Decimal("1.0"))
    },
    "slippage_above_cap": {"p": proposal(max_slippage_pct=Decimal("0.02"))},
    "priority_fee_above_cap": {"p": proposal(priority_fee_sol=Decimal("0.003"))},
    "jito_tip_above_cap": {"p": proposal(jito_tip_sol=Decimal("0.002"))},
    "volume_unavailable": {"ctx": context(organic_volume_1m_sol=None)},
    "volume_window_incomplete": {"ctx": context(volume_window_complete=False)},
    "participation_above_cap": {"ctx": context(organic_volume_1m_sol=Decimal("0.05"))},
    "price_impact_above_cap": {"lim": limits(max_price_impact_pct=Decimal("0.00001"))},
    "below_min_sol": {"w": wallet(sol_balance=Decimal("0.0015"))},
    "insufficient_sol": {
        "w": wallet(sol_balance=Decimal("0.0015"), rent_reserved_sol=Decimal("0.001"))
    },
    "exposure_after_above_cap": {
        "lim": limits(
            max_exposure_per_mint_sol=Decimal("0.0009"), max_sol_per_trade=Decimal("0.001")
        )
    },
}


def test_the_healthy_case_passes_every_check_and_is_approved() -> None:
    decision = decide()
    assert decision.approved, decision.refusals
    assert tuple(c.name for c in decision.checks) == CHECK_NAMES
    assert decision.sizing is not None and decision.sizing.sol_final > 0


@pytest.mark.parametrize("refusal", sorted(FAILING))
def test_each_refusal_is_produced_by_its_case(refusal: str) -> None:
    decision = decide(**FAILING[refusal])  # type: ignore[arg-type]
    assert not decision.approved
    assert refusal in decision.refusals, decision.refusals


def test_every_refusal_name_of_the_doctrine_has_a_case() -> None:
    assert set(FAILING) == set(REFUSAL_NAMES)


def test_every_check_is_recorded_even_after_the_first_refusal() -> None:
    decision = decide(ks=MemeKillSwitchInputs(system=KillSwitchState.EMERGENCY))
    assert decision.refusals[0] == "kill_switch_blocked"
    assert tuple(c.name for c in decision.checks) == CHECK_NAMES
    assert decision.sizing is not None, "the sizing still runs so the panel shows the size"


def test_a_missing_volume_cascades_into_unavailable_not_zero() -> None:
    decision = decide(ctx=context(organic_volume_1m_sol=None))
    states = {c.name: c.state for c in decision.checks}
    assert states["participation"] == "unavailable"
    assert states["price_impact"] == "unavailable"
    assert states["sizing"] == "unavailable"
    assert decision.sizing is None


def test_a_float_is_refused_at_construction() -> None:
    with pytest.raises(TypeError, match="float"):
        proposal(requested_sol=0.05)  # type: ignore[arg-type]


def test_the_decision_round_trips_through_json() -> None:
    decision = decide()
    payload = decision.to_jsonable()
    assert payload["approved"] is True
    assert payload["sizing"]["binding_constraint"] == decision.sizing.binding_constraint  # type: ignore[union-attr]
    assert isinstance(payload["sizing"]["sol_final"], str)
