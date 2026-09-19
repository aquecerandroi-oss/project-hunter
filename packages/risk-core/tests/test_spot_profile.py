"""T4.74-2 — the ``spot`` admission profile (``docs/RISK_ENGINE_MEME.md`` §19).

Every refusal of the profile appears at least once in the table below; the
passing case binds by ``requested`` (the ticket); an open ``lane = spot``
position takes a global slot and shrinks ``daily_cap``; every check keeps its
decomposition; no float exists anywhere in the module.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk_meme import (
    MEME_PAPER_V0,
    SPOT_CAP_ORDER,
    SPOT_CHECK_NAMES,
    SPOT_LANE,
    SPOT_REFUSAL_NAMES,
    CheckState,
    MemeDecision,
    MemeKillSwitchInputs,
    MemeLimits,
    MemeSpotProfile,
    MemeWalletState,
    OpenMemePosition,
    PendingMemeIntent,
    SpotSignalInputs,
    evaluate_spot_entry,
)

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 19, 15, 30, tzinfo=UTC)  # 12:30 BRT
DAY_START = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)  # 00:00 BRT
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
JUP = "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
TICKET = Decimal("0.05")

PROFILE = MemeSpotProfile(
    ticket_sol=TICKET,
    max_open=3,
    max_parity_pct=Decimal("0.03"),
    max_impact_pct=Decimal("0.005"),
    max_cost_r=Decimal("0.5"),
    max_signal_age_s=180,
)


def limits(**over: Any) -> MemeLimits:
    base = {**MEME_PAPER_V0.model_dump(), "max_open_positions": 5}
    return MEME_PAPER_V0.model_validate({**base, **over})


def wallet(balance: str = "1.0", **over: Any) -> MemeWalletState:
    """A wallet that starts the day at ``balance`` (cash = day start = peak), no positions."""
    sol = Decimal(balance)
    base: dict[str, Any] = {
        "wallet_id": "w1",
        "as_of": AS_OF,
        "sol_balance": sol,
        "day_start_sol_equity": sol,
        "peak_sol_equity": sol,
        "day_start_utc": DAY_START,
    }
    base.update(over)
    return MemeWalletState(**base)


def signal(**over: Any) -> SpotSignalInputs:
    # ref 2.00, stop 1.96 (2 %), target 2.06 (3 % = 1.5 R): the R63 geometry.
    base: dict[str, Any] = {
        "signal_id": "s1",
        "market_symbol": "WIFUSDT",
        "mint": WIF,
        "reference_price": Decimal("2.00"),
        "stop_price": Decimal("1.96"),
        "target1_price": Decimal("2.06"),
        "emitted_at": AS_OF - timedelta(seconds=30),
        "expires_at": AS_OF + timedelta(seconds=90),
        "parity_ratio": Decimal("1.01"),
        "quote_impact_pct": Decimal("0.001"),
        "priority_fee_sol": Decimal("0.0001"),
    }
    base.update(over)
    return SpotSignalInputs(**base)


def spot_position(mint: str = BONK, sol: str = "0.05") -> OpenMemePosition:
    return OpenMemePosition(
        position_id=f"sp-{mint[:4]}",
        mint=mint,
        sol_spent=Decimal(sol),
        token_amount=1_000_000,
        mark_sol=Decimal(sol),
        lane=SPOT_LANE,
    )


def meme_position(mint: str, sol: str = "0.05") -> OpenMemePosition:
    return OpenMemePosition(
        position_id=f"mp-{mint[:4]}",
        mint=mint,
        sol_spent=Decimal(sol),
        token_amount=1_000_000,
        mark_sol=Decimal(sol),
    )


def decide(
    *,
    w: MemeWalletState | None = None,
    lim: MemeLimits | None = None,
    prof: MemeSpotProfile = PROFILE,
    sig: SpotSignalInputs | None = None,
    ks: MemeKillSwitchInputs | None = None,
    now: datetime | None = None,
) -> MemeDecision:
    return evaluate_spot_entry(
        w or wallet(), lim or limits(), prof, sig or signal(), ks or MemeKillSwitchInputs(), now
    )


def by_name(decision: MemeDecision, name: str) -> Any:
    return next(c for c in decision.checks if c.name == name)


def test_the_healthy_signal_is_approved_at_the_ticket_binding_by_requested() -> None:
    decision = decide()
    assert decision.approved, decision.refusals
    assert (decision.profile, decision.kind, decision.proposal_id) == ("spot", "entry", "s1")
    assert decision.mint == WIF
    assert tuple(c.name for c in decision.checks) == SPOT_CHECK_NAMES
    assert all(c.state is CheckState.PASSED for c in decision.checks)
    sizing = decision.sizing
    assert sizing is not None
    assert sizing.binding_constraint == "requested"
    assert sizing.sol_final == TICKET
    assert sizing.requested_sol == TICKET
    assert tuple(c.name for c in sizing.caps) == SPOT_CAP_ORDER
    assert sizing.kill_switch_multiplier == Decimal(1)
    # The row is serialisable exactly like the desk's (canonical JSON, no float).
    payload = decision.to_jsonable()
    assert payload["profile"] == "spot"
    assert payload["sizing"]["binding_constraint"] == "requested"


def test_every_check_keeps_its_decomposition() -> None:
    decision = decide()
    geometry = by_name(decision, "geometry_invalid")
    assert geometry.value == Decimal("0.02")  # stop_frac
    assert "target_frac=0.03" in geometry.message
    cost = by_name(decision, "cost_r")
    # 2 × (0.0001 + 0.000005) + 0.05 × (2 × 0.001 + 0.003) = 0.00021 + 0.00025; R = 0.05 × 0.02
    assert (cost.value, cost.limit) == (Decimal("0.46"), Decimal("0.5"))
    assert "est_cost_sol=0.00046" in cost.message and "r_unit_sol=0.001" in cost.message
    parity = by_name(decision, "parity")
    assert (parity.value, parity.limit) == (Decimal("0.01"), Decimal("0.03"))
    stale = by_name(decision, "signal_stale")
    assert (stale.value, stale.limit) == (Decimal(30), Decimal(180))
    assert stale.input_ts is not None


# --- the refusal table: every refusal name at least once ---
EMERGENCY = MemeKillSwitchInputs(system=KillSwitchState.EMERGENCY)
LATCHED = MemeKillSwitchInputs(daily_loss_latched=True)
WARNING = MemeKillSwitchInputs(wallet=KillSwitchState.WARNING)
PENDING_SPOT = PendingMemeIntent(proposal_id="i1", mint=JUP, reserved_sol=TICKET, lane=SPOT_LANE)
SPOT_FULL = wallet(
    positions=(spot_position(BONK), spot_position(WIF[:-1] + "Q")), pending_intents=(PENDING_SPOT,)
)
# loss 0, committed 0.16 ⇒ daily_cap 0.04 < 0.05 (no WARNING, so daily_cap binds)
COMMITTED = wallet(
    sol_balance=Decimal("0.84"), positions=(meme_position(JUP, "0.08"), meme_position(BONK, "0.08"))
)
# wallet cap 0.09 − 0.045 held = 0.045 < 0.05 (available 0.0478 is looser)
SMALL_LIMITS = limits(
    wallet_max_sol=Decimal("0.09"), max_sol_per_trade=TICKET, max_exposure_per_mint_sol=TICKET
)
SMALL_WALLET = wallet("0.05", positions=(meme_position(JUP, "0.045"),))
CASES: dict[str, tuple[str, dict[str, Any]]] = {
    "kill_switch_blocked": ("kill_switch", {"ks": EMERGENCY}),
    "daily_loss_cap_latched": ("kill_switch", {"ks": LATCHED}),
    "wallet_inactive": ("wallet_status", {"w": wallet(is_active=False)}),
    "marks_incomplete": ("wallet_status", {"w": wallet(marks_complete=False)}),
    # cash 0.79 against a 1.0 day start: −0.21 ≥ the 0.20 cap
    "daily_loss_cap_reached": ("daily_loss", {"w": wallet(sol_balance=Decimal("0.79"))}),
    "wallet_over_max_sol": ("wallet_cap", {"w": wallet(sol_balance=Decimal("2.5"))}),
    "wallet_unrecognized_holdings": ("wallet_cap", {"w": wallet(unrecognized_holdings=("X",))}),
    "max_open_positions": (
        "concurrent_positions",
        {
            "w": wallet(positions=(spot_position(BONK), meme_position(JUP))),
            "lim": limits(max_open_positions=2),
        },
    ),
    "spot_max_open_reached": ("spot1_open_cap", {"w": SPOT_FULL}),
    "duplicate_market": ("duplicate_market", {"sig": signal(open_spot_markets=("WIFUSDT",))}),
    "signal_stale": ("signal_stale", {"sig": signal(emitted_at=AS_OF - timedelta(seconds=181))}),
    "signal_clock_skew": ("signal_stale", {"sig": signal(emitted_at=AS_OF + timedelta(hours=1))}),
    "signal_expired": ("signal_expired", {"sig": signal(expires_at=AS_OF)}),
    "geometry_invalid": ("geometry_invalid", {"sig": signal(stop_price=Decimal("2.00"))}),
    "parity_above_cap": ("parity", {"sig": signal(parity_ratio=Decimal("0.96"))}),
    "parity_unavailable": (
        "parity",
        {"sig": signal(parity_ratio=None, parity_reason="market_price_unavailable")},
    ),
    "impact_above_cap": ("impact", {"sig": signal(quote_impact_pct=Decimal("0.006"))}),
    "impact_unavailable": ("impact", {"sig": signal(quote_impact_pct=None)}),
    # 2 × 0.000205 + 0.00025 = 0.00066 over R 0.001 = 0.66 > 0.5 (the design's own arithmetic).
    "cost_above_r_cap": ("cost_r", {"sig": signal(priority_fee_sol=Decimal("0.0002"))}),
    "cost_unavailable": ("cost_r", {"sig": signal(quote_impact_pct=None)}),
    "priority_fee_above_cap": ("fee_caps", {"sig": signal(priority_fee_sol=Decimal("0.003"))}),
    "below_ticket:daily_cap": ("sizing", {"w": COMMITTED}),
    "below_ticket:wallet_cap": ("sizing", {"lim": SMALL_LIMITS, "w": SMALL_WALLET}),
    "below_ticket:available": ("sizing", {"w": wallet("0.052")}),  # 0.052 − costs < 0.05
    "below_ticket:kill_switch_multiplier": ("sizing", {"ks": WARNING}),
    "sizing_unavailable": ("sizing", {"sig": signal(quote_impact_pct=None)}),
}


@pytest.mark.parametrize(("refusal", "case"), sorted(CASES.items()))
def test_each_refusal_is_produced_by_name(refusal: str, case: tuple[str, dict[str, Any]]) -> None:
    check_name, over = case
    decision = decide(**over)
    assert not decision.approved
    assert by_name(decision, check_name).refusal == refusal, decision.refusals
    assert (
        tuple(c.name for c in decision.checks) == SPOT_CHECK_NAMES
    )  # all recorded after a refusal


def test_the_table_covers_every_refusal_of_the_profile() -> None:
    static = {r for r in CASES if not r.startswith("below_ticket:")}
    assert static == set(SPOT_REFUSAL_NAMES)
    dynamic = {r.split(":", 1)[1] for r in CASES if r.startswith("below_ticket:")}
    assert dynamic == {"daily_cap", "wallet_cap", "available", "kill_switch_multiplier"}


def test_below_ticket_names_the_binding_constraint_and_publishes_the_caps() -> None:
    decision = decide(w=COMMITTED)
    sizing = decision.sizing
    assert sizing is not None
    assert (sizing.binding_constraint, sizing.binding_limit.sol) == ("daily_cap", Decimal("0.04"))
    assert sizing.sol_final == Decimal("0.04")
    assert by_name(decision, "sizing").refusal == "below_ticket:daily_cap"
    assert by_name(decision, "sizing").value == Decimal("0.04")
    assert by_name(decision, "sizing").limit == TICKET


def test_the_ticket_is_clamped_by_the_trade_cap_and_binds_as_requested() -> None:
    decision = decide(
        lim=limits(max_sol_per_trade=Decimal("0.03"), max_exposure_per_mint_sol=Decimal("0.03")),
        sig=signal(priority_fee_sol=Decimal("0.00005")),  # 0.00011 + 0.00015 over R 0.0006
    )
    assert decision.approved, decision.refusals
    sizing = decision.sizing
    assert sizing is not None
    assert sizing.requested_sol == Decimal("0.03")
    assert sizing.sol_final == Decimal("0.03")
    assert sizing.binding_constraint == "requested"
    assert sizing.tied_limits == ("trade_cap",)
    assert "clamped" in sizing.caps[0].detail


def test_an_open_spot_position_takes_a_global_slot_and_reduces_daily_cap() -> None:
    lim = limits(max_open_positions=2)
    one = decide(w=wallet(positions=(meme_position(JUP),)), lim=lim)
    assert one.approved, one.refusals
    assert by_name(one, "concurrent_positions").value == Decimal(1)
    two = decide(w=wallet(positions=(meme_position(JUP), spot_position(BONK))), lim=lim)
    assert by_name(two, "concurrent_positions").refusal == "max_open_positions"
    assert by_name(two, "concurrent_positions").value == Decimal(2)
    # daily_cap = 0.20 − loss 0 − committed (0.05 + 0.05) = 0.10 with both; 0.15 with one.
    sizing_one, sizing_two = one.sizing, two.sizing
    assert sizing_one is not None and sizing_two is not None
    assert next(c for c in sizing_one.caps if c.name == "daily_cap").sol == Decimal("0.15")
    assert next(c for c in sizing_two.caps if c.name == "daily_cap").sol == Decimal("0.10")
    assert by_name(two, "spot1_open_cap").value == Decimal(1)


def test_duplicate_market_also_sees_the_mint_held_by_any_lane() -> None:
    decision = decide(w=wallet(positions=(meme_position(WIF),)))
    dup = by_name(decision, "duplicate_market")
    assert dup.refusal == "duplicate_market"
    assert "mint_held" in dup.message
    pending = decide(sig=signal(pending_spot_markets=("WIFUSDT",)))
    assert by_name(pending, "duplicate_market").refusal == "duplicate_market"


def test_unavailable_inputs_refuse_by_name_and_are_recorded_unavailable() -> None:
    decision = decide(sig=signal(parity_ratio=None, parity_reason="sol_usd_unavailable"))
    parity = by_name(decision, "parity")
    assert parity.state is CheckState.UNAVAILABLE
    assert parity.refusal == "parity_unavailable"
    assert "sol_usd_unavailable" in parity.message
    assert parity.value is None
    impact = decide(sig=signal(quote_impact_pct=None))
    assert by_name(impact, "impact").state is CheckState.UNAVAILABLE
    assert by_name(impact, "cost_r").state is CheckState.UNAVAILABLE
    assert by_name(impact, "sizing").state is CheckState.UNAVAILABLE
    assert impact.sizing is None


def test_the_instant_defaults_to_the_wallet_stamp_and_a_naive_now_is_refused() -> None:
    later = AS_OF + timedelta(seconds=200)
    assert by_name(decide(now=later), "signal_stale").refusal == "signal_stale"
    assert decide(now=AS_OF).approved
    with pytest.raises(ValueError, match="timezone-aware"):
        decide(now=datetime(2026, 9, 19, 15, 30))  # noqa: DTZ001
    # Two seconds of skew (limits.clock_skew_tolerance_s) are tolerated; an hour is not.
    assert decide(sig=signal(emitted_at=AS_OF + timedelta(seconds=2))).approved


def test_an_adverse_impact_is_never_negative_and_parity_is_never_zero() -> None:
    """Astra (19/09): a negative impact would pass the cap and *discount* cost_r (−0.45 R)."""
    with pytest.raises(ValueError, match="greater than or equal to 0"):
        signal(quote_impact_pct=Decimal("-0.01"))
    with pytest.raises(ValueError, match="greater than 0"):
        signal(parity_ratio=Decimal("0"))


def test_no_float_reaches_the_profile_or_the_signal() -> None:
    a_float: Any = 0.05  # what a careless caller would hand in
    with pytest.raises(TypeError, match="float"):
        MemeSpotProfile.model_validate({**PROFILE.model_dump(), "ticket_sol": a_float})
    with pytest.raises(TypeError, match="float"):
        signal(quote_impact_pct=a_float)


def test_the_module_has_no_float_literal_or_float_name() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "hunter_risk_meme" / "spot_profile.py").read_text(encoding="utf-8")
    assert not re.search(r"\bfloat\b", source)
    nodes = list(ast.walk(ast.parse(source)))
    consts = [n.value for n in nodes if isinstance(n, ast.Constant)]
    assert [c for c in consts if type(c) is float] == []
    # Every timedelta division is the integer kind (``//``): ``/`` on timedeltas is a float.
    divs = [ast.unparse(n) for n in nodes if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div)]
    assert [d for d in divs if "timedelta" in d] == []
