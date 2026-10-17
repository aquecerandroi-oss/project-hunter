"""Pure session and calendar helpers for B3 (no IO, no clock: dates and data come in).

``session_date`` is the local date in ``America/Sao_Paulo`` (§1.1); every instant the
engine compares is UTC. The calendar is **data the caller passes** — holidays, shortened
days, grid rows with validity, contract expiries (R3's ``b3_holidays``,
``b3_session_grids``, ``b3_contracts``). ``hunter_indicators.b3.calendar_2026`` holds the
same facts for H-038's research window; it is deliberately not imported: the money core
must not depend on the research package (numpy/polars/sqlalchemy) nor on a hard-coded
window, and R1 may not add a dependency. The service feeds those rows from the database.

``zoneinfo`` reads the tz database shipped by ``tzdata`` (declared by ``hunter-risk``);
Brazil has had no DST since 2019, but the zone is used instead of a fixed UTC−3 so a future
rule change is a data update, not a code change.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from pydantic import Field

from hunter_risk_b3.base import B3Model, as_utc
from hunter_risk_b3.context import CalendarB3, ClockCheck, CurrentContract, SessionContext
from hunter_risk_b3.limits import RiskLimitsB3

__all__ = [
    "SAO_PAULO",
    "ContractRow",
    "GridRow",
    "build_calendar",
    "build_session",
    "grid_for",
    "local_to_utc",
    "session_date_of",
]

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


class GridRow(B3Model):
    """One ``b3_session_grids`` row. ``only_on`` marks a shortened session's own grid."""

    grid_version: str = Field(min_length=1)
    valid_from: date
    valid_to: date | None
    """Inclusive; ``None`` = open-ended."""
    open_local: time
    close_local: time
    session_end_local: time
    only_on: date | None = None


class ContractRow(B3Model):
    symbol: str = Field(min_length=1)
    root: str = Field(min_length=1)
    expiry_date: date
    """Last trading day."""


def session_date_of(instant: datetime) -> date:
    return as_utc(instant).astimezone(SAO_PAULO).date()


def local_to_utc(day: date, local: time) -> datetime:
    return datetime.combine(day, local, tzinfo=SAO_PAULO).astimezone(UTC)


def grid_for(day: date, grids: Sequence[GridRow], *, shortened: bool) -> GridRow | None:
    """The single grid valid for ``day``; none or several (an overlap) ⇒ ``None``."""
    if shortened:
        found = [g for g in grids if g.only_on == day]
    else:
        found = [
            g
            for g in grids
            if g.only_on is None
            and g.valid_from <= day
            and (g.valid_to is None or day <= g.valid_to)
        ]
    return found[0] if len(found) == 1 else None


def _current_contract(
    day: date, contracts: Sequence[ContractRow], root: str
) -> CurrentContract | None:
    live = sorted((c for c in contracts if c.root == root and c.expiry_date >= day),
                  key=lambda c: c.expiry_date)  # fmt: skip
    if not live:
        return None
    first = live[0]
    return CurrentContract(symbol=first.symbol, root=first.root, expiry_date=first.expiry_date)


def build_calendar(
    day: date,
    *,
    holidays: Collection[date],
    shortened_days: Collection[date],
    grids: Sequence[GridRow],
    contracts: Sequence[ContractRow],
    root: str,
) -> CalendarB3:
    """The ``calendar`` argument for ``day``. Weekends count as non-trading days."""
    shortened = day in shortened_days
    contract = _current_contract(day, contracts, root)
    return CalendarB3(
        is_holiday=day.weekday() >= 5 or day in holidays,
        is_shortened=shortened,
        has_grid=grid_for(day, grids, shortened=shortened) is not None,
        current_contract=contract,
        is_expiry_day=contract is not None and contract.expiry_date == day,
        read_ok=True,
    )


def build_session(
    day: date, grid: GridRow, limits: RiskLimitsB3, clock: ClockCheck
) -> SessionContext:
    """The ``session`` argument: grid times plus the profile's local times, in UTC.
    ``flatten_at_local``/``rico_flatten_local`` unset (D6) stay ``None``."""

    def at(local: time | None) -> datetime | None:
        return None if local is None else local_to_utc(day, local)

    return SessionContext(
        session_date=day,
        open_utc=local_to_utc(day, grid.open_local),
        close_utc=local_to_utc(day, grid.close_local),
        flatten_at_utc=at(limits.flatten_at_local),
        rico_flatten_utc=at(limits.rico_flatten_local),
        session_end_utc=local_to_utc(day, grid.session_end_local),
        entry_cutoff_utc=at(limits.entry_cutoff_local),
        grid_version=grid.grid_version,
        clock=clock,
    )
