"""Entry-bar selection and the assumed-cost arithmetic — SHADOW-LAB.md §3.

The two numbers the whole experiment hangs on: *which* 1m bar the hypothetical
entry uses (chosen before the outcome is known, never retroactively) and what a
price costs once the declared spread/slippage hypothesis is applied.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from hunter_core.strategies.envelope import AssumedCosts
from hunter_strategy_worker.plan import LateReason, plan_entry
from hunter_strategy_worker.pricing import entry_price, exit_price, r_net

pytestmark = pytest.mark.unit

COSTS = AssumedCosts(
    spread_bps=Decimal("2"),
    slippage_bps=Decimal("5"),
    fee_bps=Decimal("4"),
    max_entry_delay_s=120,
)


def _ts(hour: int, minute: int, second: int = 0, micro: int = 0) -> datetime:
    return datetime(2026, 9, 5, hour, minute, second, micro, tzinfo=UTC)


class TestEntryBarChoice:
    def test_the_entry_bar_is_the_first_minute_open_strictly_after_the_decision(self) -> None:
        plan = plan_entry(
            source_bar_close=_ts(12, 0),
            decision_at=_ts(12, 0, 2),
            costs=COSTS,
            now=_ts(12, 0, 2),
        )
        assert plan.entry_bar_open == _ts(12, 1)
        assert plan.late_reason is None

    def test_a_decision_exactly_on_the_boundary_still_waits_for_the_next_open(self) -> None:
        """``estritamente posterior``: deciding at 12:01:00 cannot use 12:01:00."""
        plan = plan_entry(
            source_bar_close=_ts(12, 0),
            decision_at=_ts(12, 1),
            costs=COSTS,
            now=_ts(12, 1),
        )
        assert plan.entry_bar_open == _ts(12, 2)

    def test_the_delay_is_measured_from_the_reference_bar_not_from_the_decision(self) -> None:
        """SHADOW-LAB.md §3: 12:00 / 12:05:02 / 12:06 is late (360s > 120s)."""
        plan = plan_entry(
            source_bar_close=_ts(12, 0),
            decision_at=_ts(12, 5, 2),
            costs=COSTS,
            now=_ts(12, 5, 2),
        )
        assert plan.entry_bar_open == _ts(12, 6)
        assert plan.late_reason is LateReason.DELAY
        assert plan.delay_s == 360

    def test_a_two_second_decision_enters_on_the_next_minute(self) -> None:
        """The other half of the same paragraph: 12:00 / 12:00:02 / 12:01 enters."""
        plan = plan_entry(
            source_bar_close=_ts(12, 0),
            decision_at=_ts(12, 0, 2),
            costs=COSTS,
            now=_ts(12, 0, 2),
        )
        assert plan.late_reason is None
        assert plan.delay_s == 60

    def test_a_clock_already_past_the_chosen_open_is_late_never_retroactive(self) -> None:
        """The commit that misses the open: the bar is not re-chosen later."""
        plan = plan_entry(
            source_bar_close=_ts(12, 0),
            decision_at=_ts(12, 0, 2),
            costs=COSTS,
            now=_ts(12, 1, 0),
        )
        assert plan.entry_bar_open == _ts(12, 1)
        assert plan.late_reason is LateReason.MISSED_OPEN

    def test_the_deadline_is_the_open_itself(self) -> None:
        plan = plan_entry(
            source_bar_close=_ts(12, 0),
            decision_at=_ts(12, 0, 2),
            costs=COSTS,
            now=_ts(12, 0, 59, 999999),
        )
        assert plan.late_reason is None
        assert plan.deadline == _ts(12, 1)

    def test_naive_timestamps_are_refused(self) -> None:
        with pytest.raises(ValueError, match="tz-aware"):
            plan_entry(
                source_bar_close=datetime(2026, 9, 5, 12, 0),  # noqa: DTZ001
                decision_at=_ts(12, 0, 2),
                costs=COSTS,
                now=_ts(12, 0, 2),
            )


class TestAssumedCostArithmetic:
    def test_the_entry_pays_half_the_spread_plus_slippage(self) -> None:
        """2 bps spread / 5 bps slippage = 6 bps, checked by hand:
        100 * (1 + 6/10000) = 100.06."""
        assert entry_price(Decimal("100"), COSTS) == Decimal("100.06")

    def test_the_exit_pays_the_same_six_basis_points_the_other_way(self) -> None:
        assert exit_price(Decimal("100"), COSTS) == Decimal("99.94")

    def test_r_net_charges_the_fee_on_both_legs(self) -> None:
        """By hand, in Decimal:
        numerator = (110 - 100) - 0.0004*100 - 0.0004*110 - 0
                  = 10 - 0.04 - 0.044 = 9.916
        denominator = 100 - 99 = 1  ->  R_net = 9.916
        """
        value = r_net(
            entry=Decimal("100"),
            exit_=Decimal("110"),
            stop=Decimal("99"),
            costs=COSTS,
            funding_per_unit=Decimal("0"),
        )
        assert value == Decimal("9.916")

    def test_funding_is_signed_and_subtracted_per_unit(self) -> None:
        """A long paying 0.5 per unit of funding loses exactly that much R."""
        with_funding = r_net(
            entry=Decimal("100"),
            exit_=Decimal("110"),
            stop=Decimal("99"),
            costs=COSTS,
            funding_per_unit=Decimal("0.5"),
        )
        assert with_funding == Decimal("9.416")
        received = r_net(
            entry=Decimal("100"),
            exit_=Decimal("110"),
            stop=Decimal("99"),
            costs=COSTS,
            funding_per_unit=Decimal("-0.5"),
        )
        assert received == Decimal("10.416")

    def test_a_losing_trade_is_worse_than_minus_one_r_because_of_the_costs(self) -> None:
        """Entry 100.06, stop level 99, exit base 99 -> 98.9406 after costs.
        numerator = (98.9406 - 100.06) - 0.0004*100.06 - 0.0004*98.9406
                  = -1.1194 - 0.040024 - 0.03957624 = -1.19899
        denominator = 100.06 - 99 = 1.06  ->  -1.13112...
        """
        value = r_net(
            entry=Decimal("100.06"),
            exit_=Decimal("98.9406"),
            stop=Decimal("99"),
            costs=COSTS,
            funding_per_unit=Decimal("0"),
        )
        assert value < Decimal("-1")
        assert value == Decimal("-1.199000240") / Decimal("1.06")

    def test_a_non_positive_initial_risk_has_no_r(self) -> None:
        with pytest.raises(ValueError, match="initial risk"):
            r_net(
                entry=Decimal("100"),
                exit_=Decimal("110"),
                stop=Decimal("100"),
                costs=COSTS,
                funding_per_unit=Decimal("0"),
            )

    def test_the_ambient_decimal_context_cannot_move_the_numbers(self) -> None:
        """S1's lesson (notes-S1.md §11): every arithmetic path declares its own
        context, so a caller running under prec=2/ROUND_UP gets the same value."""
        import decimal

        expected = r_net(
            entry=Decimal("100"),
            exit_=Decimal("110"),
            stop=Decimal("99"),
            costs=COSTS,
            funding_per_unit=Decimal("0"),
        )
        with decimal.localcontext() as ctx:
            ctx.prec = 2
            ctx.rounding = decimal.ROUND_UP
            assert (
                r_net(
                    entry=Decimal("100"),
                    exit_=Decimal("110"),
                    stop=Decimal("99"),
                    costs=COSTS,
                    funding_per_unit=Decimal("0"),
                )
                == expected
            )
            assert entry_price(Decimal("100"), COSTS) == Decimal("100.06")
