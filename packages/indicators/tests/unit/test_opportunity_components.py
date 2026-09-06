"""The components: fixed denominator, declared direction, nothing invented."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import AnomalyEvaluationState, AnomalyType, TradeDirection
from hunter_indicators.features import DEFAULT_REGISTRY
from hunter_indicators.opportunity import (
    COMPONENT_PROFILE_VERSION,
    COMPONENTS,
    REASON_ANOMALIES_UNKNOWN,
    REASON_NO_USABLE_INPUT,
    REASON_REGIME_UNKNOWN,
    ComponentKind,
    DirectionRule,
    component_for,
    score_anomaly_component,
    score_consensus_component,
    score_mad_component,
    score_regime_component,
)
from hunter_indicators.regime import RegimeTrend, RegimeVolatility
from packages.indicators.tests.scoring import (
    CONFIG,
    MARKET,
    baselines_for,
    degraded,
    missing,
    ok,
    projection,
    regime_decision,
    revision,
    vector,
)

VOLUME_INPUTS = (
    "relative_volume_5m",
    "relative_volume_15m",
    "relative_volume_1h",
    "volume_acceleration",
)


def mad_component(name: str, values: dict[str, str], *, weight: str, **baseline: str):
    definition = component_for(name)
    keys = [item.feature for item in definition.inputs]
    return score_mad_component(
        definition,
        weight=Decimal(weight),
        market_id=MARKET,
        vector=vector({key: ok(key, value) for key, value in values.items()}),
        projection=baselines_for(keys, **baseline),
        config=CONFIG,
    )


class TestTheProfileDescribesThisBuild:
    def test_every_declared_input_exists_in_the_registry_at_that_version(self) -> None:
        for definition in COMPONENTS:
            for item in definition.inputs:
                calculator = DEFAULT_REGISTRY.get(item.feature)
                assert calculator.definition.version == item.feature_version, item.feature

    def test_the_nine_components_of_the_weight_vector_are_registered(self) -> None:
        assert {definition.name for definition in COMPONENTS} == {
            "momentum",
            "volume",
            "liquidity",
            "order_flow",
            "derivatives",
            "market_regime",
            "anomalies",
            "agent_consensus",
            "external_intelligence",
        }

    def test_the_profile_is_versioned(self) -> None:
        assert COMPONENT_PROFILE_VERSION == "components_v1"

    def test_a_gap_of_this_build_is_declared_not_hidden(self) -> None:
        liquidity = component_for("liquidity")
        assert dict(liquidity.not_implemented) == {
            "quote_volume_1h": "feature_not_implemented",
            "depth_top_25": "feature_not_implemented",
        }
        assert [item.feature for item in liquidity.inputs] == ["spread_pct"]

    def test_the_complementary_side_of_the_tape_is_not_counted_twice(self) -> None:
        order_flow = component_for("order_flow")
        features = [item.feature for item in order_flow.inputs]
        assert "buy_pressure_5m" in features
        assert "sell_pressure_5m" not in features


class TestTheDenominatorIsFixed:
    def test_every_input_present_scores_the_mean(self) -> None:
        component = mad_component("volume", dict.fromkeys(VOLUME_INPUTS, "2"), weight="0.20")
        assert component.normalized == Decimal("60.0000")  # each input at 4 MADs
        assert component.contribution == Decimal("12.0000")
        assert component.confidence == Decimal("0.9524")
        assert component.used == 4
        assert component.expected == 4

    def test_a_missing_input_lowers_the_component_and_never_raises_it(self) -> None:
        component = mad_component("volume", dict.fromkeys(VOLUME_INPUTS[:3], "2"), weight="0.20")
        assert component.normalized == Decimal("45.0000")  # 180 / 4, not 180 / 3
        assert component.confidence == Decimal("0.7143")
        assert component.used == 3
        assert component.reason is None

    def test_losing_the_quiet_input_of_a_pair_does_not_promote_the_loud_one(self) -> None:
        both = mad_component(
            "volume",
            {"relative_volume_5m": "3", "relative_volume_15m": "1"},
            weight="0.20",
        )
        alone = mad_component("volume", {"relative_volume_5m": "3"}, weight="0.20")
        assert both.normalized == Decimal("25.0000")  # (100 + 0) / 4
        assert alone.normalized == Decimal("25.0000")  # the absence adds nothing

    def test_no_usable_input_leaves_the_component_unavailable(self) -> None:
        component = mad_component("volume", {}, weight="0.20")
        assert component.available is False
        assert component.reason == REASON_NO_USABLE_INPUT
        assert component.normalized is None
        assert component.contribution == Decimal("0.0000")
        assert component.confidence == Decimal("0.0000")


class TestEligibility:
    def test_a_degraded_reading_is_not_evidence(self) -> None:
        definition = component_for("volume")
        component = score_mad_component(
            definition,
            weight=Decimal("0.20"),
            market_id=MARKET,
            vector=vector(
                {
                    "relative_volume_5m": degraded("relative_volume_5m", "2"),
                    "relative_volume_15m": ok("relative_volume_15m", "2"),
                }
            ),
            projection=baselines_for(VOLUME_INPUTS),
            config=CONFIG,
        )
        assert component.used == 1
        assert component.normalized == Decimal("15.0000")  # 60 / 4
        entry = next(item for item in component.inputs if item.feature == "relative_volume_5m")
        assert entry.available is False
        assert entry.reason == "stale_input"
        assert entry.value == Decimal("2")  # shown, not used

    def test_an_unavailable_feature_carries_its_own_reason(self) -> None:
        definition = component_for("volume")
        component = score_mad_component(
            definition,
            weight=Decimal("0.20"),
            market_id=MARKET,
            vector=vector({"relative_volume_5m": missing("relative_volume_5m")}),
            projection=baselines_for(VOLUME_INPUTS),
            config=CONFIG,
        )
        entry = next(item for item in component.inputs if item.feature == "relative_volume_5m")
        assert entry.reason == "warmup"

    def test_an_immature_baseline_refuses_the_input_with_its_own_reason(self) -> None:
        definition = component_for("volume")
        component = score_mad_component(
            definition,
            weight=Decimal("0.20"),
            market_id=MARKET,
            vector=vector({"relative_volume_5m": ok("relative_volume_5m", "2")}),
            projection=projection(revision("relative_volume_5m", sample_size=30, distinct_days=1)),
            config=CONFIG,
        )
        entry = next(item for item in component.inputs if item.feature == "relative_volume_5m")
        assert entry.available is False
        assert entry.reason == "insufficient_history"
        assert component.available is False

    def test_a_baseline_without_dispersion_refuses_rather_than_inventing_a_scale(self) -> None:
        definition = component_for("liquidity")
        component = score_mad_component(
            definition,
            weight=Decimal("0.10"),
            market_id=MARKET,
            vector=vector({"spread_pct": ok("spread_pct", "2")}),
            projection=projection(revision("spread_pct", mad="0")),
            config=CONFIG,
        )
        entry = component.inputs[0]
        assert entry.reason == "mad_zero"
        assert component.available is False


class TestDirection:
    def test_the_side_comes_from_the_reading_not_from_the_deviation(self) -> None:
        """Astra, T2.4 design review, item 5: a return of -1% against a median of
        -3% deviates *upwards* and the price is still falling."""
        definition = component_for("momentum")
        component = score_mad_component(
            definition,
            weight=Decimal("0.20"),
            market_id=MARKET,
            vector=vector({"momentum_15m": ok("momentum_15m", "-1")}),
            projection=projection(revision("momentum_15m", median="-3", mad="1")),
            config=CONFIG,
        )
        entry = component.inputs[0]
        assert entry.deviation == Decimal("2")  # above its median
        assert entry.severity == Decimal("20.00")
        assert entry.direction is TradeDirection.SHORT  # and falling
        assert component.direction is TradeDirection.SHORT

    def test_an_unusual_volume_votes_for_no_side(self) -> None:
        component = mad_component("volume", {"relative_volume_5m": "3"}, weight="0.20")
        assert component.direction is TradeDirection.NEUTRAL
        assert component.inputs[0].direction is TradeDirection.NEUTRAL

    def test_taker_pressure_is_read_around_one_half(self) -> None:
        definition = component_for("order_flow")
        rule = next(
            item.direction_rule for item in definition.inputs if item.feature == "buy_pressure_5m"
        )
        assert rule is DirectionRule.FRACTION_HALF
        component = score_mad_component(
            definition,
            weight=Decimal("0.15"),
            market_id=MARKET,
            vector=vector({"buy_pressure_5m": ok("buy_pressure_5m", "0.7")}),
            projection=projection(revision("buy_pressure_5m", median="0.5", mad="0.05")),
            config=CONFIG,
        )
        assert component.inputs[0].direction is TradeDirection.LONG

    def test_a_breakout_only_speaks_upwards(self) -> None:
        definition = component_for("momentum")
        component = score_mad_component(
            definition,
            weight=Decimal("0.20"),
            market_id=MARKET,
            vector=vector({"breakout_strength_20": ok("breakout_strength_20", "-0.5")}),
            projection=projection(revision("breakout_strength_20", median="-2", mad="0.25")),
            config=CONFIG,
        )
        assert component.inputs[0].direction is TradeDirection.NEUTRAL


class TestNonMadComponents:
    def test_the_anomaly_stack_discounts_the_second_and_later_anomalies(self) -> None:
        from packages.indicators.tests.scoring import anomaly

        component = score_anomaly_component(
            component_for("anomalies"),
            weight=Decimal("0.05"),
            anomalies=[
                anomaly(AnomalyType.VOLUME_SPIKE, "80"),
                anomaly(AnomalyType.MOMENTUM_SHIFT, "60"),
            ],
        )
        assert component.raw == Decimal("110")  # 80 + 60/2
        assert component.normalized == Decimal("100.0000")  # clipped
        assert component.transform == "anomaly_stack_v1"

    def test_no_active_anomaly_is_knowledge_not_absence(self) -> None:
        component = score_anomaly_component(
            component_for("anomalies"), weight=Decimal("0.05"), anomalies=[]
        )
        assert component.available is True
        assert component.normalized == Decimal("0.0000")

    def test_an_unloaded_anomaly_set_is_unknown(self) -> None:
        component = score_anomaly_component(
            component_for("anomalies"), weight=Decimal("0.05"), anomalies=None
        )
        assert component.available is False
        assert component.reason == REASON_ANOMALIES_UNKNOWN

    def test_an_ineligible_anomaly_does_not_score(self) -> None:
        """And it is not the same as having none: an anomaly whose feed went
        quiet is *unknown*, and unknown may not borrow the certainty of an empty
        set (Astra, T2.4 diff review, must-fix 4)."""
        from packages.indicators.tests.scoring import anomaly

        component = score_anomaly_component(
            component_for("anomalies"),
            weight=Decimal("0.05"),
            anomalies=[
                anomaly(AnomalyType.VOLUME_SPIKE, "80", state=AnomalyEvaluationState.UNKNOWN)
            ],
        )
        assert component.available is False
        assert component.reason == REASON_ANOMALIES_UNKNOWN
        assert component.normalized is None
        assert component.confidence == Decimal("0.0000")
        assert component.inputs[0].available is False

    def test_one_readable_anomaly_among_two_is_partial_knowledge(self) -> None:
        from packages.indicators.tests.scoring import anomaly

        component = score_anomaly_component(
            component_for("anomalies"),
            weight=Decimal("0.05"),
            anomalies=[
                anomaly(AnomalyType.VOLUME_SPIKE, "80"),
                anomaly(AnomalyType.MOMENTUM_SHIFT, "60", state=AnomalyEvaluationState.STALE),
            ],
        )
        assert component.available is True
        assert component.normalized == Decimal("80.0000")
        # mean maturity times coverage: the one readable anomaly is 0.9 mature
        # and it is one of two active ones (cross review, nice-to-have 1)
        assert component.confidence == Decimal("0.4500")

    def test_the_same_anomalies_in_another_order_are_the_same_bytes(self) -> None:
        from hunter_core.strategies.canonical import canonical_json
        from packages.indicators.tests.scoring import anomaly

        pair = [anomaly(AnomalyType.VOLUME_SPIKE, "80"), anomaly(AnomalyType.MOMENTUM_SHIFT, "60")]
        first = score_anomaly_component(
            component_for("anomalies"), weight=Decimal("0.05"), anomalies=pair
        )
        second = score_anomaly_component(
            component_for("anomalies"), weight=Decimal("0.05"), anomalies=list(reversed(pair))
        )
        assert canonical_json(first.as_wire()) == canonical_json(second.as_wire())

    def test_the_regime_component_reads_the_pair_against_the_direction(self) -> None:
        component = score_regime_component(
            component_for("market_regime"),
            weight=Decimal("0.10"),
            regime=regime_decision(),
            direction=TradeDirection.LONG,
        )
        assert component.normalized == Decimal("80.0000")
        assert component.transform == "regime_compat_v1"
        component = score_regime_component(
            component_for("market_regime"),
            weight=Decimal("0.10"),
            regime=regime_decision(),
            direction=TradeDirection.SHORT,
        )
        assert component.normalized == Decimal("20.0000")

    def test_high_volatility_penalises_both_sides(self) -> None:
        component = score_regime_component(
            component_for("market_regime"),
            weight=Decimal("0.10"),
            regime=regime_decision(volatility=RegimeVolatility.HIGH),
            direction=TradeDirection.LONG,
        )
        # the projected label is HIGH_VOLATILITY; the pair is still bull
        assert component.detail["trend"] == RegimeTrend.BULL.value
        assert component.normalized == Decimal("65.0000")

    def test_a_direction_nobody_claimed_is_neither_compatible_nor_not(self) -> None:
        component = score_regime_component(
            component_for("market_regime"),
            weight=Decimal("0.10"),
            regime=regime_decision(),
            direction=TradeDirection.NEUTRAL,
        )
        assert component.normalized == Decimal("50.0000")

    def test_an_unknown_regime_is_unavailable_rather_than_neutral(self) -> None:
        component = score_regime_component(
            component_for("market_regime"),
            weight=Decimal("0.10"),
            regime=None,
            direction=TradeDirection.LONG,
        )
        assert component.available is False
        assert component.reason == REASON_REGIME_UNKNOWN

    def test_a_stale_regime_is_for_display_never_for_a_score(self) -> None:
        component = score_regime_component(
            component_for("market_regime"),
            weight=Decimal("0.10"),
            regime=regime_decision(),
            direction=TradeDirection.LONG,
            stale=True,
        )
        assert component.available is False
        assert component.reason == "regime_stale"

    def test_agent_consensus_is_a_known_zero_until_m4(self) -> None:
        component = score_consensus_component(component_for("agent_consensus"), weight=Decimal("0"))
        assert component.available is True
        assert component.normalized == Decimal("0.0000")
        # available components carry no ``reason``: that field says why one could
        # not be read (cross review, nice-to-have 6)
        assert component.reason is None
        assert component.detail["status"] == "no_agents_until_m4"
        assert component.kind is ComponentKind.CONSENSUS

    def test_a_weighted_consensus_would_be_unavailable_and_say_so(self) -> None:
        component = score_consensus_component(
            component_for("agent_consensus"), weight=Decimal("0.05")
        )
        assert component.available is False
        assert component.reason == "no_agents_until_m4"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", "0.00"), ("1.25", "0.00"), ("1.5", "20.00"), ("2", "60.00"), ("3", "100.00")],
)
def test_the_piecewise_transformation_is_the_one_t23_published(value: str, expected: str) -> None:
    component = mad_component("volume", {"relative_volume_5m": value}, weight="0.20")
    assert component.inputs[0].severity == Decimal(expected)
