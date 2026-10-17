"""B3 history calendar 2021–2026 (``hunter_indicators.b3.calendar_history``)."""

from __future__ import annotations

from datetime import date

import pytest

from hunter_indicators.b3 import calendar_2026
from hunter_indicators.b3.calendar_history import (
    NO_TRADING_DAYS,
    SHORTENED_DAYS,
    OutsideHistoryCoverage,
    is_session,
    is_win_expiry,
    nearest_wednesday_to_15,
    sessions_between,
    win_expiry,
)

pytestmark = pytest.mark.unit


def test_only_weekdays_are_listed_and_ash_wednesdays_are_wednesdays() -> None:
    assert all(d.weekday() < 5 for d in NO_TRADING_DAYS)
    assert all(d.weekday() == 2 for d in SHORTENED_DAYS)
    assert not set(NO_TRADING_DAYS) & set(SHORTENED_DAYS)


def test_agrees_with_the_2026_module_where_both_cover() -> None:
    for day in calendar_2026.NO_TRADING_DAYS:
        if day.year == 2026:
            assert not is_session(day), day
    assert win_expiry(2026, 12) == date(2026, 12, 16)  # WINZ26 in calendar_2026


def test_known_sessions_and_holidays() -> None:
    assert not is_session(date(2021, 1, 25))  # São Paulo closed listed trading in 2021
    assert is_session(date(2022, 1, 25))  # not from 2022 on (not on the B3 page)
    assert is_session(date(2022, 11, 24))  # World Cup day: hours unchanged
    assert not is_session(date(2024, 3, 30))  # Saturday
    assert sessions_between(date(2021, 1, 1), date(2021, 1, 8)) == [
        date(2021, 1, 4),
        date(2021, 1, 5),
        date(2021, 1, 6),
        date(2021, 1, 7),
        date(2021, 1, 8),
    ]


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [
        (2024, 12, date(2024, 12, 18)),  # 15th is a Sunday → forward 3
        (2023, 2, date(2023, 2, 15)),  # 15th is a Wednesday
        (2024, 2, date(2024, 2, 14)),  # 15th is a Thursday → back 1 (Ash Wednesday, a session)
        (2022, 10, date(2022, 10, 12)),  # 15th is a Saturday → back 3
    ],
)
def test_nearest_wednesday_rule(year: int, month: int, expected: date) -> None:
    assert nearest_wednesday_to_15(year, month) == expected


def test_expiry_on_a_holiday_moves_to_the_next_session() -> None:
    # 12/10/2022 (nearest Wednesday to 15/10, a Saturday) is Nossa Senhora Aparecida
    assert not is_session(date(2022, 10, 12))
    assert win_expiry(2022, 10) == date(2022, 10, 13)
    assert is_win_expiry(date(2022, 10, 13))
    assert not is_win_expiry(date(2022, 10, 12))


def test_odd_months_have_no_win_expiry_and_coverage_is_enforced() -> None:
    with pytest.raises(ValueError, match="even months"):
        win_expiry(2024, 3)
    assert not is_win_expiry(date(2024, 3, 13))
    with pytest.raises(OutsideHistoryCoverage):
        is_session(date(2020, 12, 30))
