"""Which minutes a ``market_breadth`` backfill is allowed to fold, and why.

T3.77c. Split out of ``backfill_breadth.py`` for the reason ``partition_plan``
was split out of ``create_partitions.py`` (DATABASE.md §1.3): the *plan* is the
part with a rule in it, it is pure, and a pure plan is the part a unit test can
hold still. Nothing here touches a session, a clock or a role.

**The rule.** ``--apply`` folds only the minutes of days whose dense coverage
reaches :data:`~hunter_indicators.breadth.MIN_COVERAGE`. A refusal *is* a write
on this table: a minute folded over a day with no candles lands as a
``reason = 'insufficient_coverage'`` row, and ``0019`` grants nobody ``UPDATE``
or ``DELETE`` on ``market_breadth``, so that row is a **permanent tombstone** for
that minute in ``breadth_v1`` — never recomputable, only superseded by a whole
new ``breadth_version`` (``infra/migrations/ddl/breadth.py``, DATABASE.md §31).
Ninety days of which eleven have candles would be ~114 000 tombstones bought to
gain ~15 000 readings.

``--include-unusable`` (``keep=None``) is the escape hatch, for the operator who
wants the absence recorded as a fact instead of left as a gap. A choice made in
front of the coverage report, never a default.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING, Any

from hunter_indicators.breadth import MIN_COVERAGE

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date

MINUTES_PER_DAY = 1_440
MINUTE = timedelta(minutes=1)

__all__ = ["MINUTES_PER_DAY", "days_above_the_floor", "fold_windows"]


def days_above_the_floor(rows: Iterable[Any], *, universe: int) -> set[date]:
    """The calendar days whose dense coverage reaches ``MIN_COVERAGE``.

    Pure, and the single source of the verdict: the report prints it and
    :func:`fold_windows` skips by it, so what ``--apply`` writes is exactly what
    the operator was shown. A day absent from ``rows`` has no candle at all and is
    therefore never above the floor. An empty universe is not a floor anybody can
    clear, so it keeps no day rather than dividing by zero.
    """
    if universe <= 0:
        return set()
    floor = float(MIN_COVERAGE)
    return {row.day.date() for row in rows if row.dense_markets / universe >= floor}


def fold_windows(cut: datetime, *, days: int, keep: set[date] | None) -> list[tuple[datetime, int]]:
    """The ``(cut, back)`` sub-windows to fold, oldest first.

    ``keep is None`` is ``--include-unusable``: one window over the whole span,
    the behaviour before T3.77c. Otherwise every calendar day of the span that is
    not in ``keep`` is cut out and the survivors are merged into the longest
    contiguous runs available — one ``run_breadth_once`` call per run, so eleven
    scattered good days cost eleven folds and never ninety.

    The span is ``[cut - days * 1440 min, cut]`` inclusive, exactly what a single
    ``back = days * 1440`` call covers, and each window is returned the way
    ``run_breadth_once`` reads one: a closed upper minute and a count of minutes
    back from it. Days are UTC calendar days, the same grouping the coverage
    report's ``date_trunc('day', open_time)`` uses — the two must agree or the
    report would be describing days the fill does not.

    One boundary is left as it is: the first five minutes of a kept day fold
    candles that opened on the day before it, so when that day was skipped those
    few minutes may still land as ``insufficient_coverage``. Those tombstones are
    measured rather than guessed, which is the distinction the flag draws.
    """
    span = days * MINUTES_PER_DAY
    if keep is None:
        return [(cut, span)]
    start = cut - span * MINUTE
    windows: list[tuple[datetime, datetime]] = []
    day, last = start.date(), cut.date()
    low: datetime | None = None
    high = start
    while day <= last:
        midnight = datetime.combine(day, time.min, tzinfo=UTC)
        if day in keep:
            low = max(start, midnight) if low is None else low
            high = min(cut + MINUTE, midnight + timedelta(days=1))
        elif low is not None:
            windows.append((low, high))
            low = None
        day += timedelta(days=1)
    if low is not None:
        windows.append((low, high))
    return [(top - MINUTE, int((top - MINUTE - bottom) / MINUTE)) for bottom, top in windows]
