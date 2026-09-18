"""T4.61c — the conviction ladder as an input of the decision (§17, check 26 and
the ``conviction`` ceiling of §5): the size binds by its own name (review A4), a
ladder refusal is ``approved = false`` with ``first_refusal`` set like every other
check (A9), dust is ``conviction_too_small`` against the profile's floor (A5), and
off is the decision of before, byte for byte.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_risk_meme import (
    CAP_ORDER,
    CONVICTION_REFUSALS,
    LADDER_REFUSALS,
    REFUSAL_NAMES,
    MemeConviction,
    MemePolicyMissing,
    limits_from_env,
)
from hunter_risk_meme.limits import ENV_MIN_TRADE_SOL, LIVE_MIN_TRADE_SOL

from .factories import decide, limits, proposal, wallet

pytestmark = pytest.mark.unit

FULL = {
    "MEME_WALLET_MAX_SOL": "0.75",
    "MEME_MAX_SOL_PER_TRADE": "0.28",
    "MEME_DAILY_LOSS_CAP_SOL": "0.30",
    "MEME_MAX_OPEN_POSITIONS": "3",
    "MEME_COOLDOWN_S": "1800",
}


def sized(sol: str, multiplier: str = "0.5") -> MemeConviction:
    return MemeConviction(enabled=True, multiplier=Decimal(multiplier), sol_sized=Decimal(sol))


class TestTheCeiling:
    def test_conviction_sits_right_after_trade_cap_in_the_tie_break(self) -> None:
        assert CAP_ORDER.index("conviction") == CAP_ORDER.index("trade_cap") + 1

    def test_a_discounted_ladder_binds_by_its_own_name_never_as_requested(self) -> None:
        """A4: the desk asks 0,05, the ladder allows 0,025 — the binding constraint
        is ``conviction`` and ``sizing.requested_sol`` is still what the desk asked."""
        decision = decide(conv=sized("0.025"))
        assert decision.approved, decision.refusals
        assert decision.sizing is not None
        assert decision.sizing.binding_constraint == "conviction"
        assert decision.sizing.sol_final == Decimal("0.025")
        assert decision.sizing.requested_sol == Decimal("0.05"), "the desk's request, intact"
        cap = next(c for c in decision.sizing.caps if c.name == "conviction")
        assert cap.sol == Decimal("0.025") and cap.limit == Decimal("0.5")
        check = next(c for c in decision.checks if c.name == "conviction")
        assert check.passed and check.value == Decimal("0.025")

    def test_a_full_conviction_ladder_ties_and_the_policy_name_wins(self) -> None:
        decision = decide(conv=sized("0.05", "1"))
        assert decision.sizing is not None
        assert decision.sizing.binding_constraint == "requested"
        assert "conviction" in decision.sizing.tied_limits

    def test_another_ceiling_can_still_bind_below_the_ladder(self) -> None:
        decision = decide(conv=sized("0.04"), lim=limits(max_sol_per_trade=Decimal("0.03")))
        assert decision.sizing is not None
        assert decision.sizing.binding_constraint == "trade_cap"
        assert decision.sizing.sol_final == Decimal("0.03")

    def test_check_23_judges_the_final_size_the_ladder_produced(self) -> None:
        decision = decide(conv=sized("0.025"))
        check = next(c for c in decision.checks if c.name == "sizing")
        assert check.value == Decimal("0.025") and check.passed


class TestOffIsTheDecisionOfBefore:
    def test_absent_and_off_are_the_same_decision_as_no_ladder(self) -> None:
        base = decide().model_dump()
        for conv in (None, MemeConviction(), MemeConviction(enabled=False, multiplier=Decimal(0))):
            assert decide(conv=conv).model_dump() == base

    def test_off_records_check_26_as_passed_and_the_ceiling_as_unconstraining(self) -> None:
        decision = decide()
        check = next(c for c in decision.checks if c.name == "conviction")
        assert check.passed and check.message == "off"
        assert decision.sizing is not None
        cap = next(c for c in decision.sizing.caps if c.name == "conviction")
        assert cap.sol is None and cap.detail == "off"
        assert decision.sizing.binding_constraint == "requested"


class TestTheRefusals:
    @pytest.mark.parametrize("name", sorted(LADDER_REFUSALS))
    def test_a_ladder_refusal_is_not_approved_and_is_the_first_refusal(self, name: str) -> None:
        """A9: never ``approved = true`` with a refusal beside it — the desk and
        the R-studies read ``first_refusal`` and ``checks[].refusal``."""
        conv = MemeConviction(enabled=True, multiplier=Decimal(0), refusal=name)
        decision = decide(conv=conv)
        assert decision.approved is False
        assert decision.first_refusal == name
        assert decision.refusals == (name,), "the other 25 checks passed"
        check = next(c for c in decision.checks if c.name == "conviction")
        assert check.refusal == name and check.state == "failed"

    def test_a_ladder_refusal_leaves_the_other_checks_at_the_flat_size(self) -> None:
        decision = decide(
            conv=MemeConviction(enabled=True, multiplier=Decimal(0), refusal="entry_after_drop")
        )
        assert decision.sizing is not None, "the sizing is published for the panel"
        assert decision.sizing.sol_final == Decimal("0.05")
        cap = next(c for c in decision.sizing.caps if c.name == "conviction")
        assert cap.sol is None and cap.detail == "entry_after_drop"
        assert decision.sizing.binding_constraint == "requested"

    def test_dust_is_conviction_too_small_against_the_profile_floor(self) -> None:
        """A5: 0,07 × 0,25 = 0,0175 SOL under a 0,02 floor is refused, never sent."""
        lim = limits_from_env(FULL)
        decision = decide(
            p=proposal(requested_sol=Decimal("0.28")),
            lim=lim,
            w=wallet(sol_balance=Decimal("0.73"), day_start_sol_equity=Decimal("0.73")),
            conv=sized("0.0175", "0.25"),
        )
        assert decision.approved is False
        assert decision.first_refusal == "conviction_too_small"
        check = next(c for c in decision.checks if c.name == "conviction")
        assert check.value == Decimal("0.0175") and check.limit == Decimal("0.02")

    def test_exactly_the_floor_is_sent(self) -> None:
        decision = decide(conv=sized("0.001", "0.02"))
        assert decision.approved, decision.refusals
        assert decision.sizing is not None and decision.sizing.sol_final == Decimal("0.001")

    def test_the_ladder_refusal_wins_over_the_dust_floor(self) -> None:
        conv = MemeConviction(
            enabled=True,
            multiplier=Decimal("0.1"),
            sol_sized=Decimal("0"),
            refusal="conviction_too_low",
        )
        assert decide(conv=conv).refusals == ("conviction_too_low",)

    def test_a_ladder_refusal_still_counts_after_an_earlier_refusal(self) -> None:
        decision = decide(
            p=proposal(agent_enabled=False),
            conv=MemeConviction(enabled=True, multiplier=Decimal(0), refusal="entry_after_drop"),
        )
        assert decision.refusals == ("agent_disabled", "entry_after_drop")

    def test_every_conviction_name_is_a_refusal_of_the_doctrine(self) -> None:
        assert CONVICTION_REFUSALS <= REFUSAL_NAMES
        assert CONVICTION_REFUSALS == LADDER_REFUSALS | {"conviction_too_small"}

    def test_a_name_that_is_not_the_ladders_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="not a ladder refusal"):
            MemeConviction(enabled=True, refusal="below_min_sol")
        with pytest.raises(ValueError):
            MemeConviction(enabled=True, multiplier=Decimal("1.5"))


class TestTheLiveFloor:
    def test_absent_is_two_hundredths_of_a_sol_not_the_paper_dust(self) -> None:
        assert limits_from_env(FULL).min_trade_sol == LIVE_MIN_TRADE_SOL == Decimal("0.02")

    def test_the_owner_may_set_it(self) -> None:
        live = limits_from_env({**FULL, ENV_MIN_TRADE_SOL: "0.05"})
        assert live.min_trade_sol == Decimal("0.05")

    @pytest.mark.parametrize("raw", ["abc", "0", "-1", "nan"])
    def test_unreadable_or_non_positive_is_refused_by_name(self, raw: str) -> None:
        with pytest.raises(MemePolicyMissing) as info:
            limits_from_env({**FULL, ENV_MIN_TRADE_SOL: raw})
        assert info.value.invalid == (ENV_MIN_TRADE_SOL,)

    def test_a_floor_above_the_trade_cap_is_refused_with_the_numbers(self) -> None:
        with pytest.raises(MemePolicyMissing) as info:
            limits_from_env({**FULL, "MEME_MAX_SOL_PER_TRADE": "0.01"})
        assert info.value.invalid == (ENV_MIN_TRADE_SOL,)
        assert "0.02 exceeds max_sol_per_trade 0.01" in str(info.value)

    def test_the_paper_preset_keeps_its_own_floor(self) -> None:
        assert limits().min_trade_sol == Decimal("0.001")
