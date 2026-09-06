"""Volume features — hand-computed ratios over disjoint windows."""

from __future__ import annotations

from decimal import Decimal

from hunter_indicators.features.context import build_context
from hunter_indicators.features.state import EMPTY_STATE
from hunter_indicators.features.vector import Reason
from hunter_indicators.features.volume import (
    RelativeVolume,
    VolumeAcceleration,
    volume_calculators,
)
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, series


def _ctx(volumes: list[Decimal]):
    candles = series([Decimal("100")] * len(volumes), volumes=volumes)
    return build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=ORIGIN + len(volumes) * MINUTE,
        candles=candles,
    )


class TestRelativeVolume:
    def test_current_window_over_the_median_of_the_previous_ones(self) -> None:
        # four 5-minute windows: sums 10, 20, 30 (previous) and 40 (current)
        volumes = (
            [Decimal("2")] * 5  # 10
            + [Decimal("4")] * 5  # 20
            + [Decimal("6")] * 5  # 30
            + [Decimal("8")] * 5  # 40
        )
        calc = RelativeVolume(window_minutes=5, lookback_windows=3)
        value = calc.compute(_ctx(volumes), EMPTY_STATE)
        assert value.key == "relative_volume_5m"
        assert value.value == Decimal("2")  # 40 / median(10, 20, 30) = 40/20

    def test_the_median_of_an_even_sample_is_the_middle_average(self) -> None:
        volumes = [Decimal("1")] * 2 + [Decimal("3")] * 2 + [Decimal("5")] * 2
        calc = RelativeVolume(window_minutes=2, lookback_windows=2)
        # windows: 2, 6 (previous, median 4) and 10 (current) -> 10/4 = 2.5
        assert calc.compute(_ctx(volumes), EMPTY_STATE).value == Decimal("2.5")

    def test_a_silent_baseline_has_no_ratio(self) -> None:
        volumes = [Decimal("0")] * 10 + [Decimal("5")] * 5
        calc = RelativeVolume(window_minutes=5, lookback_windows=2)
        assert calc.compute(_ctx(volumes), EMPTY_STATE).reason is Reason.ZERO_DIVISOR

    def test_a_silent_current_window_is_a_real_zero(self) -> None:
        volumes = [Decimal("5")] * 10 + [Decimal("0")] * 5
        calc = RelativeVolume(window_minutes=5, lookback_windows=2)
        assert calc.compute(_ctx(volumes), EMPTY_STATE).value == Decimal("0")

    def test_warmup_before_the_lookback_is_complete(self) -> None:
        calc = RelativeVolume(window_minutes=5, lookback_windows=3)
        assert calc.compute(_ctx([Decimal("1")] * 15), EMPTY_STATE).reason is Reason.WARMUP

    def test_the_definition_states_the_denominator(self) -> None:
        definition = RelativeVolume(window_minutes=60, lookback_windows=23).definition
        assert definition.key == "relative_volume_1h"
        assert definition.params == {
            "window_minutes": 60,
            "lookback_windows": 23,
            "statistic": "median",
        }


class TestVolumeAcceleration:
    def test_growth_between_two_consecutive_windows(self) -> None:
        volumes = [Decimal("2")] * 5 + [Decimal("3")] * 5  # 10 then 15
        calc = VolumeAcceleration(window_minutes=5)
        value = calc.compute(_ctx(volumes), EMPTY_STATE)
        assert value.key == "volume_acceleration"
        assert value.value == Decimal("0.5")  # (15 - 10) / 10

    def test_a_drop_is_negative(self) -> None:
        volumes = [Decimal("4")] * 5 + [Decimal("1")] * 5  # 20 then 5
        calc = VolumeAcceleration(window_minutes=5)
        assert calc.compute(_ctx(volumes), EMPTY_STATE).value == Decimal("-0.75")

    def test_a_silent_previous_window_has_no_acceleration(self) -> None:
        volumes = [Decimal("0")] * 5 + [Decimal("1")] * 5
        calc = VolumeAcceleration(window_minutes=5)
        assert calc.compute(_ctx(volumes), EMPTY_STATE).reason is Reason.ZERO_DIVISOR


def test_the_registered_v1_set_is_frozen() -> None:
    assert [calc.definition.key for calc in volume_calculators()] == [
        "relative_volume_15m",
        "relative_volume_1h",
        "relative_volume_5m",
        "volume_acceleration",
    ]
