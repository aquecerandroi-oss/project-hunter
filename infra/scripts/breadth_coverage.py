"""What a ``market_breadth`` backfill would be worth: the per-day coverage report.

T3.88, split out of ``backfill_breadth.py`` for the reason ``breadth_windows``
was split out of it in T3.77c (and ``partition_plan`` out of
``create_partitions.py``, DATABASE.md §1.3): the tool was at 319 of the repo's
350 lines, and the *measurement* is a separable thing from the *fill*. Nothing
here writes.

**The universe is the series'.** ``breadth_v1`` measured every monitored active
perpetual (~200), which is why 87 of the last 91 days were below the 80 % floor:
only 16 markets have 1-minute candles going back 90 days. ``breadth_v2`` measures
exactly those 16 (:mod:`hunter_core.universe`, the same rule the shadow universe
uses), so the same 90 days that were unmeasurable for v1 are measurable for v2 —
and this report is where that claim is checked before anything is written, per
day, against real candles.

``dense_markets`` counts the markets with at least ``dense`` of the day's 1 440
minutes: a market with forty candles on a day contributes to *some* minutes and to
almost none, and counting it the same as a complete one would overstate what a
backfill could cover.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from breadth_windows import days_above_the_floor
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from hunter_scanner_worker.breadth_repo import history_universe_ids, monitored_universe

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_indicators.breadth import BreadthSpec

__all__ = ["CoverageRow", "day_coverage", "print_coverage", "universe_ids"]

_DENSE_SQL = text(
    "WITH per_day AS ("
    "  SELECT date_trunc('day', c.open_time) AS day, c.market_id, count(*) AS minutes"
    "    FROM candles c"
    "   WHERE c.timeframe = '1m' AND c.is_final AND c.market_id = ANY(:market_ids)"
    "     AND c.open_time >= :start AND c.open_time < :end"
    "   GROUP BY 1, 2"
    ") "
    "SELECT day, count(*) AS markets,"
    "       count(*) FILTER (WHERE minutes >= :dense) AS dense_markets,"
    "       sum(minutes) AS candles "
    "  FROM per_day GROUP BY day ORDER BY day"
).bindparams(bindparam("market_ids", type_=ARRAY(PG_UUID(as_uuid=True))))
"""How many markets **of this series' universe** have 1-minute candles on each day
of the window, and how many of them are dense. The universe arrives as an array
of ids rather than as a sub-select so that the report and the fold answer to the
same list — one membership query, one universe, two consumers."""


@dataclass(frozen=True, slots=True)
class CoverageRow:
    """One day of the report. ``day`` is a ``date_trunc``, hence UTC midnight.

    The field names are the ones :func:`breadth_windows.days_above_the_floor`
    reads (``day``, ``dense_markets``): the verdict is computed once, by that pure
    function, and printed here — never recomputed with a second comparison that
    could drift from it.
    """

    day: datetime
    markets: int
    dense_markets: int
    candles: int


async def universe_ids(
    session: AsyncSession, *, exchange: str, spec: BreadthSpec, as_of: datetime
) -> list[UUID]:
    """The market ids ``spec`` folds — the same call the producer makes."""
    if not spec.restricted:
        return await monitored_universe(session, exchange)
    return await history_universe_ids(
        session, exchange=exchange, min_history_days=spec.min_history_days, clock=lambda: as_of
    )


async def day_coverage(
    session: AsyncSession,
    *,
    market_ids: list[UUID],
    days: int,
    end: datetime,
    dense: int,
) -> list[CoverageRow]:
    """The report's rows, oldest first. An empty universe reports no day."""
    if not market_ids:
        return []
    rows = await session.execute(
        _DENSE_SQL,
        {
            "market_ids": market_ids,
            "start": end - timedelta(days=days),
            "end": end,
            "dense": dense,
        },
    )
    return [
        CoverageRow(
            day=row.day,
            markets=int(row.markets),
            dense_markets=int(row.dense_markets),
            candles=int(row.candles),
        )
        for row in rows
    ]


def print_coverage(
    rows: list[CoverageRow], *, universe: int, dense: int, spec: BreadthSpec
) -> set[date]:
    """Print the report and return the days a fill would actually cover."""
    floor = (spec.min_coverage * universe).to_integral_value(rounding="ROUND_CEILING")
    print(f"série: {spec.version}  universo: {spec.universe_rule}")
    print(f"universo agora: {universe} perpétuas")
    print(f"piso de cobertura: {spec.min_coverage} -> {floor} mercados densos por minuto")
    print(f"denso = ao menos {dense} de 1440 velas de 1 min no dia")
    print("")
    print(f"{'dia':<12}{'mercados':>10}{'densos':>10}{'cobertura':>12}{'velas':>12}")
    above = days_above_the_floor(rows, universe=universe)
    for row in rows:
        coverage = 0.0 if universe <= 0 else row.dense_markets / universe
        print(
            f"{row.day.date().isoformat():<12}{row.markets:>10}{row.dense_markets:>10}"
            f"{coverage:>11.1%}{row.candles:>12}"
        )
    print("")
    print(f"dias que passariam o piso de cobertura: {len(above)} de {len(rows)}")
    return above
