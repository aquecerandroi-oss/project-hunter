"""Sizing: nine ceilings, the smallest wins, the kill switch multiplies afterwards."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import KillSwitchState
from hunter_risk.inputs import BookLevel
from hunter_risk.kill_switch import entry_size_multiplier
from hunter_risk.limits import PAPER_V1, RiskLimits
from hunter_risk.observations import book_capacity_qty
from hunter_risk.sizing import (
    entry_cash_multiplier,
    floor_to_step,
    round_trip_cost_fraction,
    size_entry,
    stop_distance_fraction,
)

from .factories import COSTS, beta, liquidity, market, pending, portfolio, position, proposal, spec

pytestmark = pytest.mark.unit


def _size(**over: object):
    kwargs: dict[str, object] = {
        "proposal": proposal(),
        "portfolio": portfolio(),
        "limits": PAPER_V1,
        "liquidity": liquidity(),
        "spec": spec(),
        "beta": beta(),
        "size_multiplier": Decimal("1"),
    }
    return size_entry(**(kwargs | over))  # type: ignore[arg-type]


class TestCostModel:
    def test_round_trip_cost_is_the_two_legs_of_the_declared_hypothesis(self) -> None:
        # spread 2 + 2 x slippage 5 + 2 x fee 4 = 20 bps, the same model as
        # services/strategy-worker/hunter_strategy_worker/pricing.py.
        assert round_trip_cost_fraction(COSTS) == Decimal("0.0020")

    def test_the_entry_cash_multiplier_is_a_product_not_a_sum(self) -> None:
        # (1 + 6 bps of displacement) x (1 + 4 bps of fee). The additive form
        # would leave the product term uncovered, and on spot cash is hard.
        assert entry_cash_multiplier(COSTS) == (Decimal(1) + Decimal("0.0006")) * (
            Decimal(1) + Decimal("0.0004")
        )

    def test_stop_distance_is_relative_to_the_entry_reference(self) -> None:
        assert stop_distance_fraction(Decimal("100"), Decimal("97.5")) == Decimal("0.025")

    def test_a_stop_at_or_above_the_entry_has_no_distance(self) -> None:
        with pytest.raises(ValueError, match="stop"):
            stop_distance_fraction(Decimal("100"), Decimal("100"))


class TestFloorToStep:
    def test_quantity_is_always_rounded_down(self) -> None:
        assert floor_to_step(Decimal("18.5185185"), Decimal("0.001")) == Decimal("18.518")

    def test_rounding_down_can_reach_zero(self) -> None:
        assert floor_to_step(Decimal("0.4"), Decimal("1")) == Decimal("0")


class TestBookWalk:
    def test_the_whole_book_fits_when_it_is_cheap_enough(self) -> None:
        asks = (
            BookLevel(price=Decimal("100.00"), qty=Decimal("10")),
            BookLevel(price=Decimal("100.05"), qty=Decimal("10")),
            BookLevel(price=Decimal("100.20"), qty=Decimal("10")),
        )
        got = book_capacity_qty(asks, Decimal("100"), Decimal("0.001"))
        assert got == Decimal("30")

    def test_the_walk_stops_inside_the_level_where_the_budget_runs_out(self) -> None:
        asks = (
            BookLevel(price=Decimal("100.00"), qty=Decimal("10")),
            BookLevel(price=Decimal("100.05"), qty=Decimal("10")),
        )
        # budget 2 bps -> VWAP <= 100.02; 10 at 100.00 plus 20/3 at 100.05 is exactly it.
        got = book_capacity_qty(asks, Decimal("100"), Decimal("0.0002"))
        assert got == Decimal("10") + Decimal(20) / Decimal(3)

    def test_a_book_whose_best_ask_already_costs_too_much_has_zero_capacity(self) -> None:
        asks = (BookLevel(price=Decimal("100.5"), qty=Decimal("10")),)
        assert book_capacity_qty(asks, Decimal("100"), Decimal("0.001")) == Decimal("0")

    def test_an_unobserved_book_has_no_capacity_and_says_so(self) -> None:
        assert book_capacity_qty((), Decimal("100"), Decimal("0.001")) is None


class TestTheWorkedExample:
    """R$100,000 at a test rate of 5.00 BRL/USDT = 20,000 USDT of equity."""

    def test_risk_per_trade_wins_and_produces_the_expected_notional(self) -> None:
        got = _size()
        assert got.stop_distance_pct == Decimal("0.025")
        assert got.cost_pct == Decimal("0.0020")
        # 0.25% of 20,000 = 50 USDT of planned loss; 50 / (0.025 + 0.002) = 1851.85...
        assert got.binding_limit.name == "risk_per_trade"
        assert got.binding_limit.notional == Decimal("1851.851851851851851851851852")
        assert got.qty == Decimal("18.518")
        assert got.notional == Decimal("1851.800")
        assert got.planned_risk_quote == Decimal("49.9986")

    def test_the_ceiling_is_a_ceiling_and_never_a_target(self) -> None:
        got = _size()
        for cap in got.caps:
            if cap.notional is not None:
                assert got.notional <= cap.notional

    def test_the_declared_stop_is_carried_through_and_never_moved(self) -> None:
        assert _size().stop == Decimal("97.5")

    def test_a_requested_notional_is_a_further_ceiling_not_a_size_to_reach(self) -> None:
        got = _size(proposal=proposal(requested_notional=Decimal("300")))
        assert got.binding_limit.name == "requested"
        assert got.notional == Decimal("300")


class TestKB0071:
    """The one-percent participation ceiling on the median minute of the VPS."""

    def test_participation_wins_in_the_median_market(self) -> None:
        got = _size(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("4605.10"),
                median_30m_quote_volume=Decimal("4605.10"),
            )
        )
        assert got.binding_limit.name == "market_participation"
        assert got.binding_limit.notional == Decimal("46.0510")
        assert got.qty == Decimal("0.460")
        assert got.notional == Decimal("46.000")

    def test_the_reference_is_the_smaller_of_the_minute_and_the_median(self) -> None:
        got = _size(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("4605.10"),
                median_30m_quote_volume=Decimal("900000"),
            )
        )
        assert got.binding_limit.notional == Decimal("46.0510")

    def test_notional_already_taken_in_this_market_is_subtracted(self) -> None:
        # Two agents proposing the same market in the same cycle: the first
        # reserved 30 USDT, so the second may only take the remaining 16.051.
        got = _size(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("4605.10"),
                median_30m_quote_volume=Decimal("4605.10"),
                participation_used_quote=Decimal("30"),
            )
        )
        assert got.binding_limit.name == "market_participation"
        assert got.binding_limit.notional == Decimal("16.0510")


class TestEachCeiling:
    def test_the_per_coin_ceiling_binds_when_the_coin_is_already_held(self) -> None:
        state = portfolio(
            open_positions=(position(notional=Decimal("1500"), planned_risk_quote=Decimal("0")),)
        )
        got = _size(portfolio=state, proposal=proposal(stop=Decimal("99.9")))
        assert got.binding_limit.name == "asset_exposure"
        assert got.binding_limit.notional == Decimal("500")

    def test_the_total_ceiling_binds_when_other_coins_fill_the_wallet(self) -> None:
        state = portfolio(
            open_positions=(
                position(
                    market=market("ETHUSDT", "ETH"),
                    notional=Decimal("7900"),
                    planned_risk_quote=Decimal("0"),
                ),
            )
        )
        got = _size(portfolio=state, proposal=proposal(stop=Decimal("99.9")))
        assert got.binding_limit.name == "total_exposure"
        assert got.binding_limit.notional == Decimal("100")

    def test_the_beta_ceiling_divides_the_remaining_budget_by_the_absolute_beta(self) -> None:
        state = portfolio(
            open_positions=(
                position(
                    market=market("ETHUSDT", "ETH"),
                    notional=Decimal("1000"),
                    planned_risk_quote=Decimal("0"),
                    beta_btc=Decimal("1"),
                ),
            )
        )
        got = _size(
            portfolio=state, proposal=proposal(stop=Decimal("99.9")), beta=beta(value="-20.0")
        )
        # 0.5 x 20,000 - 1,000 = 9,000 of beta budget; |beta| = 20 -> 450 of notional.
        # The sign does not matter: the directive sums |notional x beta|.
        assert got.binding_limit.name == "beta_exposure"
        assert got.binding_limit.notional == Decimal("450")

    def test_a_validated_beta_of_zero_adds_no_ceiling_instead_of_dividing_by_zero(self) -> None:
        got = _size(beta=beta(value="0"))
        caps = {cap.name: cap for cap in got.caps}
        assert caps["beta_exposure"].notional is None
        assert got.binding_limit.name == "risk_per_trade"

    def test_the_aggregate_risk_ceiling_binds_when_the_budget_is_nearly_spent(self) -> None:
        state = portfolio(
            open_positions=(
                position(
                    market=market("ETHUSDT", "ETH"),
                    notional=Decimal("100"),
                    planned_risk_quote=Decimal("195"),
                ),
            )
        )
        got = _size(portfolio=state)
        # 1% of 20,000 = 200 of aggregate budget, 195 committed -> 5 / 0.027
        assert got.binding_limit.name == "aggregate_risk"
        assert got.binding_limit.notional == Decimal("185.1851851851851851851851852")

    def test_pending_entries_consume_the_aggregate_budget_too(self) -> None:
        state = portfolio(
            pending_entries=(
                pending(
                    market=market("ETHUSDT", "ETH"),
                    reserved_notional=Decimal("100"),
                    planned_risk_quote=Decimal("195"),
                ),
            )
        )
        assert _size(portfolio=state).binding_limit.name == "aggregate_risk"

    def test_the_cash_ceiling_leaves_room_for_the_entry_cost(self) -> None:
        state = portfolio(cash=Decimal("100"))
        got = _size(portfolio=state, proposal=proposal(stop=Decimal("99.9")))
        assert got.binding_limit.name == "cash"
        assert got.binding_limit.notional == Decimal("100") / entry_cash_multiplier(COSTS)

    def test_the_book_ceiling_binds_when_the_book_is_thin(self) -> None:
        thin = (BookLevel(price=Decimal("100.00"), qty=Decimal("2")),)
        got = _size(liquidity=liquidity(asks=thin))
        assert got.binding_limit.name == "book_depth"
        assert got.binding_limit.notional == Decimal("200")


class TestKillSwitchMultiplier:
    def test_the_multiplier_halves_the_final_size_after_every_ceiling(self) -> None:
        full = _size()
        half = _size(size_multiplier=entry_size_multiplier(KillSwitchState.WARNING, PAPER_V1))
        assert half.kill_switch_multiplier == Decimal("0.5")
        assert half.notional_after_multiplier == full.notional_before_multiplier / 2
        assert half.qty == Decimal("9.259")

    def test_the_multiplier_bites_whichever_ceiling_won(self) -> None:
        # R-KS-1: in the old contract the multiplier only scaled the risk budget,
        # so a proposal sized by participation came out identical in WARNING.
        thin = liquidity(
            last_minute_quote_volume=Decimal("4605.10"),
            median_30m_quote_volume=Decimal("4605.10"),
        )
        full = _size(liquidity=thin)
        half = _size(liquidity=thin, size_multiplier=Decimal("0.5"))
        assert full.binding_limit.name == "market_participation"
        assert half.binding_limit.name == "market_participation"
        assert half.notional < full.notional

    def test_the_binding_limit_is_the_ceiling_that_won_not_the_multiplier(self) -> None:
        half = _size(size_multiplier=Decimal("0.5"))
        assert half.binding_limit.name == "risk_per_trade"
        assert half.notional_before_multiplier == Decimal("1851.851851851851851851851852")


class TestExchangeMinimums:
    def test_quantity_is_floored_to_the_step_never_rounded_up(self) -> None:
        got = _size(spec=spec(step_size=Decimal("1")))
        assert got.qty == Decimal("18")
        assert got.notional == Decimal("1800")

    def test_a_size_below_the_step_becomes_zero_rather_than_a_minimum_order(self) -> None:
        got = _size(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("100"), median_30m_quote_volume=Decimal("100")
            ),
            spec=spec(step_size=Decimal("1")),
        )
        assert got.qty == Decimal("0")
        assert got.notional == Decimal("0")


class TestProvenance:
    """R-PROV-1 and R-KS-2: the decision has to be contradictable by a number."""

    def test_the_binding_constraint_is_published_by_name(self) -> None:
        got = _size()
        assert got.binding_constraint == got.binding_limit.name == "risk_per_trade"

    def test_the_counterfactual_of_the_multipliers_measures_the_kill_switch_step(self) -> None:
        half = _size(size_multiplier=Decimal("0.5"))
        assert half.qty == Decimal("9.259")
        assert half.size_without_multipliers.qty == Decimal("18.518")
        assert half.size_without_multipliers.unavailable_reason is None

    def test_without_the_warning_the_two_numbers_agree(self) -> None:
        full = _size()
        assert full.size_without_multipliers.qty == full.qty

    def test_the_counterfactual_of_participation_measures_how_much_the_rule_bites(self) -> None:
        # KB-0071: in the median market the 1 % participation ceiling cuts the
        # position from 1,851.80 to 46.00 USDT. That is the number Everton needs
        # to decide whether to keep p = 0.01, and it is published, not inferred.
        got = _size(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("4605.10"),
                median_30m_quote_volume=Decimal("4605.10"),
            )
        )
        assert got.binding_constraint == "market_participation"
        assert got.notional == Decimal("46.000")
        assert got.size_without_participation.notional == Decimal("1851.800")

    def test_the_two_counterfactuals_are_never_the_same_number_by_accident(self) -> None:
        got = _size(
            liquidity=liquidity(
                last_minute_quote_volume=Decimal("4605.10"),
                median_30m_quote_volume=Decimal("4605.10"),
            ),
            size_multiplier=Decimal("0.5"),
        )
        assert got.size_without_multipliers.qty == Decimal("0.460")
        assert got.size_without_participation.qty == Decimal("9.259")


class TestAstraCounterexamples:
    """Two defects Astra's review of the diff produced, with her scenarios."""

    def test_the_book_ceiling_is_a_quantity_and_not_a_spend(self) -> None:
        # mid 100, budget 1 %: 1 unit at 100 plus 1 at 102 is exactly VWAP 101.
        # The ceiling is therefore 2 units. Returning the *spend* (202) and then
        # dividing it by entry_ref (100) would authorise 2.02 units, whose real
        # VWAP is 101.0099 - above the budget the ceiling exists to enforce.
        asks = (
            BookLevel(price=Decimal("100"), qty=Decimal("1")),
            BookLevel(price=Decimal("102"), qty=Decimal("10")),
        )
        assert book_capacity_qty(asks, Decimal("100"), Decimal("0.01")) == Decimal("2")

    def test_the_size_never_walks_deeper_than_the_slippage_budget(self) -> None:
        asks = (
            BookLevel(price=Decimal("100"), qty=Decimal("1")),
            BookLevel(price=Decimal("102"), qty=Decimal("10")),
        )
        wide = RiskLimits.model_validate(
            PAPER_V1.model_dump() | {"max_slippage_pct": Decimal("0.01")}
        )
        got = _size(liquidity=liquidity(asks=asks), limits=wide)
        assert got.binding_limit.name == "book_depth"
        assert got.qty == Decimal("2.000")

    def test_the_cash_ceiling_covers_the_fee_charged_on_the_executed_price(self) -> None:
        # cash out = notional x (1 + deslocamento) x (1 + fee). The additive
        # 1 + d + f leaves the product term d x f uncovered, and on spot the cash
        # is the hard limit: the order would be short by that much.
        displacement = Decimal("0.0006")  # half spread (1 bp) + slippage (5 bps)
        fee = Decimal("0.0004")
        got = _size(portfolio=portfolio(cash=Decimal("100")), proposal=proposal(stop=Decimal("99")))
        cap = got.binding_limit.notional
        assert got.binding_limit.name == "cash"
        assert cap is not None
        assert cap * (Decimal(1) + displacement) * (Decimal(1) + fee) <= Decimal("100")
