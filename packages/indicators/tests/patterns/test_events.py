"""Breakout, retest and bounce — the three things a line can do to price."""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.patterns.events import BreakDirection, EventKind, detect_events
from hunter_indicators.patterns.pivots import find_pivots
from hunter_indicators.patterns.scale import atr_series
from hunter_indicators.patterns.trendlines import LineKind, TrendLine, find_lines
from packages.indicators.tests.patterns.builders import (
    ORIGIN,
    STEP,
    bars,
    replace_bar,
    resistance_price,
)

pytestmark = pytest.mark.unit

K = 3
ATR_PERIOD = 14
BREAK_BAR = 47


def _atr(series: tuple[Bar, ...]) -> tuple[Decimal | None, ...]:
    return atr_series(series, period=ATR_PERIOD, timeframe=Timeframe.M15)


def _lines(series: tuple[Bar, ...]) -> tuple[TrendLine, ...]:
    atr = _atr(series)
    pivots = find_pivots(series, atr, k=K, min_swing_atr=Decimal("1.0"))
    return find_lines(series, atr, pivots)


def _with_breakout(index: int = BREAK_BAR) -> tuple[Bar, ...]:
    """Bar ``index`` closes 3.0 above the resistance line (~1.2 ATR)."""
    series = bars(52)
    close = resistance_price(index) + Decimal("3")
    return replace_bar(series, index, close=close, high=close + Decimal("0.5"))


def test_the_resistance_line_survives_the_bar_that_breaks_it() -> None:
    lines = _lines(_with_breakout())
    resistance = next(line for line in lines if line.kind is LineKind.RESISTANCE)

    assert resistance.valid_from_idx == 43, "the third peak is confirmed three bars later"
    assert resistance.violations == 1, "one close through it, after the last touch"
    assert resistance.score == Decimal(3 * 20 - 1)


def test_a_close_beyond_the_line_is_a_breakout() -> None:
    series = _with_breakout()
    atr = _atr(series)
    resistance = next(line for line in _lines(series) if line.kind is LineKind.RESISTANCE)

    events = detect_events(series, atr, [resistance])

    breakouts = [event for event in events if event.kind is EventKind.BREAKOUT]
    assert len(breakouts) == 1
    event = breakouts[0]
    assert event.index == BREAK_BAR
    assert event.origin_idx == BREAK_BAR
    assert event.direction is BreakDirection.UP
    assert event.line_id == resistance.line_id
    assert event.line_price == resistance.projected(BREAK_BAR)
    scale = atr[BREAK_BAR]
    assert scale is not None
    assert event.distance_atr == Decimal("3") / scale


def test_a_breakout_without_relative_volume_is_not_reported() -> None:
    series = _with_breakout()
    atr = _atr(series)
    lines = [line for line in _lines(series) if line.kind is LineKind.RESISTANCE]
    quiet = [Decimal("1.0")] * len(series)
    loud = [*quiet]
    loud[BREAK_BAR] = Decimal("2.0")

    without = detect_events(series, atr, lines, rvol=quiet, rvol_min=Decimal("1.5"))
    with_volume = detect_events(series, atr, lines, rvol=loud, rvol_min=Decimal("1.5"))

    assert [event for event in without if event.kind is EventKind.BREAKOUT] == []
    assert [event.index for event in with_volume if event.kind is EventKind.BREAKOUT] == [BREAK_BAR]


def _with_retest(retest_bar: int) -> tuple[Bar, ...]:
    """After the breakout, ``retest_bar`` dips onto the line and closes above it."""
    series = _with_breakout()
    level = resistance_price(retest_bar)
    return replace_bar(
        series,
        retest_bar,
        low=level,
        close=level + Decimal("2"),
        high=level + Decimal("2.5"),
    )


def test_a_dip_back_to_the_broken_line_is_a_retest() -> None:
    series = _with_retest(BREAK_BAR + 1)
    atr = _atr(series)
    lines = [line for line in _lines(series) if line.kind is LineKind.RESISTANCE]

    events = detect_events(series, atr, lines, retest_bars=3)

    retests = [event for event in events if event.kind is EventKind.RETEST]
    assert [(event.origin_idx, event.index) for event in retests] == [
        (BREAK_BAR + 1, BREAK_BAR + 1)
    ]


def test_a_dip_after_the_retest_window_is_not_a_retest() -> None:
    series = _with_retest(BREAK_BAR + 4)
    atr = _atr(series)
    lines = [line for line in _lines(series) if line.kind is LineKind.RESISTANCE]

    events = detect_events(series, atr, lines, retest_bars=3)

    assert [event for event in events if event.kind is EventKind.RETEST] == []


def test_touching_the_support_line_and_closing_away_is_a_bounce() -> None:
    series = bars(62)
    atr = _atr(series)
    support = [line for line in _lines(series) if line.kind is LineKind.SUPPORT]
    assert support and support[0].valid_from_idx == 38

    events = detect_events(series, atr, support, bounce_bars=3)

    bounces = [event for event in events if event.kind is EventKind.BOUNCE]
    assert [(event.origin_idx, event.index) for event in bounces] == [(45, 46), (55, 56)]
    assert all(event.direction is BreakDirection.UP for event in bounces)


def test_no_event_is_reported_before_the_line_is_valid() -> None:
    series = bars(62)
    atr = _atr(series)
    support = _lines(series)[0]

    events = detect_events(series, atr, [support], bounce_bars=3)

    assert events and all(event.index >= support.valid_from_idx for event in events)


def _flat_line() -> TrendLine:
    """A hand-made horizontal support at 100, valid from bar 3."""
    return TrendLine(
        line_id="flat",
        kind=LineKind.SUPPORT,
        origin=(0, Decimal("100")),
        through=(1, Decimal("100")),
        anchors=((0, Decimal("100")), (1, Decimal("100")), (2, Decimal("100"))),
        slope_per_bar=Decimal("0"),
        touches=3,
        first_idx=0,
        last_idx=2,
        valid_from_idx=3,
        violations=0,
        score=Decimal("6"),
    )


def _flat_bar(index: int, low: Decimal, high: Decimal, close: Decimal) -> Bar:
    return Bar(
        open_time=ORIGIN + index * STEP,
        close_time=ORIGIN + (index + 1) * STEP,
        open=close,
        high=high,
        low=low,
        close=close,
        volume=Decimal("10"),
    )


def test_a_pending_bounce_never_swallows_the_breakout_that_happened_first() -> None:
    """Astra, T3.34 review, must-fix 3, with her scenario, ATR = 1 everywhere.

    Bar 3 touches the line and closes just above it; bar 4 closes 1 ATR through
    it; bar 5 recovers. The bounce confirmation used to be found at bar 5 and
    the cursor jumped over bar 4, deleting the breakout from the history.
    """
    D = Decimal
    series = (
        _flat_bar(0, D("102"), D("104"), D("103")),
        _flat_bar(1, D("102"), D("104"), D("103")),
        _flat_bar(2, D("102"), D("104"), D("103")),
        _flat_bar(3, D("100"), D("101"), D("100.10")),
        _flat_bar(4, D("98.5"), D("100.50"), D("99")),
        _flat_bar(5, D("99.5"), D("101.5"), D("101")),
    )
    atr = (D("1"),) * 6

    events = detect_events(series, atr, [_flat_line()], bounce_bars=3)

    assert [(event.kind, event.index) for event in events] == [(EventKind.BREAKOUT, 4)]
