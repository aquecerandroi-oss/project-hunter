"""T4.67b — the launch admission profile (``docs/RISK_ENGINE_MEME.md``, "Perfil de
lançamento"): every skipped check is **recorded** as ``skipped`` with its reason
(never labelled ``passed``), the relaxed checks keep their refusals, the kept
checks refuse exactly as in the full profile, the launch's own open cap binds by
name, the ticket is the request's ceiling and the ``processed`` quote is admitted
only in this profile.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import (
    REFUSAL_NAMES,
    CheckState,
    CurveState,
    MemeContext,
    MemeDecision,
    MemeKillSwitchInputs,
    MemeLaunchProfile,
    OpenMemePosition,
    PendingMemeIntent,
    evaluate_meme_entry,
)
from hunter_risk_meme.decision import MemeCheck, skipped
from hunter_risk_meme.profile import LAUNCH_RELAXED_CHECKS, LAUNCH_SKIPPED_CHECKS

from .factories import AS_OF, FEE_PCT, INITIAL_REAL, context, curve, limits, proposal, wallet
from .factories import decide as full_decide
from .test_checks_table import CHECK_NAMES

pytestmark = pytest.mark.unit

OTHER = "So11111111111111111111111111111111111111112"
LAUNCH = MemeLaunchProfile(
    ticket_sol=Decimal("0.01"),
    max_open=2,
    max_participation_pct=Decimal("0.10"),
    max_token_age_s=5,
)


def _launch_curve(**over: Any) -> CurveState:
    """A curve one second old: virgin reserves plus a 0,5 SOL dev buy, read ``processed``."""
    base: dict[str, Any] = {
        "virtual_sol_reserves": 30_500_000_000,
        "virtual_token_reserves": 1_060_000_000_000_000,
        "real_sol_reserves": 500_000_000,
        "real_token_reserves": INITIAL_REAL - 13_000_000_000_000,
        "commitment": "processed",
        "observed_at": AS_OF - timedelta(milliseconds=300),
    }
    base.update(over)
    return curve(**base)


def _launch_context(**over: Any) -> MemeContext:
    """What the executor can know at t+1 s: the age from the proposal's own stamp,
    the curve's real SOL as the whole life's volume, nothing about holders,
    bundles or the creator's flow."""
    base: dict[str, Any] = {
        "token_created_at": AS_OF - timedelta(seconds=1),
        "token_age_source": "meme_proposals.reasons[0].created_at",
        "organic_volume_1m_sol": Decimal("0.5"),
        "volume_ts": AS_OF - timedelta(milliseconds=300),
        "volume_window_complete": True,
        "bundled_share_pct": None,
        "top10_share_pct": None,
        "holder_denominator_valid": None,
        "creator_net_sol": None,
    }
    base.update(over)
    return context(**base)


def _desk_position(i: int) -> OpenMemePosition:
    return OpenMemePosition(
        position_id=f"d{i}",
        mint=OTHER,
        sol_spent=Decimal("0.05"),
        token_amount=1,
        mark_sol=Decimal("0.05"),
    )


def _launch_position(i: int) -> OpenMemePosition:
    return OpenMemePosition(
        position_id=f"l{i}",
        mint=OTHER,
        sol_spent=Decimal("0.01"),
        token_amount=10,
        mark_sol=Decimal("0.01"),
        lane="launch",
    )


def decide(**over: Any) -> MemeDecision:
    kwargs: dict[str, Any] = {
        "p": proposal(requested_sol=Decimal("0.01"), mode="live"),
        "w": wallet(),
        "lim": limits(min_trade_sol=Decimal("0.02")),
        "c": _launch_curve(),
        "ctx": _launch_context(),
        "ks": MemeKillSwitchInputs(),
        "launch": LAUNCH,
    }
    kwargs.update(over)
    return evaluate_meme_entry(
        kwargs["p"],
        kwargs["w"],
        kwargs["lim"],
        kwargs["c"],
        kwargs["ctx"],
        kwargs["ks"],
        live_enabled=True,
        curve_fee_pct=FEE_PCT,
        creates_ata=True,
        launch=kwargs["launch"],
    )


def _check(decision: MemeDecision, name: str) -> MemeCheck:
    return next(c for c in decision.checks if c.name == name)


def test_the_launch_case_is_approved_with_every_check_recorded() -> None:
    decision = decide()
    assert decision.approved, decision.refusals
    assert tuple(c.name for c in decision.checks) == (*CHECK_NAMES, "launch_open_cap")
    assert decision.profile == "launch"
    assert decision.sizing is not None and decision.sizing.sol_final == Decimal("0.01")
    assert decision.sizing.binding_constraint == "requested"
    assert "launch_ticket" in decision.sizing.tied_limits


