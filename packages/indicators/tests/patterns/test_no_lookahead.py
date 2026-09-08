"""No look-ahead: what we say about bar *i* cannot depend on bar *i + 1*.

Three claims, tested separately:

1. over random walks, ``scan(bars, as_of=i)`` is byte-for-byte
   ``scan(bars[: i + 1])`` — appending bars never rewrites the past;
2. the bar still forming (or any absurd future bar) does not move a single
   pivot, line or event of the cut before it;
3. the test has teeth: a *deliberate cheat* — the same pipeline with pivots
   declared known on the bar they happen on — reports a line one bar could not
   have drawn, and fails the very comparison of claim 1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.patterns.pivots import find_pivots
from hunter_indicators.patterns.scale import atr_series
from hunter_indicators.patterns.scan import PatternScan, scan
from hunter_indicators.patterns.trendlines import LineKind, find_lines
from packages.indicators.tests.patterns.builders import ORIGIN, STEP, bars, walk

pytestmark = pytest.mark.unit

TF = Timeframe.M15
K = 3


def _visible(result: PatternScan) -> tuple[object, ...]:
    return (result.pivots, result.lines, result.channels, result.events)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    steps=st.lists(st.integers(min_value=-40, max_value=40), min_size=70, max_size=110),
    fraction=st.integers(min_value=40, max_value=95),
)
def test_appending_bars_never_changes_what_an_earlier_cut_reported(
    steps: list[int], fraction: int
) -> None:
    series = walk(steps)
    cut = (len(series) - 1) * fraction // 100

    full = scan(series, timeframe=TF, as_of=cut)
    prefix = scan(series[: cut + 1], timeframe=TF)

    assert _visible(full) == _visible(prefix)


def test_a_wild_bar_after_the_cut_moves_nothing() -> None:
    series = bars(52)
    absurd = Bar(
        open_time=ORIGIN + 52 * STEP,
        close_time=ORIGIN + 53 * STEP,
        open=Decimal("126"),
        high=Decimal("400"),
        low=Decimal("1"),
        close=Decimal("399"),
        volume=Decimal("100000"),
    )

    before = scan(series, timeframe=TF)
    after = scan((*series, absurd), timeframe=TF, as_of=51)

    assert _visible(before) == _visible(after)


def _cheating_lines(series: Sequence[Bar], cut: int):
    """The cheat: a swing is "known" on the bar it happened on (``confirmed_at = index``).

    The most common look-ahead bug in technical-analysis code, written on
    purpose: the pivot at bar 45 needs bars 46-48 to be a pivot at all, and the
    cheat anchors a line on it as if bar 45 already knew.
    """
    atr = atr_series(series, period=14, timeframe=TF)
    pivots = [
        replace(pivot, confirmed_at=pivot.index)
        for pivot in find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"))
    ]
    return find_lines(series[: cut + 1], atr[: cut + 1], pivots, as_of=cut)


def test_the_cheat_is_caught_by_the_same_comparison() -> None:
    series = bars(52)
    cut = 45

    honest = scan(series, timeframe=TF, as_of=cut).lines
    cheating = _cheating_lines(series, cut)

    assert [line.touches for line in honest if line.kind is LineKind.SUPPORT] == [3]
    assert [line.touches for line in cheating if line.kind is LineKind.SUPPORT] == [4], (
        "the fourth low is at bar 45 and is only confirmed at 48"
    )
    # …and the same prefix comparison the honest scan passes fails for the cheat:
    # with only 46 bars the pivot at 45 cannot be found at all.
    assert _cheating_lines(series[: cut + 1], cut) != cheating


def test_bars_must_be_contiguous_instead_of_silently_bridging_a_gap() -> None:
    series = bars(30)
    with_hole = (*series[:20], *series[21:])
    assert with_hole[20].open_time - with_hole[19].open_time == timedelta(minutes=30)

    with pytest.raises(ValueError, match="contiguous"):
        scan(with_hole, timeframe=TF)


def test_the_cut_is_a_bar_index_not_a_clock() -> None:
    series = bars(30)
    assert series[10].close_time == datetime(2026, 9, 1, 2, 45, tzinfo=UTC)

    with pytest.raises(ValueError, match="outside the series"):
        scan(series, timeframe=TF, as_of=30)
