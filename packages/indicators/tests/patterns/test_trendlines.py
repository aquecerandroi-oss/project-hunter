"""Trend lines and channels over the synthetic wave — every number by hand."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.patterns.channels import find_channels
from hunter_indicators.patterns.pivots import find_pivots
from hunter_indicators.patterns.scale import atr_series
from hunter_indicators.patterns.scan import scan
from hunter_indicators.patterns.trendlines import LineKind, find_lines
from packages.indicators.tests.patterns.builders import (
    bars,
    replace_bar,
    resistance_price,
    support_price,
    walk,
    wave_low,
)

pytestmark = pytest.mark.unit

K = 3
PIVOT_K = 3
MIN_TOUCHES = 3
ATR_PERIOD = 14


def _lines(series: tuple[Bar, ...], **kwargs: object):
    atr = atr_series(series, period=ATR_PERIOD, timeframe=Timeframe.M15)
    pivots = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"))
    return find_lines(series, atr, pivots, **kwargs), atr  # type: ignore[arg-type]


def test_three_lows_on_a_line_make_exactly_one_support_line() -> None:
    series = bars(42)
    lines, _atr = _lines(series)

    support = [line for line in lines if line.kind is LineKind.SUPPORT]
    assert len(support) == 1, "the three collinear pairs must collapse into one line"
    line = support[0]
    assert line.touches == 3
    assert line.slope_per_bar == Decimal("0.5")
    assert line.anchors == ((15, wave_low(15)), (25, wave_low(25)), (35, wave_low(35)))
    assert (line.first_idx, line.last_idx) == (15, 35)
    assert line.valid_from_idx == 38, "the third touch is only confirmed k bars later"
    assert line.violations == 0
    assert line.score == Decimal(3 * 20)
    assert line.projected(41) == support_price(41)


def test_two_pivots_are_not_a_trend_line() -> None:
    """42 bars only confirm two peaks; a line needs the third touch."""
    series = bars(42)
    lines, _atr = _lines(series)

    assert [line.kind for line in lines] == [LineKind.SUPPORT]


def test_two_closes_through_the_line_invalidate_it() -> None:
    series = bars(42)
    for index in (28, 29):
        low = support_price(index) - Decimal("8")
        series = replace_bar(series, index, low=low, close=low + Decimal("0.5"))

    lines, _atr = _lines(series)

    assert not [line for line in lines if line.kind is LineKind.SUPPORT]


def test_parallel_support_and_resistance_are_a_channel() -> None:
    series = bars(52)
    lines, atr = _lines(series)

    support = next(line for line in lines if line.kind is LineKind.SUPPORT)
    resistance = next(line for line in lines if line.kind is LineKind.RESISTANCE)
    assert support.touches == 4 and resistance.touches == 3
    assert support.slope_per_bar == resistance.slope_per_bar == Decimal("0.5")

    channels = find_channels(lines, atr)
    assert len(channels) == 1
    channel = channels[0]
    assert channel.upper is resistance and channel.lower is support
    width = resistance_price(51) - support_price(51)
    assert width == Decimal("9.5")
    scale = atr[51]
    assert scale is not None
    assert channel.width_atr == width / scale


def test_a_line_only_exists_at_the_cut_that_confirmed_it() -> None:
    series = bars(42)
    atr = atr_series(series, period=ATR_PERIOD, timeframe=Timeframe.M15)
    pivots = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"))

    assert find_lines(series, atr, pivots, as_of=37) == ()
    assert len(find_lines(series, atr, pivots, as_of=38)) == 1


def test_prices_stay_decimal_all_the_way_through() -> None:
    series = bars(42)
    lines, _atr = _lines(series)
    line = lines[0]

    assert isinstance(line.slope_per_bar, Decimal)
    assert all(isinstance(price, Decimal) for _index, price in line.anchors)
    assert isinstance(line.projected(100), Decimal)
    assert line.projected(100) == Decimal("107.5") + Decimal("0.5") * Decimal(85)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(st.integers(min_value=-40, max_value=40), min_size=150, max_size=220))
def test_the_line_that_is_reported_is_the_line_that_was_validated(steps: list[int]) -> None:
    """Whatever geometry passed the touch and respect tests is the geometry drawn.

    Astra, T3.34 review, must-fix 1: the candidate was validated with the slope
    and origin of the generating pair, but ``projected()`` re-anchored on the
    first *touch*, which is only within ``tolerance_atr`` of it. Measured on the
    real series the drift reached 0.485 ATR and one reported line failed its own
    respect rule.
    """
    series = walk(steps)
    result = scan(series, timeframe=Timeframe.M15)

    tolerance = Decimal("0.25")
    for line in result.lines:
        for index, price in line.anchors:
            scale = result.atr[index]
            assert scale is not None
            assert abs(price - line.projected(index)) <= tolerance * scale
        for index in range(line.first_idx, line.last_idx + 1):
            scale = result.atr[index]
            if scale is None:
                continue
            level = line.projected(index)
            close = series[index].close
            beyond = close - level if line.kind is LineKind.RESISTANCE else level - close
            assert beyond <= tolerance * scale


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(steps=st.lists(st.integers(min_value=-40, max_value=40), min_size=150, max_size=220))
def test_a_line_is_never_valid_before_its_own_geometry_was_knowable(steps: list[int]) -> None:
    """Astra, T3.34 review, must-fix 2: the two pivots that fix the slope have to
    be confirmed before the line can be said to exist — otherwise the events
    searched from ``valid_from_idx`` are computed against a future slope.
    """
    series = walk(steps)
    result = scan(series, timeframe=Timeframe.M15)

    for line in result.lines:
        assert line.valid_from_idx >= line.origin[0] + PIVOT_K
        assert line.valid_from_idx >= line.through[0] + PIVOT_K
        assert line.valid_from_idx >= line.anchors[MIN_TOUCHES - 1][0] + PIVOT_K


def test_the_line_is_actually_drawable_on_the_bar_it_claims() -> None:
    """The property above says "not before"; this one says "and it is there".

    Deterministic on purpose: at an arbitrary cut the *selection* can differ
    (scores and buckets are evaluated at the cut), so the strong claim is made
    where the answer is known by hand.
    """
    series = bars(62)
    line = next(item for item in scan(series, timeframe=Timeframe.M15).lines)

    earlier = scan(series, timeframe=Timeframe.M15, as_of=line.valid_from_idx)

    assert any(
        other.origin == line.origin
        and other.through == line.through
        and other.slope_per_bar == line.slope_per_bar
        for other in earlier.lines
    )
