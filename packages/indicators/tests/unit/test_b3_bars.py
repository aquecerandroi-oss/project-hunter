"""Intraday bars and plans for the WIN family H-039/H-040/H-041 — synthetic fixtures (tests only).

Every instant is UTC; 10:00 BRT = 13:00Z (BRT is a fixed UTC−3 since 2019).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.b3.bars import Bar, aggregate, closed_prefix, session_bars
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import IntradayWindow, TradePlan

pytestmark = pytest.mark.unit

OPEN = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)  # Monday 04/03/2024 10:00 BRT


def bar(minute: int, o: int, h: int, low: int, c: int) -> Bar:
    return Bar(
        start=OPEN + timedelta(minutes=minute),
        minutes=1,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
    )


def test_bar_end_is_start_plus_duration() -> None:
    assert bar(0, 100, 105, 95, 100).end == OPEN + timedelta(minutes=1)


def test_bar_refuses_naive_time_and_inconsistent_prices() -> None:
    with pytest.raises(ValueError, match="aware"):
        Bar(datetime(2024, 3, 4, 13), 1, Decimal(1), Decimal(1), Decimal(1), Decimal(1))  # noqa: DTZ001
    with pytest.raises(ValueError, match="OHLC"):
        bar(0, 100, 99, 95, 100)  # high below open
    with pytest.raises(ValueError, match="OHLC"):
        bar(0, 100, 105, 101, 100)  # low above close


def test_closed_prefix_keeps_only_bars_ended_by_t() -> None:
    bars = [bar(i, 100, 101, 99, 100) for i in range(5)]
    assert closed_prefix(bars, OPEN + timedelta(minutes=3)) == bars[:3]
    assert closed_prefix(bars, OPEN + timedelta(minutes=2, seconds=59)) == bars[:2]
    assert closed_prefix(bars, OPEN) == []


def test_aggregate_builds_buckets_from_the_anchor_and_marks_empty_ones() -> None:
    bars = [
        bar(0, 100, 110, 95, 105),
        bar(1, 105, 120, 104, 118),
        bar(2, 118, 119, 90, 92),
        # minutes 3..5 missing: bucket [3, 6) is empty
        bar(6, 92, 93, 91, 93),
    ]
    out = aggregate(bars, anchor=OPEN, minutes=3, until=OPEN + timedelta(minutes=9))
    assert len(out) == 3
    first = out[0]
    assert first is not None
    assert (first.open, first.high, first.low, first.close) == (
        Decimal(100),
        Decimal(120),
        Decimal(90),
        Decimal(92),
    )
    assert first.start == OPEN and first.minutes == 3
    assert out[1] is None
    assert out[2] is not None and out[2].close == Decimal(93)


def test_aggregate_never_emits_a_bucket_that_ends_after_until() -> None:
    bars = [bar(i, 100, 101, 99, 100) for i in range(10)]
    out = aggregate(bars, anchor=OPEN, minutes=3, until=OPEN + timedelta(minutes=8))
    assert len(out) == 2  # [0,3) and [3,6); [6,9) is not closed at 8


def test_session_bars_filters_by_window() -> None:
    bars = [bar(i, 100, 101, 99, 100) for i in range(-5, 5)]
    win = IntradayWindow(date(2024, 3, 4), open_at=OPEN, exit_at=OPEN + timedelta(minutes=3))
    assert [b.start for b in session_bars(bars, win)] == [
        OPEN + timedelta(minutes=i) for i in range(3)
    ]


def test_window_and_plan_validate_their_fields() -> None:
    with pytest.raises(ValueError, match="open_at < exit_at"):
        IntradayWindow(date(2024, 3, 4), open_at=OPEN, exit_at=OPEN)
    with pytest.raises(ValueError, match="exactly one"):
        TradePlan(
            strategy="x/1",
            trading_date=date(2024, 3, 4),
            side=Side.BUY,
            decided_at=OPEN,
            exit_at=OPEN + timedelta(minutes=5),
            stop_level=Decimal(95),
            stop_fraction=Decimal("0.005"),
            target_r=None,
            reason="r",
        )
    with pytest.raises(ValueError, match="decided_at < exit_at"):
        TradePlan(
            strategy="x/1",
            trading_date=date(2024, 3, 4),
            side=Side.BUY,
            decided_at=OPEN,
            exit_at=OPEN,
            stop_level=Decimal(95),
            stop_fraction=None,
            target_r=None,
            reason="r",
        )


def test_plan_identity_is_a_stable_string_for_the_freeze() -> None:
    plan = TradePlan(
        strategy="orb_win/1",
        trading_date=date(2024, 3, 4),
        side=Side.SELL,
        decided_at=OPEN + timedelta(minutes=31),
        exit_at=OPEN + timedelta(minutes=390),
        stop_level=Decimal("127450"),
        stop_fraction=None,
        target_r=None,
        reason="close below the opening range",
    )
    assert plan.identity() == (
        "orb_win/1|2024-03-04|sell|2024-03-04T13:31:00+00:00|2024-03-04T19:30:00+00:00"
        "|stop=127450|frac=-|target_r=-"
    )
