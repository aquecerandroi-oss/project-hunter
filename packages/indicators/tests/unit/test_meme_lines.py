"""T4.10 — the lines as features, over synthetic series with hand-computed answers.

The series below is drawn so the arithmetic can be checked on paper: two local
lows at 36 (m = −12) and 41 (m = −7) give a support line of slope 1 SOL/min,
worth 48 at the minute's close; the close at 56 sits 16,6667 % above it. The
previous window's high is 53, so 56 is a breakout — and the current minute's
own photos are never that reference, which is the second thing proved here.
The third is non-anticipation: a photo inside the window that reached us one
second after the close changes nothing.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.lines import (
    FLAT,
    LINE_DEFINITIONS,
    LINE_REASONS,
    NO_SNAPSHOT,
    OUT_OF_RANGE,
    TOO_FEW_POINTS,
    LineFeatures,
    LinePoint,
    compute_lines,
    local_lows,
    log_slope,
)

pytestmark = pytest.mark.unit

END = datetime(2026, 9, 12, 12, 15, tzinfo=UTC)

TWO_LOWS: dict[int, str] = {
    -15: "41",  # previous window only
    -14: "40",
    -13: "38",
    -12: "36",  # low 1
    -11: "39",
    -10: "42",
    -9: "45",
    -8: "43",
    -7: "41",  # low 2 — higher than low 1
    -6: "44",
    -5: "47",
    -4: "49",
    -3: "50",
    -2: "52",
    -1: "53",  # the previous window's high
    0: "56",  # now
}


def _point(minute: int, mcap: str | None, *, seconds: int = 0, late_s: int = 0) -> LinePoint:
    observed = END + timedelta(minutes=minute, seconds=seconds)
    return LinePoint(
        observed_at=observed,
        received_at=max(observed, END + timedelta(seconds=late_s)) if late_s else observed,
        mcap_sol=None if mcap is None else Decimal(mcap),
    )


def _series(values: dict[int, str]) -> list[LinePoint]:
    return [_point(m, v) for m, v in values.items()]


def _now(values: dict[int, str]) -> Decimal:
    return Decimal(values[0])


# ---- the line ---------------------------------------------------------------------------


def test_the_support_line_runs_through_the_last_two_local_lows() -> None:
    lines = compute_lines(_series(TWO_LOWS), end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.line_reason is None
    assert lines.line_points == 15
    assert lines.support_line_slope == Decimal("1.000000")  # (41 − 36) / 5 min
    assert lines.support_line_sol == Decimal("48.0000000000")  # 41 + 1 × 7 min
    assert lines.higher_lows is True
    assert lines.distance_to_support_pct == Decimal("0.166667")  # (56 − 48) / 48
    assert lines.high_15m_sol == Decimal("56.0000000000")
    assert lines.low_15m_sol == Decimal("36.0000000000")


def test_local_lows_are_strictly_below_both_neighbours_and_never_the_ends() -> None:
    lows = local_lows(_series({m: v for m, v in TWO_LOWS.items() if m >= -14}))
    assert [(p.observed_at, p.mcap_sol) for p in lows] == [
        (END - timedelta(minutes=12), Decimal(36)),
        (END - timedelta(minutes=7), Decimal(41)),
    ]
    plateau = _series({-4: "50", -3: "40", -2: "40", -1: "50", 0: "60"})
    assert local_lows(plateau) == [], "a flat bottom has no strict low"


def test_lower_lows_are_reported_as_such() -> None:
    values = {**TWO_LOWS, -7: "30"}  # second low (30) now below the first (36)
    lines = compute_lines(_series(values), end_time=END, mcap_now=_now(values))
    assert lines.higher_lows is False
    assert lines.support_line_slope == Decimal("-1.200000")  # (30 − 36) / 5
    assert lines.support_line_sol == Decimal("21.6000000000")  # 30 − 1,2 × 7


# ---- the breakout uses the previous window -------------------------------------------------


def test_breakout_compares_now_with_the_previous_windows_high() -> None:
    lines = compute_lines(_series(TWO_LOWS), end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.breakout_15m is True  # 56 >= 53
    lower = {**TWO_LOWS, 0: "52"}
    assert compute_lines(_series(lower), end_time=END, mcap_now=Decimal(52)).breakout_15m is False
    equal = {**TWO_LOWS, 0: "53"}
    assert compute_lines(_series(equal), end_time=END, mcap_now=Decimal(53)).breakout_15m is True


def test_the_current_minute_is_never_its_own_breakout_reference() -> None:
    """A photo taken 30 s before the close, inside the minute being folded, raises
    the window's high to 70 — and the reference stays the previous window's 53."""
    points = [*_series(TWO_LOWS), _point(0, "70", seconds=-30)]
    lines = compute_lines(points, end_time=END, mcap_now=Decimal(56))
    assert lines.high_15m_sol == Decimal("70.0000000000")
    assert lines.breakout_15m is True, "56 >= 53; had the minute counted, 56 < 70 would say no"


def test_a_photo_older_than_the_previous_window_is_not_the_reference() -> None:
    points = [*_series(TWO_LOWS), _point(-16, "90")]  # m = −16 is outside both windows
    lines = compute_lines(points, end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.breakout_15m is True and lines.line_points == 15


def test_breakout_is_unknown_when_the_previous_window_has_no_photo() -> None:
    """Five photos, all inside the minute being folded: enough points for the
    window, nothing at or before ``end_time − 1 min`` to break out of."""
    only_now = [_point(0, "56", seconds=-s) for s in (0, 10, 20, 30, 40)]
    lines = compute_lines(only_now, end_time=END, mcap_now=Decimal(56))
    assert lines.breakout_15m is None and lines.line_points == 5
    assert lines.line_reason == FLAT, "five equal photos have no low at all"


# ---- non-anticipation -----------------------------------------------------------------------


def test_a_photo_received_after_the_close_changes_nothing() -> None:
    """A deeper low at m = −3, stamped inside the window but received one second
    after ``end_time``, is not an input of this minute: the line, the extremes,
    the count and the breakout are the ones computed without it."""
    baseline = compute_lines(_series(TWO_LOWS), end_time=END, mcap_now=_now(TWO_LOWS))
    late = [*_series(TWO_LOWS), _point(-3, "20", seconds=30, late_s=1)]
    assert compute_lines(late, end_time=END, mcap_now=_now(TWO_LOWS)) == baseline
    on_time = [*_series(TWO_LOWS), _point(-3, "20", seconds=30)]
    changed = compute_lines(on_time, end_time=END, mcap_now=_now(TWO_LOWS))
    assert changed != baseline and changed.line_points == 16
    assert changed.low_15m_sol == Decimal("20.0000000000")


def test_a_photo_received_exactly_at_the_close_counts() -> None:
    at_close = [*_series(TWO_LOWS), _point(-3, "20", seconds=30, late_s=0)]
    # received_at == observed_at here; make it exactly END instead:
    at_close[-1] = LinePoint(at_close[-1].observed_at, END, at_close[-1].mcap_sol)
    lines = compute_lines(at_close, end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.line_points == 16


def test_two_photos_of_the_same_instant_keep_the_last_received() -> None:
    first = LinePoint(END - timedelta(minutes=3), END - timedelta(minutes=3), Decimal(50))
    second = LinePoint(
        END - timedelta(minutes=3), END - timedelta(minutes=2, seconds=59), Decimal(20)
    )
    points = [*_series({m: v for m, v in TWO_LOWS.items() if m != -3}), first, second]
    lines = compute_lines(points, end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.line_points == 15 and lines.low_15m_sol == Decimal("20.0000000000")


# ---- slopes on ln(mcap) ---------------------------------------------------------------------


def test_log_slopes_recover_the_growth_rate_of_an_exponential_series() -> None:
    """``mcap = 10 · e^(0,02 · m)``: the OLS slope of ``ln(mcap)`` is exactly 0,02
    per minute over both horizons — and a monotone series has no line (``flat``)."""
    points = [
        LinePoint(
            END + timedelta(minutes=m),
            END + timedelta(minutes=m),
            Decimal(repr(10 * math.exp(0.02 * m))),
        )
        for m in range(-14, 1)
    ]
    lines = compute_lines(points, end_time=END, mcap_now=points[-1].mcap_sol)
    assert lines.mcap_slope_15m == Decimal("0.020000")
    assert lines.mcap_slope_5m == Decimal("0.020000")
    assert lines.line_reason == FLAT
    assert lines.support_line_sol is None and lines.higher_lows is None
    assert lines.high_15m_sol is not None and lines.breakout_15m is True


def test_log_slope_needs_two_distinct_instants() -> None:
    one = [_point(0, "50")]
    assert log_slope(one, origin=END - timedelta(minutes=5)) is None
    two = [_point(-1, "50"), _point(0, "55")]
    assert log_slope(two, origin=END - timedelta(minutes=5)) is not None


def test_a_falling_series_has_a_negative_slope() -> None:
    lines = compute_lines(_series(TWO_LOWS), end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.mcap_slope_15m is not None and lines.mcap_slope_15m > 0
    falling = {m: str(60 + (-m) * 2) for m in range(-14, 1)}  # 88 at −14 down to 60 now
    lines = compute_lines(_series(falling), end_time=END, mcap_now=_now(falling))
    assert lines.mcap_slope_15m is not None and lines.mcap_slope_15m < 0


# ---- reasons --------------------------------------------------------------------------------


def _all_none(lines: LineFeatures) -> bool:
    return all(
        getattr(lines, name) is None
        for name in (
            "mcap_slope_5m",
            "mcap_slope_15m",
            "high_15m_sol",
            "low_15m_sol",
            "breakout_15m",
            "support_line_sol",
            "support_line_slope",
            "higher_lows",
            "distance_to_support_pct",
        )
    )


def test_fewer_than_five_photos_is_too_few_points() -> None:
    four = {m: v for m, v in TWO_LOWS.items() if m >= -3}
    lines = compute_lines(_series(four), end_time=END, mcap_now=_now(four))
    assert lines.line_reason == TOO_FEW_POINTS and lines.line_points == 4
    assert _all_none(lines)


def test_no_market_cap_for_the_minute_is_no_snapshot() -> None:
    lines = compute_lines(_series(TWO_LOWS), end_time=END, mcap_now=None)
    assert lines.line_reason == NO_SNAPSHOT and lines.line_points == 15
    assert _all_none(lines)


def test_a_photo_without_a_market_cap_is_not_a_point() -> None:
    points = [*_series({m: v for m, v in TWO_LOWS.items() if m != -3}), _point(-3, None)]
    lines = compute_lines(points, end_time=END, mcap_now=_now(TWO_LOWS))
    assert lines.line_points == 14


def test_a_support_at_or_below_zero_is_out_of_range_and_keeps_the_window_facts() -> None:
    values = {**TWO_LOWS, -12: "50", -7: "10", -6: "44"}  # lows 50 → 10: −8 SOL/min
    lines = compute_lines(_series(values), end_time=END, mcap_now=_now(values))
    assert lines.line_reason == OUT_OF_RANGE
    assert lines.support_line_sol is None and lines.distance_to_support_pct is None
    assert lines.high_15m_sol == Decimal("56.0000000000") and lines.breakout_15m is True
    assert lines.mcap_slope_15m is not None


def test_the_reason_vocabulary_is_the_briefs() -> None:
    assert LINE_REASONS == {"too_few_points", "no_snapshot", "flat", "out_of_range"}


def test_every_column_is_registered_once_with_the_window_parameters() -> None:
    keys = [definition.key for definition in LINE_DEFINITIONS]
    assert keys == [
        "mcap_slope_5m",
        "mcap_slope_15m",
        "high_15m_sol",
        "low_15m_sol",
        "breakout_15m",
        "support_line_sol",
        "support_line_slope",
        "higher_lows",
        "distance_to_support_pct",
    ]
    for definition in LINE_DEFINITIONS:
        assert definition.version == 1
        assert definition.params["window_minutes"] == 15
        assert definition.params["min_points"] == 5
        assert "meme_curve_snapshots.received_at" in definition.inputs
