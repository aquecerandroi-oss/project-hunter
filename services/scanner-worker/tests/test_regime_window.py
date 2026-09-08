"""Which hours a pass is due to produce — the rule that decides whether a hole heals.

The bug this file exists to catch (code-reviewer on ``f7aed39``) leaves no trace
anywhere else: with "every hour with no row" as the only rule, an hour written
``unknown`` while a candle was missing **has** a row, is never looked at again,
and stays ``unknown`` after the gap is repaired — the job logs a healthy pass
every hour while the series keeps a permanent hole. The arithmetic is pure, so
the proof is a table of hours, not a database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_scanner_worker.regime_window import HOUR, REPAIR_HOURS, floor_hour, hours_due

pytestmark = pytest.mark.unit

CUT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
DAYS = 1
WINDOW = 25
"""``[CUT - 1 day, CUT]``, both ends included."""


def _all_hours(days: int = DAYS) -> list[datetime]:
    first = CUT - timedelta(days=days)
    hours: list[datetime] = []
    hour = first
    while hour <= CUT:
        hours.append(hour)
        hour += HOUR
    return hours


def _known(*, digest: str = "d") -> dict[datetime, str | None]:
    """A full window: every hour already has a row, as in steady state."""
    return dict.fromkeys(_all_hours(), digest)


def test_the_cut_is_the_hour_that_closed_at_or_before_the_clock() -> None:
    """12:37 produces 12:00 — the pass never labels an hour still in flight."""
    assert floor_hour(datetime(2026, 9, 8, 12, 37, 41, 5, tzinfo=UTC)) == CUT
    assert floor_hour(CUT) == CUT


def test_an_empty_table_is_due_the_whole_window() -> None:
    """The first pass over a fresh database: 24 hours plus the cut."""
    due = hours_due(CUT, days=DAYS, known={})

    assert due == _all_hours()
    assert len(due) == WINDOW


def test_a_full_window_is_still_due_its_repair_window() -> None:
    """Steady state: nothing is missing, and the last 72 h are recomputed anyway.

    Recomputed, not rewritten — the digest decides that, one layer down.
    """
    due = hours_due(CUT, days=DAYS, known=_known(), repair_hours=3)

    assert due == [CUT - 3 * HOUR, CUT - 2 * HOUR, CUT - HOUR, CUT]


def test_an_hour_inside_the_repair_window_is_due_even_though_it_has_a_row() -> None:
    """HIGH-1: the hour written ``unknown`` during a gap is exactly this hour."""
    known = _known()
    broken = CUT - 2 * HOUR

    assert broken in known
    assert broken in hours_due(CUT, days=DAYS, known=known, repair_hours=REPAIR_HOURS)


def test_the_old_rule_alone_would_never_look_at_that_hour_again() -> None:
    """``repair_hours=0`` is the behaviour before this fix, kept as the contrast.

    Only the cut comes back: every other hour has a row, so a candle backfill
    older than one hour would never reach the series.
    """
    assert hours_due(CUT, days=DAYS, known=_known(), repair_hours=0) == [CUT]


def test_a_missing_hour_older_than_the_repair_window_is_still_due() -> None:
    """The two rules are a union: backfill reaches where repair does not."""
    known = _known()
    hole = CUT - 20 * HOUR
    del known[hole]

    due = hours_due(CUT, days=DAYS, known=known, repair_hours=3)

    assert due == [hole, CUT - 3 * HOUR, CUT - 2 * HOUR, CUT - HOUR, CUT]


def test_the_repair_window_is_clipped_by_the_backfill_window() -> None:
    """Asking to repair deeper than ``days`` repairs to ``days``, never beyond.

    An hour outside the backfill window has no row and no reader; producing it
    from here would write history nobody asked for. The caller that wants more
    widens both — ``regime_hourly.main`` raises ``--backfill-days`` to match
    ``--repair-days`` for this reason.
    """
    due = hours_due(CUT, days=DAYS, known=_known(), repair_hours=100)

    assert due == _all_hours()
    assert due[0] == CUT - timedelta(days=DAYS)


def test_the_answer_is_ordered_oldest_first_and_has_no_duplicates() -> None:
    """The pass writes in this order, so ``run.last_ts`` ends up being the cut."""
    known = _known()
    del known[CUT - 20 * HOUR]

    due = hours_due(CUT, days=DAYS, known=known, repair_hours=6)

    assert due == sorted(due)
    assert len(set(due)) == len(due)
    assert due[-1] == CUT
