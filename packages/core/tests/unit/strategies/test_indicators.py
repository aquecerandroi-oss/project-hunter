"""Pure indicators — Wilder ATR(14), medians, relative volume, returns.

The ATR expectations are computed by hand from the definition
(``TR = max(h-l, |h-prev_close|, |l-prev_close|)``, seed = simple mean of the
first ``period`` true ranges, then ``ATR_i = (ATR_{i-1}(p-1) + TR_i)/p``), never
read off the implementation — SHADOW-LAB.md §7 and docs/plans/M2.md T2.2.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.indicators import (
    atr_percent,
    max_previous_close,
    median,
    relative_volume,
    return_n,
    wilder_atr,
)

from .conftest import ORIGIN, D

pytestmark = pytest.mark.unit


_NO_VOLUME = D(0)
_UNIT_RANGE = D("1")


def bar(
    index: int, high: Decimal, low: Decimal, close: Decimal, volume: Decimal = _NO_VOLUME
) -> Bar:
    start = ORIGIN + timedelta(minutes=15 * index)
    return Bar(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=close,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def constant_bars(count: int, *, half_range: Decimal = _UNIT_RANGE) -> list[Bar]:
    """Every bar closes at 100 with a symmetric range: every TR is ``2*half_range``."""
    return [bar(i, D("100") + half_range, D("100") - half_range, D("100")) for i in range(count)]


def test_the_seed_alone_is_not_eligible_yet() -> None:
    """The M2 gate (`.claude/state/dialogue-M2.md`, round 4 §2): 14 true ranges
    define the seed, but the reading is only released after the 15th true range
    has been smoothed in — the seed is never served as the current ATR."""
    assert wilder_atr(constant_bars(14), period=14) is None  # not even a seed
    assert wilder_atr(constant_bars(15), period=14) is None  # seed only
    assert wilder_atr(constant_bars(16), period=14) is not None  # seed + one update


def test_wilder_atr_seed_is_the_mean_of_the_first_true_ranges() -> None:
    atr = wilder_atr(constant_bars(16), period=14)

    assert atr is not None
    assert atr.value == D("2")
    assert atr.seed == D("2")
    assert atr.bars_used == 16
    assert atr.period == 14
    assert atr.method == "wilder_v1"
    assert atr.origin == "rolling_window_v1"


def test_wilder_atr_seed_anchor_is_the_bar_where_the_seed_is_defined() -> None:
    atr = wilder_atr(constant_bars(20), period=14)

    assert atr is not None
    # bars[0] only provides the previous close; TR 1..14 seed the average, so the
    # seed is first defined on bars[14].
    assert atr.seed_anchor == ORIGIN + timedelta(minutes=15 * 14)


def test_wilder_atr_smoothing_step_is_exact() -> None:
    bars = [*constant_bars(15), bar(15, D("108"), D("92"), D("100"))]  # TR = 16

    atr = wilder_atr(bars, period=14)

    assert atr is not None
    assert atr.value == D("3")  # (2*13 + 16) / 14
    assert atr.seed == D("2")
    assert atr.bars_used == 16


def test_wilder_atr_two_smoothing_steps() -> None:
    bars = [
        *constant_bars(15),
        bar(15, D("108"), D("92"), D("100")),  # TR = 16 -> ATR 3
        bar(16, D("101.5"), D("100"), D("100")),  # TR = 1.5 -> (3*13 + 1.5)/14
    ]

    atr = wilder_atr(bars, period=14)

    assert atr is not None
    assert atr.value == D("40.5") / D("14")
    assert str(atr.value) == "2.892857142857142857142857143"


def test_wilder_atr_true_range_uses_the_previous_close_gap() -> None:
    bars = [*constant_bars(15), bar(15, D("120"), D("118"), D("119"))]  # gap up

    atr = wilder_atr(bars, period=14)

    assert atr is not None
    # TR = max(120-118, |120-100|, |118-100|) = 20 -> (2*13 + 20)/14
    assert atr.value == D("46") / D("14")


def test_wilder_atr_rejects_a_non_positive_period() -> None:
    with pytest.raises(ValueError, match="period"):
        wilder_atr(constant_bars(15), period=0)


def test_atr_percent_divides_by_the_last_close() -> None:
    atr = wilder_atr(constant_bars(16), period=14)
    assert atr is not None
    assert atr_percent(atr, D("100")) == D("0.02")


def test_atr_percent_of_a_zero_close_is_none() -> None:
    atr = wilder_atr(constant_bars(16), period=14)
    assert atr is not None
    assert atr_percent(atr, D(0)) is None


def test_the_rolling_window_is_the_declared_origin() -> None:
    """A pure function has no checkpoint: the ATR is recomputed from exactly the
    bars it is given, and the window start is recorded so the reading can be
    reproduced. Two calls with the same window agree; a longer window is a
    *different*, declared reading — never claimed to equal a continuous Wilder
    state carried since an older origin."""
    bars = constant_bars(40)

    short = wilder_atr(bars[-20:], period=14)
    long_ = wilder_atr(bars, period=14)

    assert short is not None and long_ is not None
    assert short.window_start == bars[-20].open_time
    assert long_.window_start == bars[0].open_time
    assert wilder_atr(bars[-20:], period=14) == short


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["1", "3", "2"], "2"),
        (["1", "2", "3", "4"], "2.5"),
        (["5"], "5"),
        (["1", "1", "1", "100"], "1"),
    ],
)
def test_median_is_exact(values: list[str], expected: str) -> None:
    assert median([D(v) for v in values]) == D(expected)


def test_median_of_nothing_is_none() -> None:
    assert median([]) is None


def test_relative_volume_excludes_the_current_bar() -> None:
    bars = [bar(i, D("101"), D("99"), D("100"), volume=D("10")) for i in range(5)]
    bars.append(bar(5, D("101"), D("99"), D("100"), volume=D("40")))

    assert relative_volume(bars, window=5) == D("4")


def test_relative_volume_needs_a_full_window() -> None:
    bars = [bar(i, D("101"), D("99"), D("100"), volume=D("10")) for i in range(3)]
    assert relative_volume(bars, window=5) is None


def test_relative_volume_is_none_when_the_baseline_median_is_zero() -> None:
    bars = [bar(i, D("101"), D("99"), D("100"), volume=D(0)) for i in range(5)]
    bars.append(bar(5, D("101"), D("99"), D("100"), volume=D("40")))

    assert relative_volume(bars, window=5) is None


def test_max_previous_close_excludes_the_current_bar() -> None:
    bars = [bar(i, D("200"), D("1"), D("100") + D(i)) for i in range(5)]  # closes 100..104
    assert max_previous_close(bars, count=4) == D("103")
    assert max_previous_close(bars, count=2) == D("103")


def test_max_previous_close_needs_the_whole_lookback() -> None:
    bars = [bar(i, D("200"), D("1"), D("100") + D(i)) for i in range(3)]
    assert max_previous_close(bars, count=5) is None


def test_return_n_is_a_fraction() -> None:
    bars = [bar(0, D("200"), D("1"), D("100")), bar(1, D("200"), D("1"), D("101"))]
    assert return_n(bars, n=1) == D("0.01")


def test_return_n_needs_the_reference_bar() -> None:
    assert return_n([bar(0, D("200"), D("1"), D("100"))], n=1) is None


def test_return_n_of_a_zero_reference_is_none() -> None:
    bars = [bar(0, D("200"), D(0), D(0)), bar(1, D("200"), D("1"), D("101"))]
    assert return_n(bars, n=1) is None