def test_every_skipped_check_is_recorded_as_skipped_with_its_reason_never_as_passed() -> None:
    decision = decide()
    assert set(LAUNCH_SKIPPED_CHECKS) == {
        "creator_behaviour",
        "bundled_share",
        "top10_share",
        "conviction",
    }
    for name, why in LAUNCH_SKIPPED_CHECKS.items():
        recorded = _check(decision, name)
        assert recorded.state is CheckState.SKIPPED, name
        assert recorded.passed is True, "a skip does not block the approval"
        assert recorded.refusal is None
        assert recorded.message == f"skipped:launch:{why}"
    for name in LAUNCH_RELAXED_CHECKS:
        relaxed = _check(decision, name)
        assert relaxed.state is CheckState.PASSED, f"{name} is relaxed, not skipped"
        assert "launch:" in relaxed.message, f"{name} says it ran under the launch rule"
    payload = decision.to_jsonable()
    assert payload["profile"] == "launch"
    states = {c["name"]: c["state"] for c in payload["checks"]}
    assert states["creator_behaviour"] == "skipped" and states["conviction"] == "skipped"


def test_the_full_profile_is_unchanged_without_a_launch_profile() -> None:
    decision = full_decide()
    assert decision.profile == "full"
    assert tuple(c.name for c in decision.checks) == CHECK_NAMES
    assert all(c.state is not CheckState.SKIPPED for c in decision.checks)
    assert all("launch" not in c.message for c in decision.checks)
    assert decision.to_jsonable()["profile"] == "full"


def test_a_skipped_check_cannot_carry_a_refusal_and_needs_a_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        skipped("x", "")
    with pytest.raises(ValueError, match="refusal"):
        MemeCheck(name="x", state=CheckState.SKIPPED, refusal="nope", message="why")


# ---- relaxed checks keep their refusals ---------------------------------------------


def test_the_processed_quote_is_admitted_only_in_the_launch_profile() -> None:
    assert decide().approved
    full = full_decide(
        p=proposal(requested_sol=Decimal("0.01"), mode="live"),
        c=_launch_curve(),
        ctx=_launch_context(),
        live_enabled=True,
    )
    assert "commitment_too_weak" in full.refusals
    assert "state_freshness" in LAUNCH_RELAXED_CHECKS


def test_a_stale_or_undated_or_skewed_launch_quote_still_refuses() -> None:
    stale = decide(c=_launch_curve(observed_at=AS_OF - timedelta(seconds=6)))
    assert "curve_state_stale" in stale.refusals
    assert "curve_state_undated" in decide(c=_launch_curve(observed_at=None)).refusals
    skewed = decide(c=_launch_curve(observed_at=AS_OF + timedelta(seconds=3)))
    assert "curve_state_clock_skew" in skewed.refusals


def test_token_age_has_no_minimum_but_keeps_the_launch_maximum_and_the_provenance() -> None:
    fresh = decide(ctx=_launch_context(token_created_at=AS_OF - timedelta(milliseconds=200)))
    assert fresh.approved, fresh.refusals
    late = decide(ctx=_launch_context(token_created_at=AS_OF - timedelta(seconds=6)))
    assert "token_too_old" in late.refusals
    assert _check(late, "token_age").limit == Decimal(5), "the launch's maximum, not 600 s"
    unknown = decide(ctx=_launch_context(token_created_at=None, token_age_source=None))
    assert "token_age_unknown" in unknown.refusals


