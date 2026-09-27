"""EXP-M26's coverage guard (design §1.6) — pure, no database.

The four scenarios the design names: a window observed end to end; a coin
younger than 16 min, observed from its birth (truncated, counted apart); five
photos in the last four minutes that pass ``MIN_POINTS`` while eleven minutes
went unobserved; and a photo received after ``T`` that must not rescue a hole.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.lines import LinePoint
from hunter_meme_worker.lab_opportunities_coverage import (
    COVERAGE_MAX_GAP_S,
    COVERAGE_VERSION,
    coverage_of,
    unread_coverage,
)

pytestmark = pytest.mark.unit

T = datetime(2026, 10, 5, 12, 30, tzinfo=UTC)
OLD = T - timedelta(hours=1)
"""A coin created long before the window: its effective start is ``T − 16 min``."""


def _point(seconds_before: int, *, late_by: int = 0, mcap: str = "36") -> LinePoint:
    at = T - timedelta(seconds=seconds_before)
    return LinePoint(
        observed_at=at, received_at=at + timedelta(seconds=late_by), mcap_sol=Decimal(mcap)
    )


def _every(step_s: int, *, since_s: int = 16 * 60 - 10) -> list[LinePoint]:
    return [_point(s) for s in range(since_s, -1, -step_s)]


def test_a_window_photographed_every_minute_is_covered() -> None:
    status, detail = coverage_of(_every(60), end_time=T, created_at=OLD)
    assert status == "covered"
    assert detail["version"] == COVERAGE_VERSION
    assert detail["params"]["max_gap_s"] == COVERAGE_MAX_GAP_S == 150
    assert detail["truncated_at_birth"] is False
    assert detail["points"] == 16
    assert detail["max_gap_s"] == "60.0"


def test_a_coin_younger_than_the_window_is_covered_from_birth_not_complete() -> None:
    born = T - timedelta(seconds=930)
    points = [_point(s) for s in range(900, -1, -60)]
    status, detail = coverage_of(points, end_time=T, created_at=born)
    assert status == "covered_from_birth"
    assert detail["truncated_at_birth"] is True
    assert detail["effective_start"] == born.isoformat()
    assert detail["lead_s"] == "30.0"


def test_five_photos_in_the_last_four_minutes_are_a_gap_not_a_line() -> None:
    points = [_point(s) for s in (240, 180, 120, 60, 0)]
    status, detail = coverage_of(points, end_time=T, created_at=OLD)
    assert status == "gap"
    assert detail["points"] == 5
    assert detail["lead_s"] == str(Decimal(str(16 * 60 - 240.0)))


@pytest.mark.parametrize(
    ("missing", "why"),
    [
        (range(16 * 60 - 10, 16 * 60 - 200, -1), "lead"),
        (range(170, -1, -1), "tail"),
        (range(500, 330, -1), "gap"),
    ],
)
def test_a_hole_longer_than_150_s_anywhere_is_a_gap(missing: range, why: str) -> None:
    holes = set(missing)
    points = [p for p in _every(30) if int((T - p.observed_at).total_seconds()) not in holes]
    status, _ = coverage_of(points, end_time=T, created_at=OLD)
    assert status == "gap", why


def test_a_photo_received_after_t_does_not_fill_the_hole() -> None:
    """``lines.usable_points``' own rule: it had not reached us at ``T``."""
    points = [p for p in _every(30) if (T - p.observed_at).total_seconds() > 150]
    status, _ = coverage_of([*points, _point(40, late_by=41)], end_time=T, created_at=OLD)
    assert status == "gap"
    status, _ = coverage_of([*points, _point(40)], end_time=T, created_at=OLD)
    assert status == "covered", "the same photo received in time closes it"


def test_a_photo_without_a_positive_market_cap_is_not_a_point() -> None:
    points = [_point(s, mcap="0") if s < 200 else _point(s) for s in range(950, -1, -60)]
    status, _ = coverage_of(points, end_time=T, created_at=OLD)
    assert status == "gap"


def test_no_usable_point_is_a_gap_and_an_unread_is_named_apart() -> None:
    assert coverage_of([], end_time=T, created_at=OLD)[0] == "gap"
    status, detail = unread_coverage("line_points_read_failed")
    assert status == "unread" and detail["error"] == "line_points_read_failed"
