"""H-039 opening-range breakout on the WIN (``hunter_indicators.b3.orb``) — synthetic fixtures.

Session Monday 04/03/2024: OPEN = 10:00 BRT = 13:00Z, time exit 16:30 BRT = 19:30Z, last
decision 14:00 BRT = 17:00Z. Prices are multiples of the 5-point tick.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import IntradayWindow, NoPlan, TradePlan
from hunter_indicators.b3.orb import (
    OPENING_RANGE_DEFINITION,
    ORB_V1,
    opening_range,
    scan_orb,
)

pytestmark = pytest.mark.unit

OPEN = datetime(2024, 3, 4, 13, 0, tzinfo=UTC)
WINDOW = IntradayWindow(date(2024, 3, 4), open_at=OPEN, exit_at=OPEN + timedelta(minutes=390))


def flat(minute: int, price: int = 120000, spread: int = 20) -> Bar:
    return Bar(
        start=OPEN + timedelta(minutes=minute),
        minutes=1,
        open=Decimal(price),
        high=Decimal(price + spread),
        low=Decimal(price - spread),
        close=Decimal(price),
    )


def with_close(minute: int, close: int) -> Bar:
    lo, hi = min(120000, close) - 5, max(120000, close) + 5
    return Bar(
        OPEN + timedelta(minutes=minute),
        1,
        Decimal(120000),
        Decimal(hi),
        Decimal(lo),
        Decimal(close),
    )


def session(overrides: dict[int, Bar] | None = None, missing: set[int] | None = None) -> list[Bar]:
    """390 one-minute bars; the opening range is [119900, 120100] (bars 3 and 7 set it)."""
    bars: dict[int, Bar] = {m: flat(m) for m in range(390)}
    bars[3] = Bar(
        OPEN + timedelta(minutes=3),
        1,
        Decimal(120000),
        Decimal(120100),
        Decimal(119990),
        Decimal(120050),
    )
    bars[7] = Bar(
        OPEN + timedelta(minutes=7),
        1,
        Decimal(120000),
        Decimal(120010),
        Decimal(119900),
        Decimal(119950),
    )
    bars.update(overrides or {})
    return [bars[m] for m in sorted(bars) if m not in (missing or set())]


def test_frozen_parameters_and_feature_definition() -> None:
    assert ORB_V1.version == "orb_win/1"
    assert ORB_V1.range_minutes == 30
    assert ORB_V1.min_range_bars == 25
    assert OPENING_RANGE_DEFINITION.key == "win_opening_range"
    assert OPENING_RANGE_DEFINITION.version == 1
    assert OPENING_RANGE_DEFINITION.params["range_minutes"] == 30


def test_opening_range_reads_only_the_first_thirty_minutes() -> None:
    assert opening_range(session(), WINDOW, ORB_V1) == (Decimal(120100), Decimal(119900))
    # a huge bar at 10:30 (minute 30) is outside the range
    bars = session({30: flat(30, 121000, 500)})
    assert opening_range(bars, WINDOW, ORB_V1) == (Decimal(120100), Decimal(119900))


def test_upside_close_buys_with_stop_at_the_range_low() -> None:
    plan = scan_orb(session({31: with_close(31, 120105)}), WINDOW, ORB_V1)
    assert isinstance(plan, TradePlan)
    assert plan.side is Side.BUY
    assert plan.decided_at == OPEN + timedelta(minutes=32)  # end of the 10:31 bar
    assert plan.stop_level == Decimal(119900)
    assert plan.stop_fraction is None and plan.target_r is None
    assert plan.exit_at == WINDOW.exit_at
    assert plan.supporting_features["range_high"] == "120100"


def test_downside_close_sells_with_stop_at_the_range_high() -> None:
    plan = scan_orb(session({40: with_close(40, 119895)}), WINDOW, ORB_V1)
    assert isinstance(plan, TradePlan)
    assert plan.side is Side.SELL
    assert plan.stop_level == Decimal(120100)


def test_a_touch_without_a_close_beyond_is_not_a_breakout() -> None:
    touch = Bar(
        OPEN + timedelta(minutes=31),
        1,
        Decimal(120000),
        Decimal(120200),
        Decimal(119995),
        Decimal(120100),
    )
    assert scan_orb(session({31: touch}), WINDOW, ORB_V1) == NoPlan(
        WINDOW.trading_date, "no_breakout"
    )


def test_only_the_first_breakout_counts() -> None:
    plan = scan_orb(
        session({50: with_close(50, 119800), 60: with_close(60, 120400)}), WINDOW, ORB_V1
    )
    assert isinstance(plan, TradePlan) and plan.side is Side.SELL


def test_last_decision_bar_ends_at_14h() -> None:
    at_limit = scan_orb(session({239: with_close(239, 120200)}), WINDOW, ORB_V1)  # ends 17:00Z
    assert isinstance(at_limit, TradePlan) and at_limit.decided_at == OPEN + timedelta(minutes=240)
    late = scan_orb(session({240: with_close(240, 120200)}), WINDOW, ORB_V1)  # ends 17:01Z
    assert late == NoPlan(WINDOW.trading_date, "no_breakout")


def test_too_few_range_bars_or_a_degenerate_range_is_no_trade() -> None:
    sparse = session(missing={0, 1, 2, 4, 5, 6})  # 24 of 30 range bars
    assert scan_orb(sparse, WINDOW, ORB_V1) == NoPlan(WINDOW.trading_date, "range_insufficient")
    dead = [flat(m, spread=0) for m in range(390)]
    assert scan_orb(dead, WINDOW, ORB_V1) == NoPlan(WINDOW.trading_date, "range_degenerate")


def test_neighbour_range_lengths_scale_the_minimum_bar_count() -> None:
    p15 = replace(ORB_V1, version="orb_win/1@range15", range_minutes=15)
    assert p15.min_range_bars == 13
    p60 = replace(ORB_V1, version="orb_win/1@range60", range_minutes=60)
    assert p60.min_range_bars == 50
    plan = scan_orb(session({16: with_close(16, 120105)}), WINDOW, p15)
    assert isinstance(plan, TradePlan) and plan.decided_at == OPEN + timedelta(minutes=17)


def test_changing_bars_after_the_decision_never_changes_it() -> None:
    base = session({31: with_close(31, 120105)})
    plan = scan_orb(base, WINDOW, ORB_V1)
    assert isinstance(plan, TradePlan)
    future = [
        b
        if b.end <= plan.decided_at
        else flat(int((b.start - OPEN).total_seconds() // 60), 110000, 900)
        for b in base
    ]
    assert scan_orb(future, WINDOW, ORB_V1) == plan


def test_bars_outside_the_window_are_ignored() -> None:
    before = [flat(m, 150000, 5000) for m in range(-60, 0)]
    plan = scan_orb(before + session({31: with_close(31, 120105)}), WINDOW, ORB_V1)
    assert isinstance(plan, TradePlan) and plan.stop_level == Decimal(119900)
