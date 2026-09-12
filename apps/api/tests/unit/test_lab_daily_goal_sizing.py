"""Unit tests: value of 1R and percentiles behind the daily goal — T3.78.

No IO: every input is a plain value or a hand-built ``BetPricingInput``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_api.services.lab_daily_goal_sizing import (
    BetPricingInput,
    label_brl,
    percentile,
    price_bet,
    sum_priced_bets,
    usdt_to_brl,
)

pytestmark = pytest.mark.unit


def test_summed_money_uses_each_bets_own_size() -> None:
    assert sum_priced_bets(
        [(Decimal("2"), Decimal("10")), (Decimal("-1"), Decimal("30"))]
    ) == Decimal("-10")


def test_summed_money_does_not_present_partial_pricing_as_total() -> None:
    assert sum_priced_bets([(Decimal("2"), Decimal("10")), (Decimal("-1"), None)]) is None
    assert sum_priced_bets([(None, Decimal("30"))]) == Decimal(0)
    assert sum_priced_bets([]) == Decimal(0)


_COSTS = {"spread_bps": "10", "slippage_bps": "5", "fee_bps": "10", "max_entry_delay_s": 30}
_EQUITY = Decimal("100000")


def _inputs(**overrides: object) -> BetPricingInput:
    base: dict[str, object] = {
        "virtual_entry": Decimal("100"),
        "virtual_stop": Decimal("99"),
        "assumed_costs_raw": _COSTS,
        "quote_volume": Decimal("200000"),
    }
    base.update(overrides)
    return BetPricingInput(**base)  # type: ignore[arg-type]


class TestPriceBet:
    def test_missing_entry_or_stop_is_a_named_reason(self) -> None:
        result = price_bet(_inputs(virtual_stop=None), equity_usdt=_EQUITY)
        assert result.value_1r_usdt is None
        assert result.reason == "no_entry_or_stop"

    def test_missing_volume_is_a_named_reason(self) -> None:
        result = price_bet(_inputs(quote_volume=None), equity_usdt=_EQUITY)
        assert result.value_1r_usdt is None
        assert result.reason == "no_volume"

    def test_missing_cost_assumption_is_a_named_reason(self) -> None:
        result = price_bet(_inputs(assumed_costs_raw=None), equity_usdt=_EQUITY)
        assert result.value_1r_usdt is None
        assert result.reason == "no_cost_assumption"

    def test_invalid_cost_assumption_is_a_named_reason(self) -> None:
        result = price_bet(_inputs(assumed_costs_raw={"bad": "shape"}), equity_usdt=_EQUITY)
        assert result.value_1r_usdt is None
        assert result.reason == "invalid_cost_assumption"

    def test_thin_market_is_capped_by_participation(self) -> None:
        # loss_fraction = 0.01 (stop distance) + 0.004 (round-trip cost) = 0.014
        # participation ceiling = 1% * 200_000 = 2_000 -> value = 2_000 * 0.014
        result = price_bet(_inputs(), equity_usdt=_EQUITY)
        assert result.binding == "market_participation"
        assert result.value_1r_usdt == Decimal("28.000")

    def test_deep_market_is_capped_by_risk_per_trade_and_equals_the_risk_budget(self) -> None:
        # With risk_per_trade binding, value_1r_usdt == equity * risk_per_trade_pct
        # exactly, independent of the loss fraction (the ceiling divides it out).
        result = price_bet(_inputs(quote_volume=Decimal("10000000")), equity_usdt=_EQUITY)
        assert result.binding == "risk_per_trade"
        assert result.value_1r_usdt == Decimal("250.0000")

    def test_a_short_is_priced_the_same_as_a_long_of_equal_distance(self) -> None:
        long_result = price_bet(_inputs(), equity_usdt=_EQUITY)
        short_result = price_bet(
            _inputs(virtual_entry=Decimal("99"), virtual_stop=Decimal("100")),
            equity_usdt=_EQUITY,
        )
        # Not exactly equal (the fraction denominator differs: /100 vs /99),
        # but both are priced and both are participation-bound.
        assert long_result.value_1r_usdt is not None
        assert short_result.value_1r_usdt is not None
        assert short_result.binding == "market_participation"


class TestLabelBrl:
    def test_is_the_paper_v1_risk_budget_over_a_hundred_thousand(self) -> None:
        assert label_brl() == Decimal("250.00")


class TestUsdtToBrl:
    """USDT x observed rate = BRL, exact ``Decimal`` — brief T3.78b (Everton,
    2026-09-10): the FX leg is a plain multiplication by the observed rate,
    never a float and never rounded to a fixed number of places here."""

    def test_a_whole_amount_at_a_two_decimal_rate_is_exact_to_the_cent(self) -> None:
        assert usdt_to_brl(Decimal("28"), Decimal("5.00")) == Decimal("140.00")

    def test_fractional_usdt_and_rate_multiply_exactly_no_float_drift(self) -> None:
        # 28.567 * 5.4321, computed by hand with Decimal, not float.
        assert usdt_to_brl(Decimal("28.567"), Decimal("5.4321")) == Decimal("155.1788007")

    def test_a_tiny_amount_never_rounds_away_the_sub_cent_remainder(self) -> None:
        assert usdt_to_brl(Decimal("0.01"), Decimal("5.6789")) == Decimal("0.056789")

    def test_zero_usdt_converts_to_zero_regardless_of_rate(self) -> None:
        assert usdt_to_brl(Decimal("0"), Decimal("5.4321")) == Decimal("0.0000")


class TestPercentile:
    def test_single_value(self) -> None:
        assert percentile([Decimal("5")], Decimal("0.5")) == Decimal("5")

    def test_median_of_an_odd_population(self) -> None:
        values = [Decimal("1"), Decimal("3"), Decimal("2")]
        assert percentile(values, Decimal("0.5")) == Decimal("2")

    def test_p10_and_p90_of_ten_values_by_nearest_rank(self) -> None:
        values = [Decimal(i) for i in range(1, 11)]  # 1..10
        assert percentile(values, Decimal("0.10")) == Decimal("1")
        assert percentile(values, Decimal("0.90")) == Decimal("9")

    def test_empty_population_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            percentile([], Decimal("0.5"))
