"""T4.61a — EXP-M13's fill on the 15-second lane, without a database: the
fold of one mint's stored photos into a ``GateRow``'s three
``recent_drawdown_*`` fields, and what the pure gate then says.

The series is TAXCOIN-like (R41, 16/09 21:31 BRT): the curve loses 24 of
29,6 real SOL, and the question is only *when* the peak was — 67 s ago
passes the 60 s gate window (KB-0118's best cell, the old peak), 40 s ago is
refused ``recent_drawdown``; a stale newest photo, one photo, no photo and a
photo received after the instant are each a named unknown, never a clean row.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_indicators.meme.drawdown import NO_OBSERVATION, STALE, TOO_FEW_POINTS, ReservePoint
from hunter_indicators.meme.rules import EntryFeatures, EntryGate
from hunter_indicators.meme.rules_criteria import drawdown_refusals
from hunter_meme_worker.lab_repo_drawdown import drawdown_of, fill_recent_drawdown
from hunter_meme_worker.proposals import GateRow

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 9, 18, 15, 0, tzinfo=UTC)
MINT = "TAXCOINxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
OFF = EntryGate(
    key="teste_porta",
    version=1,
    description="fixture",
    min_age_s=30,
    max_age_s=300,
    min_progress_pct=Decimal(5),
    max_progress_pct=Decimal(50),
    max_participation_pct=Decimal(1),
    require_creator_not_net_seller=False,
)
GATE = replace(OFF, max_recent_drawdown_pct=Decimal("0.50"))
"""``flow_v2/9``'s guard: X = 0,50, N = 60 s, gap 30 s (the defaults)."""


def _point(seconds_before: int, sol: str, *, received_after_s: int = 0) -> ReservePoint:
    observed = AS_OF - timedelta(seconds=seconds_before)
    return ReservePoint(
        observed_at=observed,
        received_at=observed + timedelta(seconds=received_after_s),
        real_sol=Decimal(sol),
    )


def _taxcoin(peak_age_s: int) -> list[ReservePoint]:
    """29,6 real SOL at the peak, 5,3 from then on: a fall of 82 %."""
    return [
        _point(peak_age_s + 30, "12.0"),
        _point(peak_age_s, "29.6"),
        _point(peak_age_s - 15, "5.3"),
        _point(12, "5.3"),
    ]


def _row(**overrides: Any) -> GateRow:
    base: dict[str, Any] = {
        "mint": MINT,
        "end_time": AS_OF,
        "created_at": AS_OF - timedelta(seconds=150),
        "curve_progress_pct": Decimal("0.16"),
        "progress_reason": None,
        "mcap_sol": Decimal("35"),
        "creator_sold": False,
        "curve_volume_1m_sol": Decimal("20"),
        "completed_at": None,
        "migrated_at": None,
        "snapshot": None,
        "series": "meme_features_15s_v1",
    }
    base.update(overrides)
    return GateRow(**base)


def _features(row: GateRow) -> EntryFeatures:
    return EntryFeatures(
        mint=row.mint,
        age_s=150,
        progress_pct=Decimal(16),
        creator_net_seller=False,
        curve_volume_1m_sol=Decimal(20),
        intended_size_sol=Decimal("0.05"),
        recent_drawdown_pct=row.recent_drawdown_pct,
        recent_drawdown_peak_age_s=row.recent_drawdown_peak_age_s,
        recent_drawdown_reason=row.recent_drawdown_reason,
    )


def test_a_fall_of_82_pct_from_a_peak_67_s_old_is_carried_and_not_refused() -> None:
    """KB-0118's best cell: dd > 50 % with the peak older than the window."""
    (row,) = fill_recent_drawdown([_row()], {MINT: _taxcoin(67)})
    assert row.recent_drawdown_pct == Decimal("0.820946")
    assert row.recent_drawdown_peak_age_s == Decimal("67.000")
    assert row.recent_drawdown_reason is None
    assert drawdown_refusals(_features(row), GATE) == []


def test_the_same_fall_from_a_peak_40_s_old_is_refused_recent_drawdown() -> None:
    (row,) = fill_recent_drawdown([_row()], {MINT: _taxcoin(40)})
    assert row.recent_drawdown_pct == Decimal("0.820946")
    assert row.recent_drawdown_peak_age_s == Decimal("40.000")
    assert drawdown_refusals(_features(row), GATE) == ["recent_drawdown"]


def test_a_fall_under_the_ceiling_passes() -> None:
    points = [_point(40, "10.0"), _point(25, "8.0"), _point(10, "6.0")]
    fold = drawdown_of(points, as_of=AS_OF)
    assert (fold.drawdown_pct, fold.peak_age_s, fold.reason) == (
        Decimal("0.400000"),
        Decimal("40.000"),
        None,
    )
    (row,) = fill_recent_drawdown([_row()], {MINT: points})
    assert drawdown_refusals(_features(row), GATE) == []


def test_a_stale_newest_photo_is_unknown_and_refused_by_name() -> None:
    """The newest photo is 45 s old (> the 30 s gap): fail closed."""
    points = [_point(75, "29.6"), _point(45, "5.3")]
    fold = drawdown_of(points, as_of=AS_OF)
    assert fold == (None, None, STALE)
    (row,) = fill_recent_drawdown([_row()], {MINT: points})
    assert row.recent_drawdown_reason == STALE
    assert drawdown_refusals(_features(row), GATE) == ["recent_drawdown_unknown"]


def test_one_photo_is_too_few_and_none_is_no_observation() -> None:
    assert drawdown_of([_point(12, "5.3")], as_of=AS_OF) == (None, None, TOO_FEW_POINTS)
    assert drawdown_of([], as_of=AS_OF) == (None, None, NO_OBSERVATION)
    (absent,) = fill_recent_drawdown([_row()], {})
    assert absent.recent_drawdown_reason == NO_OBSERVATION
    assert drawdown_refusals(_features(absent), GATE) == ["recent_drawdown_unknown"]


def test_a_photo_received_after_the_instant_is_not_an_input_of_it() -> None:
    """The row of 40 s ago must not see the fall the chain delivered later:
    without the late photo the two known points show no fall at all."""
    points = [_point(60, "29.6"), _point(30, "29.6"), _point(12, "5.3", received_after_s=20)]
    fold = drawdown_of(points, as_of=AS_OF)
    assert fold.reason is None and fold.drawdown_pct == Decimal("0.000000")
    later = drawdown_of(points, as_of=AS_OF + timedelta(seconds=10))
    assert later.drawdown_pct == Decimal("0.820946"), "once received, the fall is an input"


def test_a_photo_older_than_the_lookback_is_not_the_peak() -> None:
    """The 120 s horizon: a peak at 130 s is outside, the one at 100 s is in."""
    points = [_point(130, "100"), _point(100, "20"), _point(10, "10")]
    fold = drawdown_of(points, as_of=AS_OF)
    assert (fold.drawdown_pct, fold.peak_age_s) == (Decimal("0.500000"), Decimal("100.000"))
    assert drawdown_refusals(_features(_row(**_fields(fold))), GATE) == [], (
        "a 100 s old peak is older than the gate's 60 s window"
    )


def test_a_set_without_the_guard_ignores_the_fill() -> None:
    (row,) = fill_recent_drawdown([_row()], {MINT: _taxcoin(40)})
    assert drawdown_refusals(_features(row), OFF) == []


def _fields(fold: Any) -> dict[str, Any]:
    return {
        "recent_drawdown_pct": fold.drawdown_pct,
        "recent_drawdown_peak_age_s": fold.peak_age_s,
        "recent_drawdown_reason": fold.reason,
    }
