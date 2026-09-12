"""Which minutes a ``market_dispersion`` backfill is allowed to fold, and why.

T3.90, the shape ``breadth_windows`` has (T3.77c, itself the shape
``partition_plan`` has, DATABASE.md §1.3): the *plan* is the part with a rule in
it, it is pure, and a pure plan is the part a unit test can hold still. Nothing
here touches a session, a clock or a role.

**The first rule is ``breadth``'s**: ``--apply`` folds only the minutes of days
whose dense coverage reaches the series' floor. A refusal *is* a write on this
table — a minute folded over a day with no candles lands as
``reason = 'insufficient_coverage'``, and ``0020`` grants nobody ``UPDATE`` or
``DELETE``, so that row is a **permanent tombstone** for that minute in
``dispersion_24h_v1``, never recomputable, only superseded by a whole new version.
The floor arrives as an argument rather than as an import from
``hunter_indicators.breadth``: it is a property of *this* series' spec, and the day
one series relaxes its floor the other must not move with it.

**The second rule is this series' own, and it is the one with teeth.** A reading at
minute ``T`` folds a close from ``T`` and a close from ``T - 24 h``. So a kept day
whose **predecessor** was skipped produces 1 440 tombstones and not a handful: every
minute of it reaches back into the day that had no candles. ``breadth`` declared
this boundary as "the first five minutes of a kept day"; at a 24 h horizon it is the
**whole** day. :func:`foldable_days` is therefore stricter than
:func:`days_above_the_floor`: a day is foldable only when it *and* the day before it
cleared the floor.

**The third rule is the reference.** Every reading of this series is measured
against one market (``BTCUSDT``). A day on which the reference has no candles folds
to ``btc_missing`` for all 1 440 minutes — the same permanent tombstone, bought for
nothing. So a day is foldable only when the reference is dense on it **and** on the
day before it.

Consequence worth declaring: ``--days 90`` folds at most **89** days, because the
oldest day of the report has no predecessor inside it. That is not a rounding
error; it is the horizon showing up in the plan.

``--include-unusable`` (``keep=None`` at the call site) is the escape hatch, for the
operator who wants the absence recorded as a fact instead of left as a gap. A choice
made in front of the coverage report, never a default.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import date
    from decimal import Decimal

ONE_DAY = timedelta(days=1)

__all__ = ["ONE_DAY", "days_above_the_floor", "foldable_days"]


def days_above_the_floor(rows: Iterable[Any], *, universe: int, floor: Decimal) -> set[date]:
    """The calendar days whose dense coverage reaches ``floor``.

    Pure, and the single source of that half of the verdict: the report prints it
    and :func:`foldable_days` narrows it, so what ``--apply`` writes is exactly what
    the operator was shown. A day absent from ``rows`` has no candle at all and is
    therefore never above the floor. An empty universe is not a floor anybody can
    clear, so it keeps no day rather than dividing by zero.
    """
    if universe <= 0:
        return set()
    limit = float(floor)
    return {row.day.date() for row in rows if row.dense_markets / universe >= limit}


def foldable_days(above: set[date], *, reference_days: set[date]) -> set[date]:
    """Of the days above the floor, the ones a 24 h horizon can actually fold.

    A day qualifies when **four** things hold: it is above the floor, the day before
    it is above the floor, the reference market is dense on it, and the reference is
    dense on the day before it. The two "day before" clauses are the horizon: every
    minute of a day reaches back into its predecessor, so a predecessor nobody could
    see turns the whole day into tombstones.

    ``reference_days`` is measured, never assumed — it is the same per-day candle
    count the report runs for the universe, run again for one market id.
    """
    return {
        day
        for day in above
        if day - ONE_DAY in above and day in reference_days and day - ONE_DAY in reference_days
    }
