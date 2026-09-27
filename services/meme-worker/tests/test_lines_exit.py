"""T4.10 — the support line projected to a snapshot's instant, and the streak
of closes below it, from durable rows and nothing else.

T4.98 (EXP-M26 L1) — the line a snapshot is judged against is the **newest
minute known at that snapshot** (``end_time <= at`` and ``computed_at <= at``),
and only while it is fresh (``at - end_time <= 120 s``). A newer minute without
a line (``flat``, ``too_few_points``…) hides every older line; a stale or
unknown support is ``None``, which the exit rule reads as "no line" — neutral.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_meme_worker.lines_exit import (
    SUPPORT_MAX_AGE_S,
    SupportLine,
    below_support,
    next_streak,
    support_at,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 12, 12, 15, tzinfo=UTC)


def _line(
    minute: int,
    support: str | None,
    slope: str | None,
    *,
    computed_after_s: float = 0,
) -> SupportLine:
    end_time = T0 + timedelta(minutes=minute)
    return SupportLine(
        end_time=end_time,
        computed_at=end_time + timedelta(seconds=computed_after_s),
        support_sol=None if support is None else Decimal(support),
        slope_per_min=None if slope is None else Decimal(slope),
    )


LINES = [_line(0, "48", "1"), _line(1, "50", "2")]


def test_the_newest_line_at_or_before_the_instant_is_projected_to_it() -> None:
    assert support_at(LINES, T0 + timedelta(seconds=30)) == Decimal("48.5")
    assert support_at(LINES, T0 + timedelta(minutes=1)) == Decimal(50)
    assert support_at(LINES, T0 + timedelta(minutes=2, seconds=30)) == Decimal(53)
    assert support_at(LINES, T0 - timedelta(seconds=1)) is None, (
        "a minute folded later is not known"
    )
    assert support_at([], T0) is None


def test_the_default_freshness_bound_is_120_seconds() -> None:
    assert SUPPORT_MAX_AGE_S == 120


def test_a_line_older_than_the_bound_is_unknown_and_at_the_bound_still_fresh() -> None:
    line = [_line(0, "48", "1")]
    assert support_at(line, T0 + timedelta(seconds=120)) == Decimal(50)
    assert support_at(line, T0 + timedelta(seconds=121)) is None, (
        "the 20-minute-old line is not a support of this photo"
    )
    assert support_at(line, T0 + timedelta(minutes=20)) is None
    assert support_at(line, T0 + timedelta(seconds=121), max_age_s=180) is not None


def test_a_line_computed_after_the_snapshot_is_ignored() -> None:
    lines = [_line(0, "48", "1", computed_after_s=3), _line(1, "60", "0", computed_after_s=5)]
    at = T0 + timedelta(minutes=1, seconds=3)
    # minute 1 closed before the photo but was folded 2 s after it: minute 0 judges it
    assert support_at(lines, at) == Decimal("49.05")
    assert support_at(lines, T0 + timedelta(minutes=1, seconds=5)) == Decimal(60)
    assert support_at(lines, T0 + timedelta(seconds=2)) is None, "minute 0 not folded yet"
    # ``line_support_causal: false`` — the pre-T4.98 read, by ``end_time`` alone
    assert support_at(lines, at, causal=False) == Decimal(60)


def test_a_newer_minute_without_a_line_hides_every_older_line() -> None:
    lines = [_line(0, "48", "1"), _line(1, None, None)]
    assert support_at(lines, T0 + timedelta(seconds=59)) == Decimal("48.98333333333333333333333333")
    assert support_at(lines, T0 + timedelta(minutes=1, seconds=10)) is None, (
        "flat now: the older line is not projected over it"
    )
    folded_late = [_line(0, "48", "1"), _line(1, None, None, computed_after_s=20)]
    assert support_at(folded_late, T0 + timedelta(minutes=1, seconds=10)) == Decimal(
        "49.16666666666666666666666667"
    )


def _streak(lines: list[SupportLine], photos: list[tuple[int, str]]) -> int | None:
    """The loop's fold over photos (``lab_bets._process_one``), seconds after T0."""
    streak: int | None = None
    for second, mcap in photos:
        at = T0 + timedelta(seconds=second)
        streak = next_streak(streak, below_support(Decimal(mcap), support_at(lines, at)))
    return streak


def test_a_stale_line_never_builds_a_streak_and_a_fresh_one_does() -> None:
    stale = [_line(0, "48", "0")]
    assert _streak(stale, [(200, "40"), (215, "40")]) is None
    fresh = [_line(0, "48", "0"), _line(3, "48", "0")]
    assert _streak(fresh, [(200, "40"), (215, "40")]) == 2
    flat_now = [_line(0, "48", "0"), _line(3, None, None)]
    assert _streak(flat_now, [(200, "40"), (215, "40")]) is None
    # below (line of 3 min) → unknown (4 min flat) → below (line of 5 min): one, no sale
    gap = [_line(3, "48", "0"), _line(4, None, None), _line(5, "48", "0")]
    assert _streak(gap, [(200, "40"), (250, "40"), (305, "40")]) == 1


def test_below_and_the_streak() -> None:
    assert below_support(Decimal(47), Decimal(48)) is True
    assert below_support(Decimal(48), Decimal(48)) is False
    assert below_support(None, Decimal(48)) is None
    assert below_support(Decimal(47), None) is None
    assert below_support(Decimal(47), Decimal(0)) is None
    assert next_streak(None, None) is None
    assert next_streak(3, None) is None
    assert next_streak(None, True) == 1
    assert next_streak(1, True) == 2
    assert next_streak(2, False) == 0
    assert next_streak(None, False) == 0
