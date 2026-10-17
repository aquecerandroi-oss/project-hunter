"""Pure session/calendar helpers: B3 dates are America/Sao_Paulo, instants are UTC;
weekends and holidays are not trading days; a shortened session needs its own grid; the
current contract is the first one whose last trading day is not before today."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from hunter_risk_b3 import (
    ClockCheck,
    ContractRow,
    GridRow,
    build_calendar,
    build_session,
    local_to_utc,
    session_date_of,
)

from . import factories as fx

pytestmark = pytest.mark.unit

GRIDS = (
    GridRow(grid_version="g1", valid_from=date(2026, 10, 13), valid_to=date(2026, 11, 2),
            open_local=time(10), close_local=time(17), session_end_local=time(18, 25)),
    GridRow(grid_version="g2", valid_from=date(2026, 11, 3), valid_to=None,
            open_local=time(10), close_local=time(18), session_end_local=time(18, 25)),
    GridRow(grid_version="g-short", valid_from=date(2026, 12, 23), valid_to=date(2026, 12, 23),
            open_local=time(10), close_local=time(13), session_end_local=time(13, 30),
            only_on=date(2026, 12, 23)),
)  # fmt: skip
CONTRACTS = (
    ContractRow(symbol="WINZ26", root="WIN", expiry_date=date(2026, 12, 16)),
    ContractRow(symbol="WING27", root="WIN", expiry_date=date(2027, 2, 17)),
)
HOLIDAYS = {date(2026, 11, 2), date(2026, 11, 20)}


def _cal(day: date, shortened: frozenset[date] = frozenset()):
    return build_calendar(
        day, holidays=HOLIDAYS, shortened_days=shortened, grids=GRIDS, contracts=CONTRACTS,
        root="WIN",
    )  # fmt: skip


def test_session_date_is_the_sao_paulo_date() -> None:
    assert session_date_of(datetime(2026, 10, 21, 2, 59, tzinfo=UTC)) == date(2026, 10, 20)
    assert session_date_of(datetime(2026, 10, 21, 3, 0, tzinfo=UTC)) == date(2026, 10, 21)


def test_naive_instants_are_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        session_date_of(datetime(2026, 10, 21, 3, 0))  # noqa: DTZ001


def test_local_to_utc() -> None:
    assert local_to_utc(date(2026, 10, 20), time(16, 30)) == datetime(
        2026, 10, 20, 19, 30, tzinfo=UTC
    )


def test_normal_day() -> None:
    cal = _cal(date(2026, 10, 20))
    assert (cal.is_holiday, cal.has_grid, cal.is_expiry_day) == (False, True, False)
    assert cal.current_contract is not None
    assert cal.current_contract.symbol == "WINZ26"


@pytest.mark.parametrize("day", [date(2026, 11, 2), date(2026, 10, 24), date(2026, 10, 25)])
def test_holidays_and_weekends_are_not_trading_days(day: date) -> None:
    assert _cal(day).is_holiday


def test_expiry_day_and_rollover() -> None:
    assert _cal(date(2026, 12, 16)).is_expiry_day
    nxt = _cal(date(2026, 12, 17)).current_contract
    assert nxt is not None
    assert nxt.symbol == "WING27"


def test_shortened_day_needs_its_own_grid() -> None:
    with_grid = _cal(date(2026, 12, 23), frozenset({date(2026, 12, 23)}))
    assert (with_grid.is_shortened, with_grid.has_grid) == (True, True)
    without = _cal(date(2026, 12, 22), frozenset({date(2026, 12, 22)}))
    assert (without.is_shortened, without.has_grid) == (True, False)


def test_overlapping_grids_are_no_grid() -> None:
    dup = (*GRIDS, GRIDS[0].model_copy(update={"grid_version": "g1-bis"}))
    cal = build_calendar(
        date(2026, 10, 20), holidays=HOLIDAYS, shortened_days=frozenset(), grids=dup,
        contracts=CONTRACTS, root="WIN",
    )  # fmt: skip
    assert cal.has_grid is False


def test_no_contract_on_file() -> None:
    cal = build_calendar(
        date(2027, 3, 1), holidays=HOLIDAYS, shortened_days=frozenset(), grids=GRIDS,
        contracts=CONTRACTS, root="WIN",
    )  # fmt: skip
    assert cal.current_contract is None


def test_build_session_from_grid_and_limits() -> None:
    clock = ClockCheck(offset_ms=10, measured_at=fx.NOW, ok=True)
    session = build_session(date(2026, 10, 20), GRIDS[0], fx.limits(), clock)
    assert session.open_utc == datetime(2026, 10, 20, 13, 0, tzinfo=UTC)
    assert session.close_utc == datetime(2026, 10, 20, 20, 0, tzinfo=UTC)
    assert session.session_end_utc == datetime(2026, 10, 20, 21, 25, tzinfo=UTC)
    assert session.flatten_at_utc == datetime(2026, 10, 20, 19, 50, tzinfo=UTC)
    assert session.rico_flatten_utc == datetime(2026, 10, 20, 20, 10, tzinfo=UTC)
    assert session.entry_cutoff_utc is None
    assert session.grid_version == "g1"


def test_build_session_without_d6_leaves_flatten_unset() -> None:
    clock = ClockCheck(offset_ms=None, measured_at=None, ok=False)
    limits = fx.limits(flatten_at_local=None, rico_flatten_local=None)
    session = build_session(date(2026, 10, 20), GRIDS[0], limits, clock)
    assert (session.flatten_at_utc, session.rico_flatten_utc) == (None, None)
