"""Unit tests for ``infra/scripts/breadth_windows.py`` — which minutes a
``market_breadth`` backfill is allowed to fold.

No database: the rule is pure, and it has to be, because the thing it prevents is
irreversible. ``0019`` grants nobody ``UPDATE`` or ``DELETE`` on
``market_breadth``, so a minute folded over a day with no candles lands as a
``reason = 'insufficient_coverage'`` row that stays there forever in
``breadth_v1`` (DATABASE.md §31). "``--apply`` skipped the days the report just
failed" is therefore a property worth a test rather than a habit worth a comment.

Run:
    uv run pytest infra/scripts/tests/test_backfill_breadth.py -q
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from breadth_windows import (  # noqa: E402  (path surgery must come first)
    MINUTES_PER_DAY,
    days_above_the_floor,
    fold_windows,
)

MINUTE = timedelta(minutes=1)
CUT = datetime(2026, 9, 10, 12, 6, tzinfo=UTC)
UNIVERSE = 200
"""The floor is ``MIN_COVERAGE = 0.80``, so 160 dense markets pass and 159 do
not — the numbers below are picked around that edge on purpose."""


@dataclass(frozen=True)
class _Row:
    """One row of ``_COVERAGE_SQL`` as the report reads it: ``day`` is a
    ``date_trunc('day', open_time)``, therefore a UTC-midnight timestamp."""

    day: datetime
    dense_markets: int


def _row(day: int, dense: int) -> _Row:
    return _Row(day=datetime(2026, 9, day, tzinfo=UTC), dense_markets=dense)


def _minutes(windows: list[tuple[datetime, int]]) -> set[datetime]:
    """Every minute the windows would ask ``run_breadth_once`` to produce.

    ``run_breadth_once`` folds ``[cut - back, cut]`` **inclusive**, which is the
    arithmetic these windows are written against, so expanding them here is the
    only honest way to assert what a fill would touch.
    """
    touched: set[datetime] = set()
    for cut, back in windows:
        touched.update(cut - step * MINUTE for step in range(back + 1))
    return touched


def test_the_floor_is_read_from_the_dense_markets_of_each_day() -> None:
    """160 of 200 is exactly ``MIN_COVERAGE``; 159 is not, and the boundary is
    inclusive because the producer's own ``coverage >= min_coverage`` is."""
    rows = [_row(7, 159), _row(8, 160), _row(9, 200)]

    assert days_above_the_floor(rows, universe=UNIVERSE) == {date(2026, 9, 8), date(2026, 9, 9)}


def test_a_day_the_report_never_mentioned_is_below_the_floor() -> None:
    """A day with no candle at all produces no row in ``_COVERAGE_SQL``, and
    "absent" must read as 0 % rather than as "unknown, fold it anyway"."""
    assert days_above_the_floor([_row(9, 200)], universe=UNIVERSE) == {date(2026, 9, 9)}


def test_an_empty_universe_keeps_no_day_and_does_not_divide_by_zero() -> None:
    """Nobody clears a floor of zero markets; the report says so and the fill
    stops rather than folding ninety days of ``empty_universe``."""
    assert days_above_the_floor([_row(9, 0)], universe=0) == set()


def test_apply_never_folds_a_minute_of_a_day_below_the_floor() -> None:
    """The rule this module exists for, asserted minute by minute.

    Two good days around one bad one: every minute the fill would produce falls
    on 08 or 10, and not one falls on 09 — which in ``breadth_v1`` would be 1 440
    tombstones that no later run can ever take back.
    """
    keep = {date(2026, 9, 8), date(2026, 9, 10)}

    windows = fold_windows(CUT, days=3, keep=keep)

    days_touched = {minute.date() for minute in _minutes(windows)}
    assert days_touched == keep
    assert date(2026, 9, 9) not in days_touched


def test_contiguous_kept_days_become_one_fold_and_a_gap_splits_them() -> None:
    """Eleven scattered good days must not cost ninety folds, and two runs of
    good days must not be bridged across the bad one between them."""
    keep = {date(2026, 9, 8), date(2026, 9, 10)}

    split = fold_windows(CUT, days=3, keep=keep)
    joined = fold_windows(CUT, days=3, keep=keep | {date(2026, 9, 9)})

    assert len(split) == 2
    assert len(joined) == 1


def test_include_unusable_folds_the_whole_span_as_a_single_window() -> None:
    """``keep=None`` is the operator's explicit "record the absence as a fact":
    one window, the exact ``back = days * 1440`` the tool used before T3.77c.
    """
    assert fold_windows(CUT, days=90, keep=None) == [(CUT, 90 * MINUTES_PER_DAY)]


def test_no_day_above_the_floor_means_no_window_at_all() -> None:
    """Not "fold everything", which is what a missing branch would have done:
    the caller refuses out loud and names ``--include-unusable``."""
    assert fold_windows(CUT, days=7, keep=set()) == []


def test_keeping_every_day_covers_exactly_what_one_back_call_covered() -> None:
    """The split may not lose a minute at the edges: with nothing skipped, the
    windows cover the same closed span a single ``back = days * 1440`` did,
    including the cut itself (whose candles are all final by construction).
    """
    days = 3
    keep = {(CUT - step * MINUTE).date() for step in range(days * MINUTES_PER_DAY + 1)}

    split = _minutes(fold_windows(CUT, days=days, keep=keep))

    assert split == _minutes([(CUT, days * MINUTES_PER_DAY)])
    assert max(split) == CUT
    assert min(split) == CUT - days * MINUTES_PER_DAY * MINUTE


def test_a_kept_day_is_folded_whole_and_never_beyond_its_midnight() -> None:
    """The window boundaries are UTC midnights — the same grouping
    ``date_trunc('day', open_time)`` gives the report — so the report describes
    the days the fill actually visits.
    """
    windows = fold_windows(CUT, days=5, keep={date(2026, 9, 7)})

    assert windows == [(datetime(2026, 9, 7, 23, 59, tzinfo=UTC), MINUTES_PER_DAY - 1)]
    minutes = _minutes(windows)
    assert min(minutes) == datetime(2026, 9, 7, tzinfo=UTC)
    assert max(minutes) == datetime(2026, 9, 7, 23, 59, tzinfo=UTC)


def test_the_open_day_is_folded_only_up_to_the_cut() -> None:
    """The last day of the span is still running: its window stops at the cut and
    never names a minute that has not closed."""
    windows = fold_windows(CUT, days=1, keep={CUT.date()})

    assert windows == [(CUT, 12 * 60 + 6)]
    assert max(_minutes(windows)) == CUT