def test_curve_progress_has_no_minimum_but_a_born_full_curve_still_refuses() -> None:
    virgin = decide(c=_launch_curve(real_token_reserves=INITIAL_REAL))
    assert virgin.approved, virgin.refusals
    assert "curve_complete" in decide(c=_launch_curve(complete=True)).refusals
    born_full = decide(c=_launch_curve(real_token_reserves=INITIAL_REAL // 4))
    assert "progress_above_window" in born_full.refusals
    no_denominator = decide(ctx=_launch_context(initial_real_token_reserves=None))
    assert "progress_denominator_missing" in no_denominator.refusals


# ---- kept checks refuse exactly as before -------------------------------------------


@pytest.mark.parametrize(
    ("refusal", "over"),
    [
        ("kill_switch_blocked", {"ks": MemeKillSwitchInputs(system=KillSwitchState.EMERGENCY)}),
        ("daily_loss_cap_latched", {"ks": MemeKillSwitchInputs(daily_loss_latched=True)}),
        ("wallet_inactive", {"w": wallet(is_active=False)}),
        ("marks_incomplete", {"w": wallet(marks_complete=False)}),
        (
            "program_not_allowed",
            {"p": proposal(requested_sol=Decimal("0.01"), mode="live", program=OTHER)},
        ),
        ("identity_mismatch", {"c": _launch_curve(mint=OTHER)}),
        ("mayhem_state_unknown", {"c": _launch_curve(is_mayhem_mode=True)}),
        (
            "rug_cooldown_active",
            {"ctx": _launch_context(rug_cooldown_until=AS_OF + timedelta(seconds=60))},
        ),
        ("wallet_over_max_sol", {"w": wallet(sol_balance=Decimal("2.5"))}),
        (
            "daily_loss_cap_reached",
            {"w": wallet(sol_balance=Decimal("0.8"), day_start_sol_equity=Decimal("1.0"))},
        ),
        (
            "priority_fee_above_cap",
            {
                "p": proposal(
                    requested_sol=Decimal("0.01"), mode="live", priority_fee_sol=Decimal("0.0006")
                )
            },
        ),
        ("volume_unavailable", {"ctx": _launch_context(organic_volume_1m_sol=None)}),
        (
            "participation_above_cap",
            {"ctx": _launch_context(organic_volume_1m_sol=Decimal("0.05"))},
        ),
        ("price_impact_above_cap", {"lim": limits(max_price_impact_pct=Decimal("0.0000001"))}),
        ("insufficient_sol", {"w": wallet(sol_balance=Decimal("0.011"))}),
    ],
)
def test_each_kept_check_still_refuses_by_name(refusal: str, over: dict[str, Any]) -> None:
    decision = decide(**over)
    assert not decision.approved
    assert refusal in decision.refusals, decision.refusals


def test_the_live_gate_refuses_the_launch_with_the_live_flag_off() -> None:
    """The launch lane's proposal is always ``live`` (the executor builds it so);
    with ``ENABLE_MEME_LIVE_TRADING`` off the engine refuses ``meme_live_disabled``."""
    off = evaluate_meme_entry(
        proposal(requested_sol=Decimal("0.01"), mode="live"),
        wallet(),
        limits(min_trade_sol=Decimal("0.02")),
        _launch_curve(),
        _launch_context(),
        MemeKillSwitchInputs(),
        live_enabled=False,
        curve_fee_pct=FEE_PCT,
        launch=LAUNCH,
    )
    assert "meme_live_disabled" in off.refusals


def test_the_daily_loss_counts_the_treasury_inflow_in_the_launch_profile_too() -> None:
    refilled = wallet(
        sol_balance=Decimal("1.0"),
        day_start_sol_equity=Decimal("1.0"),
        treasury_inflow_today_sol=Decimal("0.25"),
    )
    assert "daily_loss_cap_reached" in decide(w=refilled).refusals


# ---- the launch's own cap, ticket and floor --------------------------------------------


def test_the_launch_open_cap_counts_only_launch_positions_and_pending_launch_intents() -> None:
    ok = decide(w=wallet(positions=(_desk_position(1), _desk_position(2))))
    assert ok.approved, ok.refusals
    cap = _check(ok, "launch_open_cap")
    assert cap.value == Decimal(0) and cap.limit == Decimal(2)
    full = decide(w=wallet(positions=(_launch_position(1), _launch_position(2))))
    assert "launch_max_open_reached" in full.refusals
    pending = wallet(
        positions=(_launch_position(1),),
        pending_intents=(
            PendingMemeIntent(
                proposal_id="q", mint=OTHER, reserved_sol=Decimal("0.011"), lane="launch"
            ),
        ),
    )
    assert "launch_max_open_reached" in decide(w=pending).refusals
    assert "launch_max_open_reached" in REFUSAL_NAMES


def test_the_global_cap_still_binds_when_desk_positions_fill_it() -> None:
    three = wallet(positions=tuple(_desk_position(i) for i in range(3)))
    assert "max_open_positions" in decide(w=three).refusals


def test_the_ticket_is_the_ceiling_and_never_above_the_trade_cap() -> None:
    asked_more = decide(p=proposal(requested_sol=Decimal("0.06"), mode="live"))
    assert asked_more.sizing is not None and asked_more.sizing.sol_final == Decimal("0.01")
    assert asked_more.sizing.binding_constraint == "launch_ticket"
    big_ticket = decide(
        p=proposal(requested_sol=Decimal("0.06"), mode="live"),
        launch=LAUNCH.model_copy(update={"ticket_sol": Decimal("0.5")}),
    )
    assert big_ticket.sizing is not None and big_ticket.sizing.sol_final == Decimal("0.05")
    assert big_ticket.sizing.binding_constraint == "trade_cap"


def test_the_floor_follows_the_ticket_and_dust_still_refuses() -> None:
    sizing = _check(decide(), "sizing")
    assert sizing.passed and sizing.limit == Decimal("0.01")
    assert "launch:" in sizing.message
    starved = decide(w=wallet(sol_balance=Decimal("0.0105")))
    assert not starved.approved
    assert {"insufficient_sol", "below_min_sol"} & set(starved.refusals)


def test_the_profile_is_refused_at_construction_when_its_numbers_are_absurd() -> None:
    with pytest.raises(ValueError):
        MemeLaunchProfile(
            ticket_sol=Decimal(0),
            max_open=2,
            max_participation_pct=Decimal("0.1"),
            max_token_age_s=5,
        )
    with pytest.raises(ValueError):
        MemeLaunchProfile(
            ticket_sol=Decimal("0.01"),
            max_open=0,
            max_participation_pct=Decimal("0.1"),
            max_token_age_s=5,
        )
    with pytest.raises(ValueError):
        MemeLaunchProfile(
            ticket_sol=Decimal("0.01"),
            max_open=2,
            max_participation_pct=Decimal("1.5"),
            max_token_age_s=5,
        )
