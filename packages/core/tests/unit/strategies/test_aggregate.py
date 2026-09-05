"""1m -> 5m/15m aggregation — SHADOW-LAB.md "Decisão conjunta" §7.

Only contiguous, final, whole UTC buckets aggregate; a trailing partial bucket
never exists (the cut *is* the bar close); an internal gap makes the window
unavailable with a reason instead of silently shrinking it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import aggregate

from .conftest import ORIGIN, BarSpec, D, explode, flat, minute, series

pytestmark = pytest.mark.unit


def test_two_15m_bars_aggregate_open_high_low_close_volume() -> None:
    specs = [
        BarSpec(D("100"), D("105"), D("95"), D("101"), D("30")),
        BarSpec(D("101"), D("110"), D("100"), D("108"), D("70")),
    ]
    window = aggregate(
        series(specs, timeframe=Timeframe.M15),
        Timeframe.M15,
        ORIGIN + timedelta(minutes=30),
        bars_needed=2,
    )

    assert window.available
    assert [bar.open_time for bar in window.bars] == [ORIGIN, ORIGIN + timedelta(minutes=15)]
    assert [bar.close_time for bar in window.bars] == [
        ORIGIN + timedelta(minutes=15),
        ORIGIN + timedelta(minutes=30),
    ]
    first, second = window.bars
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        D("100"),
        D("105"),
        D("95"),
        D("101"),
        D("30"),
    )
    assert (second.open, second.high, second.low, second.close, second.volume) == (
        D("101"),
        D("110"),
        D("100"),
        D("108"),
        D("70"),
    )


def test_only_the_last_bars_needed_bars_are_returned() -> None:
    specs = [flat(D(100) + D(i), D("1"), D("10")) for i in range(6)]
    window = aggregate(
        series(specs, timeframe=Timeframe.M5),
        Timeframe.M5,
        ORIGIN + timedelta(minutes=30),
        bars_needed=2,
    )

    assert window.available
    assert [bar.close for bar in window.bars] == [D("104"), D("105")]


def test_a_missing_minute_inside_the_window_makes_it_unavailable() -> None:
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(3)]
    candles = series(specs, timeframe=Timeframe.M5)
    del candles[7]  # 00:07, inside the second bar

    window = aggregate(candles, Timeframe.M5, ORIGIN + timedelta(minutes=15), bars_needed=3)

    assert not window.available
    assert window.reason == "gap"
    assert window.detail["missing_minute"] == "2026-01-01T00:07:00Z"
    assert window.bars == ()


def test_the_last_minute_of_the_reference_bar_missing_is_a_gap_not_a_short_bar() -> None:
    """The most dangerous gap: the reference bar itself would be built from 14 of
    its 15 minutes and still be called "the 15m bar"."""
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(2)]
    candles = series(specs, timeframe=Timeframe.M15)
    del candles[-1]  # 00:29, the last minute before the cut

    window = aggregate(candles, Timeframe.M15, ORIGIN + timedelta(minutes=30), bars_needed=2)

    assert not window.available
    assert window.reason == "gap"
    assert window.detail["missing_minute"] == "2026-01-01T00:29:00Z"


def test_a_gap_outside_the_needed_window_is_irrelevant() -> None:
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(3)]
    candles = series(specs, timeframe=Timeframe.M5)
    del candles[2]  # 00:02, inside the *first* bar only

    window = aggregate(candles, Timeframe.M5, ORIGIN + timedelta(minutes=15), bars_needed=2)

    assert window.available
    assert len(window.bars) == 2


def test_not_enough_history_is_warmup_not_a_shrunken_window() -> None:
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(2)]
    window = aggregate(
        series(specs, timeframe=Timeframe.M15),
        Timeframe.M15,
        ORIGIN + timedelta(minutes=30),
        bars_needed=3,
    )

    assert not window.available
    assert window.reason == "warmup"
    assert window.detail == {
        "window_start": "2025-12-31T23:45:00Z",
        "first_candle": "2026-01-01T00:00:00Z",
    }
    assert window.bars == ()


def test_a_hole_at_the_start_of_the_window_is_a_gap_not_warmup() -> None:
    """History reaches back far enough, but the window's first minute is missing:
    that is a hole the worker may backfill, not a market that just started."""
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(3)]
    candles = series(specs, timeframe=Timeframe.M15)
    del candles[15]  # 00:15, the first minute of the 2-bar window below

    window = aggregate(candles, Timeframe.M15, ORIGIN + timedelta(minutes=45), bars_needed=2)

    assert window.reason == "gap"
    assert window.detail["missing_minute"] == "2026-01-01T00:15:00Z"


def test_a_close_that_is_not_a_bucket_boundary_is_misaligned() -> None:
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(2)]
    window = aggregate(
        series(specs, timeframe=Timeframe.M15),
        Timeframe.M15,
        ORIGIN + timedelta(minutes=20),
        bars_needed=1,
    )

    assert window.reason == "misaligned"


def test_candles_after_the_cut_are_never_aggregated() -> None:
    """A partial trailing bucket cannot exist: the cut is the bar close itself."""
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(2)]
    candles = series(specs, timeframe=Timeframe.M15)
    candles.extend(
        explode(
            BarSpec(D("100"), D("999"), D("1"), D("500"), D("999")),
            ORIGIN + timedelta(minutes=30),
            15,
        )
    )

    window = aggregate(candles, Timeframe.M15, ORIGIN + timedelta(minutes=30), bars_needed=2)

    assert window.available
    assert window.bars[-1].close == D("100")
    assert window.bars[-1].close_time == ORIGIN + timedelta(minutes=30)


def test_a_non_final_candle_is_a_contract_violation() -> None:
    candles = series([flat(D("100"), D("1"), D("10"))], timeframe=Timeframe.M15)
    candles[3] = minute(
        candles[3].open_time, D("100"), D("100"), D("100"), D("100"), D(0), is_final=False
    )

    with pytest.raises(ValueError, match="is_final"):
        aggregate(candles, Timeframe.M15, ORIGIN + timedelta(minutes=15), bars_needed=1)


def test_a_non_1m_input_candle_is_a_contract_violation() -> None:
    bar = series([flat(D("100"), D("1"), D("10"))], timeframe=Timeframe.M15)[0]
    fifteen = bar.model_copy(
        update={"timeframe": Timeframe.M15, "close_time": bar.open_time + timedelta(minutes=15)}
    )

    with pytest.raises(ValueError, match="1m"):
        aggregate([fifteen], Timeframe.M15, ORIGIN + timedelta(minutes=15), bars_needed=1)


def test_bars_needed_must_be_positive() -> None:
    with pytest.raises(ValueError, match="bars_needed"):
        aggregate([], Timeframe.M15, ORIGIN, bars_needed=0)


def test_an_empty_series_is_warmup() -> None:
    window = aggregate([], Timeframe.M15, ORIGIN + timedelta(minutes=15), bars_needed=1)
    assert window.reason == "warmup"
    assert window.detail["first_candle"] == "none"


def test_the_window_end_may_be_earlier_than_the_last_candle() -> None:
    """A 5m strategy asks for 15m ATR bars ending at the last completed 15m close."""
    specs = [flat(D("100"), D("1"), D("10")) for _ in range(6)]  # 30 minutes of 5m bars
    candles = series(specs, timeframe=Timeframe.M5)

    window = aggregate(
        candles, Timeframe.M15, datetime(2026, 1, 1, 0, 15, tzinfo=UTC), bars_needed=1
    )

    assert window.available
    assert window.bars[-1].close_time == datetime(2026, 1, 1, 0, 15, tzinfo=UTC)
