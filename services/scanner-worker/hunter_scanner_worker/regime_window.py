"""Which hours a pass produces: the backfill rule, the repair rule, and the cut.

Split out of ``regime_job`` because it is the one part of the producer that is a
*policy* — pure arithmetic over the set of hours already on disk — and because
getting it wrong is invisible from the outside: the job keeps running, the rows
keep being written, and an hour classified ``unknown`` during a candle gap stays
``unknown`` forever after the gap is filled (the bug this module exists to state;
code-reviewer on ``f7aed39``).

Two rules, answering two different questions, unioned.

**Backfill — "every hour of the window with no row".** Answers *did this producer
ever run for that hour?* It fills thirty-one days on the first pass over a fresh
database and produces nothing afterwards, because by then every hour has a row.

**Repair — "every hour of the last ``repair_hours``, row or not".** Answers *are
the candles that hour was decided from still the candles on disk?* An hour that
was written while a minute was missing **has** a row, so the backfill rule will
never look at it again; recomputing it and comparing digests is the only thing
that can heal it. Seventy-two hours is the depth a gap repair realistically
reaches back (``docs/PIPELINE.md`` §1b) and it costs one extra fold of 72 hours
of the universe per pass. Deeper than that is ``--repair-days``, run by hand,
once, after a big backfill: folding a month of the universe on *every* hourly
pass would buy nothing on the 99 % of passes where nothing moved.

The union is then clipped to the backfill window — asking to repair deeper than
``days`` repairs to ``days``, because an hour outside the window has no row and
no reader. A caller that wants more widens both, which is exactly what
``regime_hourly.main`` does with ``--repair-days``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

HOUR = timedelta(hours=1)

BACKFILL_DAYS = 31
"""How far back the first run fills. Thirty-one days is the replay window the
cohorts on disk cover (``docs/PIPELINE.md`` §6c) plus a day of margin."""

REPAIR_HOURS = 72
"""How far back every pass recomputes and compares digests. Three days: long
enough that a candle gap noticed and repaired overnight is still healed
automatically, short enough that the extra fold is 72 hours of the universe and
not a month of it."""

__all__ = ["BACKFILL_DAYS", "HOUR", "REPAIR_HOURS", "floor_hour", "hours_due"]


def floor_hour(value: datetime) -> datetime:
    """The cut: the start of the hour that has closed at or before ``value``."""
    return ensure_utc(value).replace(minute=0, second=0, microsecond=0)


def hours_due(
    cut: datetime,
    *,
    days: int,
    known: Mapping[datetime, str | None],
    repair_hours: int = REPAIR_HOURS,
) -> list[datetime]:
    """Hours with no row, plus every hour of the repair window, oldest first.

    The cut is always in the answer: it is inside the repair window for any
    ``repair_hours >= 0``, and it is the one hour whose candles may still be
    arriving, so it is recomputed even when a row for it already exists.
    """
    first = cut - timedelta(days=days)
    repair_from = cut - max(repair_hours, 0) * HOUR
    due: list[datetime] = []
    hour = first
    while hour <= cut:
        if hour >= repair_from or hour not in known:
            due.append(hour)
        hour += HOUR
    return due
