"""Regime v0: trend, breadth, volatility, hysteresis and the stale stamp."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import MarketRegime
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.regime import (
    REASON_BREADTH_COVERAGE,
    REASON_NO_TREND_INPUT,
    REASON_STALE_OBSERVATION,
    REASON_VOLATILITY_WARMUP,
    Breadth,
    BreadthObservation,
    RegimeObservation,
    RegimeState,
    RegimeThresholds,
    RegimeTrend,
    RegimeVolatility,
    VolatilityReference,
    advance_regime,
    classify_market_trend,
    classify_regime,
    compute_breadth,
    evaluate_regime,
    regime_for_display,
)

TS = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)
THRESHOLDS = RegimeThresholds()


def reference(median: str = "0.001") -> VolatilityReference:
    return VolatilityReference(
        median=Decimal(median),
        samples=600,
        distinct_days=25,
        window_days=30,
        usable=True,
    )


WARMING_UP = VolatilityReference(
    median=None,
    samples=10,
    distinct_days=1,
    window_days=30,
    usable=False,
    reason=REASON_VOLATILITY_WARMUP,
)


def observation(
    *,
    ts: datetime = TS,
    return_4h: str | None = "0.06",
    return_1d: str | None = "0.12",
    atr_pct: str | None = "0.02",
    volatility: str | None = "0.001",
) -> RegimeObservation:
    return RegimeObservation(
        observation_ts=ts,
        return_4h=None if return_4h is None else Decimal(return_4h),
        return_1d=None if return_1d is None else Decimal(return_1d),
        atr_pct=None if atr_pct is None else Decimal(atr_pct),
        volatility=None if volatility is None else Decimal(volatility),
    )


def full_breadth(fraction: str = "0.7") -> Breadth:
    return Breadth(
        fraction=Decimal(fraction),
        coverage=Decimal("1"),
        universe_size=10,
        usable_markets=10,
        advancing=7,
        usable=True,
    )


class TestTrendOfOneMarket:
    def test_a_move_beyond_both_multiples_is_a_trend(self) -> None:
        reading = classify_market_trend(
            "BTCUSDT",
            return_4h=Decimal("0.06"),  # 3 ATRs, above the 2 required
            return_1d=Decimal("0.12"),  # 6 ATRs, above the 4 required
            atr_pct=Decimal("0.02"),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.BULL
        assert reading.r_4h == Decimal("3")
        assert reading.r_1d == Decimal("6")

    def test_the_two_horizons_must_agree_on_the_side(self) -> None:
        reading = classify_market_trend(
            "BTCUSDT",
            return_4h=Decimal("0.06"),
            return_1d=Decimal("-0.12"),
            atr_pct=Decimal("0.02"),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.SIDEWAYS

    def test_a_move_inside_the_noise_is_sideways(self) -> None:
        reading = classify_market_trend(
            "BTCUSDT",
            return_4h=Decimal("0.01"),
            return_1d=Decimal("0.02"),
            atr_pct=Decimal("0.02"),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.SIDEWAYS

    def test_a_falling_market_is_bear(self) -> None:
        reading = classify_market_trend(
            "BTCUSDT",
            return_4h=Decimal("-0.06"),
            return_1d=Decimal("-0.12"),
            atr_pct=Decimal("0.02"),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.BEAR

    def test_without_an_atr_there_is_no_scale_and_no_trend(self) -> None:
        reading = classify_market_trend(
            "BTCUSDT",
            return_4h=Decimal("0.06"),
            return_1d=Decimal("0.12"),
            atr_pct=Decimal("0"),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.UNKNOWN
        assert reading.reason == "atr_warmup"

    def test_a_missing_return_is_not_a_zero_return(self) -> None:
        reading = classify_market_trend(
            "BTCUSDT",
            return_4h=None,
            return_1d=Decimal("0.12"),
            atr_pct=Decimal("0.02"),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.UNKNOWN
        assert reading.reason == REASON_NO_TREND_INPUT


class TestBreadth:
    def _observations(self, advancing: int, total: int) -> list[BreadthObservation]:
        out: list[BreadthObservation] = []
        for index in range(total):
            up = index < advancing
            out.append(
                BreadthObservation(
                    market=f"M{index:03d}",
                    return_4h=Decimal("0.05") if up else Decimal("-0.05"),
                    relative_volume_1h=Decimal("2") if up else Decimal("1"),
                )
            )
        return out

    def test_the_fraction_counts_markets_advancing_with_volume(self) -> None:
        breadth = compute_breadth(
            self._observations(7, 10), universe_size=10, thresholds=THRESHOLDS
        )
        assert breadth.usable is True
        assert breadth.fraction == Decimal("0.7")
        assert breadth.advancing == 7
        assert breadth.members == tuple(f"M{i:03d}" for i in range(7))

    def test_volume_is_required_not_only_a_positive_return(self) -> None:
        observations = [
            BreadthObservation(
                market="A", return_4h=Decimal("0.05"), relative_volume_1h=Decimal("1.2")
            ),
            BreadthObservation(
                market="B", return_4h=Decimal("0.05"), relative_volume_1h=Decimal("2")
            ),
        ]
        breadth = compute_breadth(observations, universe_size=2, thresholds=THRESHOLDS)
        assert breadth.advancing == 1
        assert breadth.members == ("B",)

    def test_thin_coverage_makes_the_confirmation_unavailable_not_bearish(self) -> None:
        observations = self._observations(0, 7) + [
            BreadthObservation(market="X", return_4h=None, relative_volume_1h=None)
            for _ in range(3)
        ]
        breadth = compute_breadth(observations, universe_size=10, thresholds=THRESHOLDS)
        assert breadth.usable is False
        assert breadth.reason == REASON_BREADTH_COVERAGE
        assert breadth.fraction is None
        assert breadth.coverage == Decimal("0.7")

    def test_every_excluded_market_says_why(self) -> None:
        observations = [
            BreadthObservation(market="A", return_4h=None, relative_volume_1h=Decimal("2")),
            BreadthObservation(market="B", return_4h=Decimal("0.05"), relative_volume_1h=None),
        ]
        breadth = compute_breadth(observations, universe_size=2, thresholds=THRESHOLDS)
        assert dict(breadth.excluded) == {
            "A": "missing_return_4h",
            "B": "missing_relative_volume_1h",
        }

    def test_an_empty_universe_is_not_a_hundred_percent_covered(self) -> None:
        breadth = compute_breadth([], universe_size=0, thresholds=THRESHOLDS)
        assert breadth.usable is False
        assert breadth.coverage == Decimal("0")


class TestEvaluateReading:
    def test_a_calm_trending_market_reads_bull_normal(self) -> None:
        reading = evaluate_regime(
            observation=observation(),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        assert reading.trend is RegimeTrend.BULL
        assert reading.volatility is RegimeVolatility.NORMAL
        assert reading.regime is MarketRegime.BTC_BULL

    def test_twice_the_median_volatility_is_high(self) -> None:
        reading = evaluate_regime(
            observation=observation(volatility="0.002"),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        assert reading.volatility is RegimeVolatility.HIGH
        assert reading.regime is MarketRegime.HIGH_VOLATILITY
        assert reading.values["volatility_ratio"] == Decimal("2")

    def test_half_the_median_volatility_is_low(self) -> None:
        reading = evaluate_regime(
            observation=observation(return_4h="0.001", return_1d="0.002", volatility="0.0005"),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        assert reading.volatility is RegimeVolatility.LOW
        assert reading.regime is MarketRegime.LOW_VOLATILITY

    def test_the_volatility_warmup_makes_the_regime_unknown_with_a_reason(self) -> None:
        reading = evaluate_regime(
            observation=observation(),
            reference=WARMING_UP,
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        assert reading.known is False
        assert reading.regime is MarketRegime.UNKNOWN
        assert reading.reason == REASON_VOLATILITY_WARMUP
        # the trend it could compute survives as evidence, not as a classification
        assert reading.trend is RegimeTrend.BULL

    def test_a_missing_trend_input_is_unknown_too(self) -> None:
        reading = evaluate_regime(
            observation=observation(return_1d=None),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        assert reading.known is False
        assert reading.reason == REASON_NO_TREND_INPUT


class TestHysteresis:
    def _bull(self, ts: datetime):
        return evaluate_regime(
            observation=observation(ts=ts),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )

    def test_three_readings_are_needed_to_publish(self) -> None:
        state = RegimeState()
        published: list[MarketRegime] = []
        for index in range(3):
            decision = advance_regime(state, self._bull(TS + index * MINUTE), THRESHOLDS)
            state = decision.state_out
            published.append(decision.regime)
        assert published == [MarketRegime.UNKNOWN, MarketRegime.UNKNOWN, MarketRegime.BTC_BULL]
        assert state.confirmations == 0

    def test_the_third_reading_marks_the_transition(self) -> None:
        state = RegimeState()
        decision = advance_regime(state, self._bull(TS), THRESHOLDS)
        assert decision.changed is False
        state = decision.state_out
        state = advance_regime(state, self._bull(TS + MINUTE), THRESHOLDS).state_out
        decision = advance_regime(state, self._bull(TS + 2 * MINUTE), THRESHOLDS)
        assert decision.changed is True
        assert decision.state_out.published_at == TS + 2 * MINUTE

    def test_an_interrupted_run_starts_again(self) -> None:
        state = RegimeState()
        state = advance_regime(state, self._bull(TS), THRESHOLDS).state_out
        sideways = evaluate_regime(
            observation=observation(ts=TS + MINUTE, return_4h="0", return_1d="0"),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        state = advance_regime(state, sideways, THRESHOLDS).state_out
        assert state.confirmations == 1
        assert state.candidate_trend is RegimeTrend.SIDEWAYS

    def test_blindness_publishes_at_once_and_needs_no_confirmation(self) -> None:
        state = RegimeState()
        for index in range(3):
            state = advance_regime(state, self._bull(TS + index * MINUTE), THRESHOLDS).state_out
        assert state.regime is MarketRegime.BTC_BULL
        blind = evaluate_regime(
            observation=observation(ts=TS + 3 * MINUTE),
            reference=WARMING_UP,
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        decision = advance_regime(state, blind, THRESHOLDS)
        assert decision.regime is MarketRegime.UNKNOWN
        assert decision.changed is True
        assert decision.confidence is None

    def test_a_redelivered_reading_confirms_nothing(self) -> None:
        state = RegimeState()
        state = advance_regime(state, self._bull(TS), THRESHOLDS).state_out
        decision = advance_regime(state, self._bull(TS), THRESHOLDS)
        assert decision.state_out == state
        assert decision.reason == REASON_STALE_OBSERVATION

    def test_the_hysteresis_follows_the_pair_not_the_projected_label(self) -> None:
        """Two pairs project onto ``HIGH_VOLATILITY``; the trend under it may not
        flip without its own three readings."""
        state = RegimeState()
        violent_bull = evaluate_regime(
            observation=observation(volatility="0.003"),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        for index in range(3):
            reading = evaluate_regime(
                observation=observation(ts=TS + index * MINUTE, volatility="0.003"),
                reference=reference(),
                breadth=full_breadth(),
                thresholds=THRESHOLDS,
            )
            state = advance_regime(state, reading, THRESHOLDS).state_out
        assert state.regime is MarketRegime.HIGH_VOLATILITY
        assert violent_bull.trend is RegimeTrend.BULL
        violent_bear = evaluate_regime(
            observation=observation(
                ts=TS + 3 * MINUTE, return_4h="-0.06", return_1d="-0.12", volatility="0.003"
            ),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        decision = advance_regime(state, violent_bear, THRESHOLDS)
        assert decision.regime is MarketRegime.HIGH_VOLATILITY
        assert decision.trend is RegimeTrend.BULL  # still the published pair
        assert decision.state_out.candidate_trend is RegimeTrend.BEAR


class TestConfidence:
    def _publish(self, breadth: Breadth):
        state = RegimeState()
        decision = None
        for index in range(3):
            reading = evaluate_regime(
                observation=observation(ts=TS + index * MINUTE),
                reference=reference(),
                breadth=breadth,
                thresholds=THRESHOLDS,
            )
            decision = advance_regime(state, reading, THRESHOLDS)
            state = decision.state_out
        assert decision is not None
        return decision

    def test_an_agreeing_breadth_gives_full_confidence(self) -> None:
        assert self._publish(full_breadth("0.7")).confidence == Decimal("1.0000")

    def test_a_disagreeing_breadth_lowers_it(self) -> None:
        assert self._publish(full_breadth("0.2")).confidence == Decimal("0.6000")

    def test_an_unavailable_breadth_is_not_a_disagreement(self) -> None:
        thin = Breadth(
            fraction=None,
            coverage=Decimal("0.5"),
            universe_size=10,
            usable_markets=5,
            advancing=0,
            usable=False,
            reason=REASON_BREADTH_COVERAGE,
        )
        assert self._publish(thin).confidence == Decimal("0.7500")


class TestDecisionEnvelope:
    def test_the_supporting_features_carry_the_whole_evidence(self) -> None:
        decision = classify_regime(
            state=RegimeState(),
            observation=observation(),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        supporting = decision.supporting_features()
        assert supporting["classifier_version"] == "regime_v0"
        assert supporting["thresholds"]["trend_4h_atr_multiple"] == Decimal("2")
        assert supporting["reading"]["breadth"]["members"] == []
        assert supporting["state_in"]["confirmations"] == 0

    def test_the_same_evidence_serialises_to_the_same_bytes(self) -> None:
        first = classify_regime(
            state=RegimeState(),
            observation=observation(),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        second = classify_regime(
            state=RegimeState(),
            observation=observation(),
            reference=reference(),
            breadth=full_breadth(),
            thresholds=THRESHOLDS,
        )
        assert canonical_json(first.supporting_features()) == canonical_json(
            second.supporting_features()
        )


class TestDisplay:
    def test_a_fresh_regime_is_not_stale(self) -> None:
        state = RegimeState(
            trend=RegimeTrend.BULL,
            volatility=RegimeVolatility.NORMAL,
            last_observation_ts=TS,
        )
        display = regime_for_display(state, as_of=TS + MINUTE, thresholds=THRESHOLDS)
        assert display.regime is MarketRegime.BTC_BULL
        assert display.stale is False
        assert display.age_s == Decimal("60")

    def test_an_old_regime_is_shown_with_the_stamp(self) -> None:
        state = RegimeState(
            trend=RegimeTrend.BULL,
            volatility=RegimeVolatility.NORMAL,
            last_observation_ts=TS,
        )
        display = regime_for_display(state, as_of=TS + 10 * MINUTE, thresholds=THRESHOLDS)
        assert display.regime is MarketRegime.BTC_BULL
        assert display.stale is True

    def test_nothing_was_ever_classified(self) -> None:
        display = regime_for_display(RegimeState(), as_of=TS, thresholds=THRESHOLDS)
        assert display.regime is MarketRegime.UNKNOWN
        assert display.stale is True
        assert display.age_s is None


class TestCrossReviewT24:
    """The regime half of the cross review: the tie, the label and the confidence."""

    def _publish(self, breadth: Breadth, *, bear: bool = False):
        state = RegimeState()
        decision = None
        for index in range(THRESHOLDS.confirmations):
            reading = evaluate_regime(
                observation=observation(
                    ts=TS + index * MINUTE,
                    return_4h="-0.06" if bear else "0.06",
                    return_1d="-0.12" if bear else "0.12",
                ),
                reference=reference(),
                breadth=breadth,
                thresholds=THRESHOLDS,
            )
            decision = advance_regime(state, reading, THRESHOLDS)
            state = decision.state_out
        assert decision is not None
        return decision

    def test_an_exact_breadth_tie_confirms_one_side_only(self) -> None:
        """A number that confirms whatever it is asked about confirms nothing:
        at ``breadth_agreement_min`` the threshold belongs to the upside, so the
        bull is confirmed and the bear needs to be strictly below it (cross
        review, nice-to-have 4)."""
        tie = full_breadth("0.5")
        assert self._publish(tie).trend is RegimeTrend.BULL
        assert self._publish(tie).confidence == Decimal("1.0000")
        assert self._publish(tie, bear=True).trend is RegimeTrend.BEAR
        assert self._publish(tie, bear=True).confidence == Decimal("0.6000")

    def test_below_the_tie_the_bear_is_confirmed_and_the_bull_is_not(self) -> None:
        thin = full_breadth("0.4999")
        assert self._publish(thin, bear=True).confidence == Decimal("1.0000")
        assert self._publish(thin).confidence == Decimal("0.6000")

    def test_the_confidence_is_part_of_the_supporting_features(self) -> None:
        decision = self._publish(full_breadth("0.7"))
        supporting = decision.supporting_features()
        assert supporting["confidence"] == Decimal("1.0000")
        assert supporting["confidence"] == decision.confidence

    def test_the_pair_can_change_without_the_label_changing(self) -> None:
        """``bull+high`` and ``bear+high`` are both ``HIGH_VOLATILITY``: the row
        and the event have to be able to tell the two apart (nice-to-have 3)."""
        state = RegimeState()
        for index in range(THRESHOLDS.confirmations):
            reading = evaluate_regime(
                observation=observation(ts=TS + index * MINUTE, volatility="0.003"),
                reference=reference(),
                breadth=full_breadth(),
                thresholds=THRESHOLDS,
            )
            state = advance_regime(state, reading, THRESHOLDS).state_out
        decision = None
        for index in range(THRESHOLDS.confirmations):
            reading = evaluate_regime(
                observation=observation(
                    ts=TS + (3 + index) * MINUTE,
                    return_4h="-0.06",
                    return_1d="-0.12",
                    volatility="0.003",
                ),
                reference=reference(),
                breadth=full_breadth(),
                thresholds=THRESHOLDS,
            )
            decision = advance_regime(state, reading, THRESHOLDS)
            state = decision.state_out
        assert decision is not None
        assert decision.changed is True  # the pair moved: bull+high -> bear+high
        assert decision.label_changed is False  # both project onto HIGH_VOLATILITY
        assert decision.regime is MarketRegime.HIGH_VOLATILITY
        assert decision.trend is RegimeTrend.BEAR
        assert decision.supporting_features()["label_changed"] is False

    def test_a_label_change_is_a_pair_change_too(self) -> None:
        state = RegimeState()
        decision = None
        for index in range(THRESHOLDS.confirmations):
            reading = evaluate_regime(
                observation=observation(ts=TS + index * MINUTE),
                reference=reference(),
                breadth=full_breadth(),
                thresholds=THRESHOLDS,
            )
            decision = advance_regime(state, reading, THRESHOLDS)
            state = decision.state_out
        assert decision is not None
        assert decision.regime is MarketRegime.BTC_BULL
        assert decision.changed is True
        assert decision.label_changed is True

    def test_a_reading_that_publishes_nothing_changed_neither(self) -> None:
        decision = self._publish(full_breadth("0.7"))
        again = advance_regime(
            decision.state_out,
            evaluate_regime(
                observation=observation(ts=TS + 5 * MINUTE),
                reference=reference(),
                breadth=full_breadth("0.7"),
                thresholds=THRESHOLDS,
            ),
            THRESHOLDS,
        )
        assert again.changed is False
        assert again.label_changed is False
