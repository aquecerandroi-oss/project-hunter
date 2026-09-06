"""The internal statistics of the regime classifier, on synthetic series.

``return_1d`` and the volatility estimator are **not** registered features (the
T2.2 set has neither), so they are computed here from the persisted 1-minute
candles the caller hands over — and the numbers below are the arithmetic, not a
description of it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.regime import (
    REASON_NO_DISPERSION,
    REASON_VOLATILITY_WARMUP,
    HourlySample,
    RegimeThresholds,
    hourly_samples,
    return_over,
    trailing_volatility,
    volatility_reference,
)
from packages.indicators.tests.factories import candle, flat_series, series

HOUR = timedelta(hours=1)
MINUTE = timedelta(minutes=1)
START = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)


def _minutes(n: int, *, closes: list[Decimal] | None = None, start: datetime = START):
    if closes is None:
        return flat_series(n, start=start)
    return series(closes, start=start)


class TestReturnOverMinutes:
    def test_the_return_is_the_close_to_close_fraction(self) -> None:
        candles = _minutes(0, closes=[Decimal("100")] * 1440 + [Decimal("110")])
        as_of = START + 1441 * MINUTE
        assert return_over(candles, minutes=1440, as_of=as_of) == Decimal("0.1")

    def test_a_window_that_is_not_covered_has_no_return(self) -> None:
        candles = _minutes(10)
        as_of = START + 10 * MINUTE
        assert return_over(candles, minutes=1440, as_of=as_of) is None

    def test_a_candle_still_forming_is_never_read(self) -> None:
        closed = _minutes(0, closes=[Decimal("100")] * 61)
        forming = candle(START + 61 * MINUTE, close=Decimal("999"), is_final=False)
        as_of = START + 62 * MINUTE
        with_forming = [*closed, forming]
        assert return_over(with_forming, minutes=60, as_of=as_of) == return_over(
            closed, minutes=60, as_of=as_of
        )

    def test_a_zero_reference_price_has_no_return(self) -> None:
        candles = _minutes(0, closes=[Decimal("0")] * 61)
        assert return_over(candles, minutes=60, as_of=START + 61 * MINUTE) is None


class TestTrailingVolatility:
    def test_the_estimator_is_the_mean_absolute_one_minute_return(self) -> None:
        # 61 closes -> 60 returns, one single +1% move and 59 zeros.
        closes = [Decimal("100")] * 60 + [Decimal("101")]
        candles = _minutes(0, closes=closes)
        as_of = START + 61 * MINUTE
        # 0.01 / 60 = 0.000166666666666666...
        assert trailing_volatility(candles, as_of=as_of, thresholds=RegimeThresholds()) == Decimal(
            "0.0001666667"
        )

    def test_sixty_returns_need_sixty_one_closes(self) -> None:
        candles = _minutes(60)
        assert (
            trailing_volatility(candles, as_of=START + 60 * MINUTE, thresholds=RegimeThresholds())
            is None
        )

    def test_a_short_window_is_refused_rather_than_estimated(self) -> None:
        candles = _minutes(30)
        as_of = START + 30 * MINUTE
        assert trailing_volatility(candles, as_of=as_of, thresholds=RegimeThresholds()) is None

    def test_a_gap_inside_the_window_refuses_the_estimate(self) -> None:
        # sixty-one candles, so only the hole (minute 30) can refuse the estimate
        head = _minutes(0, closes=[Decimal("100")] * 30)
        tail = _minutes(0, closes=[Decimal("100")] * 31, start=START + 31 * MINUTE)
        as_of = START + 62 * MINUTE
        assert (
            trailing_volatility([*head, *tail], as_of=as_of, thresholds=RegimeThresholds()) is None
        )


class TestHourlySamples:
    def test_samples_are_hour_aligned_and_stop_before_the_observation(self) -> None:
        candles = _minutes(0, closes=[Decimal("100")] * 180)
        # 03:00 is the observation; hours 01 and 02 are sampled, and hour 00 is
        # not: nothing precedes it, so it has no anchor close.
        samples = hourly_samples(
            candles, until=START + 3 * HOUR, thresholds=RegimeThresholds(), days=30
        )
        assert [item.hour_start for item in samples] == [START + HOUR, START + 2 * HOUR]
        assert {item.minutes_used for item in samples} == {60}

    def test_an_hour_missing_minutes_is_not_sampled(self) -> None:
        head = _minutes(0, closes=[Decimal("100")] * 30, start=START + 30 * MINUTE)  # half of 00
        tail = _minutes(0, closes=[Decimal("100")] * 60, start=START + HOUR)
        samples = hourly_samples(
            [*head, *tail], until=START + 2 * HOUR, thresholds=RegimeThresholds(), days=30
        )
        assert [item.hour_start for item in samples] == [START + HOUR]

    def test_the_return_across_the_hour_boundary_is_not_lost(self) -> None:
        """Astra, T2.4 diff review: without the anchor close, an hour that opens
        with a jump reads as perfectly calm and the reference becomes zero."""
        closes = [Decimal("100")] * 60 + [Decimal("101")] * 60
        candles = _minutes(0, closes=closes)
        thresholds = RegimeThresholds(volatility_min_samples=1, volatility_min_distinct_days=1)
        samples = hourly_samples(candles, until=START + 2 * HOUR, thresholds=thresholds, days=30)
        assert [item.hour_start for item in samples] == [START + HOUR]
        assert samples[0].value > 0
        assert volatility_reference(samples, thresholds).usable is True

    def test_the_window_does_not_reach_further_than_the_declared_days(self) -> None:
        candles = _minutes(0, closes=[Decimal("100")] * 120)
        samples = hourly_samples(
            candles, until=START + 2 * HOUR, thresholds=RegimeThresholds(), days=0
        )
        assert samples == ()


class TestVolatilityReference:
    def _samples(self, values: list[str], *, start: datetime = START) -> list[HourlySample]:
        return [
            HourlySample(hour_start=start + i * HOUR, value=Decimal(v), minutes_used=60)
            for i, v in enumerate(values)
        ]

    def test_a_thin_history_is_warming_up_and_says_so(self) -> None:
        reference = volatility_reference(self._samples(["1", "2", "3"]), RegimeThresholds())
        assert reference.usable is False
        assert reference.reason == REASON_VOLATILITY_WARMUP
        assert reference.median is None

    def test_the_reference_is_the_median_of_the_hourly_samples(self) -> None:
        thresholds = RegimeThresholds(volatility_min_samples=4, volatility_min_distinct_days=1)
        reference = volatility_reference(self._samples(["1", "2", "3", "10"]), thresholds)
        assert reference.usable is True
        assert reference.median == Decimal("2.5")
        assert reference.samples == 4
        assert reference.distinct_days == 1

    def test_a_reference_without_dispersion_is_refused(self) -> None:
        thresholds = RegimeThresholds(volatility_min_samples=4, volatility_min_distinct_days=1)
        reference = volatility_reference(self._samples(["0", "0", "0", "0"]), thresholds)
        assert reference.usable is False
        assert reference.reason == REASON_NO_DISPERSION


class TestThresholdsAreVersioned:
    def test_the_shipped_thresholds_publish_the_bare_version(self) -> None:
        assert RegimeThresholds().identity == "regime_v0"

    def test_an_overridden_threshold_travels_under_another_identity(self) -> None:
        other = RegimeThresholds(trend_4h_atr_multiple=Decimal("3"))
        assert other.identity != "regime_v0"
        assert other.identity.startswith("regime_v0+")

    def test_the_parameters_are_serialisable_for_the_envelope(self) -> None:
        wire = RegimeThresholds().as_wire()
        assert wire["trend_4h_atr_multiple"] == Decimal("2")
        assert wire["confirmations"] == 3


@pytest.mark.parametrize("days", [1, 7, 30])
def test_the_sampled_window_is_bounded_by_days(days: int) -> None:
    candles = _minutes(0, closes=[Decimal("100")] * (31 * 24 * 60), start=START)
    until = START + timedelta(days=31)
    samples = hourly_samples(candles, until=until, thresholds=RegimeThresholds(), days=days)
    assert len(samples) == days * 24  # every hour of the span has its anchor
