"""N_hist, funnel and 80/20 cut of the WIN family — synthetic bars (tests only)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.b3.bars import Bar
from infra.research.b3.sessions import build_population, overnight_gaps, primary_size

pytestmark = pytest.mark.unit


def minute(day: date, hh: int, mm: int, price: int = 120000) -> Bar:
    start = datetime(day.year, day.month, day.day, hh + 3, mm, tzinfo=UTC)  # BRT → UTC
    return Bar(start, 1, Decimal(price), Decimal(price + 5), Decimal(price - 5), Decimal(price))


def day_bars(day: date, first: tuple[int, int] = (10, 0), price: int = 120000) -> list[Bar]:
    out: list[Bar] = []
    t = datetime(day.year, day.month, day.day, *first)  # noqa: DTZ001
    end = datetime(day.year, day.month, day.day, 16, 31)  # noqa: DTZ001
    while t < end:
        out.append(minute(day, t.hour, t.minute, price))
        t += timedelta(minutes=1)
    return out


def test_primary_is_the_floor_of_eighty_percent() -> None:
    assert primary_size(10) == 8
    assert primary_size(11) == 8
    assert primary_size(1) == 0


def test_funnel_drops_ash_wednesday_expiry_grid_and_missing_data_in_order() -> None:
    # 12–13/02/2024 Carnaval (no session). 14/02 is Ash Wednesday AND WING24's expiry
    # (counted once, as Ash Wednesday, the earlier step). 16/02: both series start at 10:30
    # → grid incompatible. 19/02: no Ibovespa at all → no data.
    days = [date(2024, 2, d) for d in (9, 14, 15, 16, 19, 20, 21)]
    win: list[Bar] = []
    ibov: list[Bar] = []
    for d in days:
        first = (10, 30) if d.day == 16 else (10, 0)
        win += day_bars(d, first)
        if d.day != 19:
            ibov += day_bars(d, first, 127000)
    pop = build_population(win, ibov)
    assert dict(pop.funnel) == {
        "calendar_sessions": 7,
        "ash_wednesday": 1,
        "win_expiry": 0,
        "grid_incompatible": 1,
        "no_data": 1,
        "n_hist": 4,
    }
    assert [s.window.trading_date for s in pop.sessions] == [
        date(2024, 2, d) for d in (9, 15, 20, 21)
    ]
    assert pop.sessions[0].window.open_at == datetime(2024, 2, 9, 13, 0, tzinfo=UTC)
    assert pop.sessions[0].window.exit_at == datetime(2024, 2, 9, 19, 30, tzinfo=UTC)
    assert [s.window.trading_date for s in pop.primary] == [date(2024, 2, d) for d in (9, 15, 20)]
    assert [s.window.trading_date for s in pop.holdout] == [date(2024, 2, 21)]
    assert pop.excluded == [
        (date(2024, 2, 14), "ash_wednesday"),
        (date(2024, 2, 16), "grid_incompatible"),
        (date(2024, 2, 19), "no_data"),
    ]


def test_grid_needs_only_one_series_at_the_open_as_frozen() -> None:
    # the frozen text excludes a session when the Ibovespa AND the WIN both lack a bar in
    # [O, O+5 min); one of them is enough to keep it
    d = date(2024, 12, 17)
    pop = build_population(day_bars(d, (10, 0)), day_bars(d, (10, 7), 127000))
    assert pop.funnel["grid_incompatible"] == 0 and pop.funnel["n_hist"] == 1


def test_expiry_day_is_excluded() -> None:
    days = [date(2024, 12, d) for d in (17, 18, 19)]  # WINZ24 expires Wed 18/12/2024
    win = [b for d in days for b in day_bars(d)]
    ibov = [b for d in days for b in day_bars(d, price=127000)]
    pop = build_population(win, ibov)
    assert pop.funnel["win_expiry"] == 1
    assert [s.window.trading_date for s in pop.sessions] == [date(2024, 12, 17), date(2024, 12, 19)]


def test_dates_before_the_calendar_coverage_are_counted_and_left_out() -> None:
    days = [date(2020, 12, 30), date(2021, 1, 4)]
    win = [b for d in days for b in day_bars(d)]
    ibov = [b for d in days for b in day_bars(d, price=127000)]
    pop = build_population(win, ibov)
    assert pop.before_coverage == 1
    assert [s.window.trading_date for s in pop.sessions] == [date(2021, 1, 4)]


def test_overnight_gaps_are_a_diagnostic_in_bp() -> None:
    days = [date(2024, 12, 17), date(2024, 12, 19)]
    win = day_bars(days[0], price=120000) + day_bars(days[1], price=122400)
    ibov = [b for d in days for b in day_bars(d, price=127000)]
    pop = build_population(win, ibov)
    gaps = overnight_gaps(pop.sessions)
    assert gaps == [(date(2024, 12, 19), Decimal(200))]
