"""Swing pivots: confirmation window, ATR significance, and *when* they exist."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.patterns.pivots import PivotKind, find_pivots
from hunter_indicators.patterns.scale import atr_series
from packages.indicators.tests.patterns.builders import ORIGIN, STEP, bars, wave_low

pytestmark = pytest.mark.unit

K = 3
ATR_PERIOD = 14


def _atr(series: tuple[Bar, ...]) -> tuple[Decimal | None, ...]:
    return atr_series(series, period=ATR_PERIOD, timeframe=Timeframe.M15)


def test_the_troughs_of_the_wave_are_the_pivot_lows() -> None:
    series = bars(42)
    pivots = find_pivots(series, _atr(series), k=K, min_swing_atr=Decimal("1.0"))

    lows = [p for p in pivots if p.kind is PivotKind.LOW]
    assert [p.index for p in lows] == [15, 25, 35]
    assert [p.price for p in lows] == [wave_low(15), wave_low(25), wave_low(35)]
    assert [p.confirmed_at for p in lows] == [18, 28, 38]


def test_the_peaks_of_the_wave_are_the_pivot_highs() -> None:
    series = bars(52)
    pivots = find_pivots(series, _atr(series), k=K, min_swing_atr=Decimal("1.0"))

    highs = [p for p in pivots if p.kind is PivotKind.HIGH]
    assert [p.index for p in highs] == [20, 30, 40]
    assert [p.price for p in highs] == [wave_low(i) + Decimal("2") for i in (20, 30, 40)]


def test_a_pivot_does_not_exist_before_its_confirmation_bar() -> None:
    series = bars(52)
    atr = _atr(series)

    at_47 = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"), as_of=47)
    at_48 = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"), as_of=48)

    assert 45 not in [p.index for p in at_47]
    assert 45 in [p.index for p in at_48 if p.kind is PivotKind.LOW]


def test_a_pivot_needs_an_atr_to_be_measured_against() -> None:
    """The first troughs (5, 15) are real swings but land inside the ATR warm-up."""
    series = bars(52)
    atr = _atr(series)
    assert atr[14] is None and atr[15] is not None

    pivots = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"))
    assert min(p.index for p in pivots) >= 15


def _bar(index: int, low: Decimal, height: Decimal) -> Bar:
    return Bar(
        open_time=ORIGIN + index * STEP,
        close_time=ORIGIN + (index + 1) * STEP,
        open=low + height / 2,
        high=low + height,
        low=low,
        close=low + height / 2,
        volume=Decimal("10"),
    )


def _spike_then_quiet(volatile: int = 30, quiet: int = 25) -> tuple[Bar, ...]:
    """Range-10 bars (ATR climbs to 10), then range-0.4 bars wiggling by 0.3.

    The quiet stretch has textbook local extremes; measured against the ATR the
    volatile stretch left behind they are a fraction of one.
    """
    out = [_bar(index, Decimal("100"), Decimal("10")) for index in range(volatile)]
    ladder = (Decimal("0"), Decimal("0.1"), Decimal("0.2"), Decimal("0.3"), Decimal("0.2"))
    for step_index in range(quiet):
        index = volatile + step_index
        out.append(_bar(index, Decimal("100") + ladder[step_index % 5], Decimal("0.4")))
    return tuple(out)


def test_a_wiggle_that_is_small_against_the_current_atr_is_not_a_pivot() -> None:
    series = _spike_then_quiet()
    atr = atr_series(series, period=ATR_PERIOD, timeframe=Timeframe.M15)

    without_filter = find_pivots(series, atr, k=K, min_swing_atr=Decimal("0"))
    with_filter = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"))

    assert [p.index for p in without_filter if p.index >= 30], "the quiet stretch has extremes"
    assert max(p.prominence_atr for p in without_filter) < Decimal("1.0")
    assert with_filter == ()
