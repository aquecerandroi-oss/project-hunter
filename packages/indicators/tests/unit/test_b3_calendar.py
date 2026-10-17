"""B3 session data for the H-038 weeks (``hunter_indicators.b3.calendar_2026``).

Expected values come from the official B3 pages read on 17/10/2026 (cited in the module).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from hunter_indicators.b3.calendar_2026 import (
    COVERAGE_END,
    COVERAGE_START,
    WIN_SPEC,
    OutsideCalendarCoverage,
    b3_session,
    win_contract,
)
from hunter_indicators.b3.contract import NoTradeReason

pytestmark = pytest.mark.unit


def test_monday_19_october_is_a_regular_session_with_the_current_grid() -> None:
    s = b3_session(date(2026, 10, 19))
    assert s is not None
    assert s.open_at == datetime(2026, 10, 19, 13, 0, tzinfo=UTC)  # 10:00 BRT
    assert s.close_at == datetime(2026, 10, 19, 20, 0, tzinfo=UTC)  # 17:00 BRT
    assert s.previous_close_at == datetime(2026, 10, 16, 20, 0, tzinfo=UTC)  # Fri 16/10 17:00
    assert s.exclusions == ()


@pytest.mark.parametrize(
    "day",
    [
        date(2026, 11, 2),  # Finados
        date(2026, 11, 20),  # Dia Nacional de Zumbi e Consciência Negra
        date(2026, 12, 24),  # véspera de Natal — sem sessão de negociação
        date(2026, 12, 25),  # Natal
        date(2026, 12, 31),  # expediente interno — sem sessão de negociação
        date(2026, 10, 24),  # Saturday
        date(2026, 10, 25),  # Sunday
    ],
)
def test_no_session_on_b3_holidays_and_weekends(day: date) -> None:
    assert b3_session(day) is None


def test_new_grid_from_3_november_and_previous_close_skips_the_holiday() -> None:
    s = b3_session(date(2026, 11, 3))
    assert s is not None
    assert s.open_at == datetime(2026, 11, 3, 13, 0, tzinfo=UTC)  # 10:00 BRT
    assert s.close_at == datetime(2026, 11, 3, 21, 0, tzinfo=UTC)  # 18:00 BRT
    assert s.previous_close_at == datetime(2026, 10, 30, 20, 0, tzinfo=UTC)  # Fri 30/10 17:00


def test_previous_close_skips_the_20_november_holiday() -> None:
    s = b3_session(date(2026, 11, 23))
    assert s is not None
    assert s.previous_close_at == datetime(2026, 11, 19, 21, 0, tzinfo=UTC)  # Thu 19/11 18:00


def test_win_expiry_day_is_excluded_and_the_contract_rolls_after_it() -> None:
    s = b3_session(date(2026, 12, 16))  # Wednesday closest to 15/12
    assert s is not None
    assert s.exclusions == (NoTradeReason.WIN_EXPIRY_DAY,)
    assert win_contract(date(2026, 10, 19)) == "WINZ26"
    assert win_contract(date(2026, 12, 16)) == "WINZ26"
    assert win_contract(date(2026, 12, 17)) == "WING27"


def test_every_session_in_coverage_has_ordered_times() -> None:
    day = COVERAGE_START
    sessions = 0
    while day <= COVERAGE_END:
        s = b3_session(day)
        if s is not None:
            sessions += 1
            assert s.previous_close_at < s.open_at < s.close_at
        day = date.fromordinal(day.toordinal() + 1)
    # 19/10–31/12/2026: 54 weekdays minus 02/11, 20/11, 24/12, 25/12, 31/12 = 49 sessions
    assert sessions == 49


@pytest.mark.parametrize("day", [date(2026, 10, 16), date(2027, 1, 4)])
def test_outside_coverage_is_an_error_not_a_guess(day: date) -> None:
    with pytest.raises(OutsideCalendarCoverage):
        b3_session(day)


def test_win_spec_is_the_b3_contract_data() -> None:
    assert WIN_SPEC.root == "WIN"
    assert WIN_SPEC.tick_size == Decimal("5")
    assert WIN_SPEC.point_value_brl == Decimal("0.20")
