"""``hunter_indicators.meme.drawdown`` (T4.52b-2) — EXP-M13's "do not buy
after the fall" over the real SOL, with KB-0118's own cases: the TAXCOIN fill
(peak 67 s old, −82 %) is **not** cut by ``N = 60 s``; the same fall with a
40 s-old peak is; a photo older than 30 s is unknown; and the gate with the
key off reads exactly as it did."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_indicators.meme.drawdown import (
    DEFAULT_MAX_GAP_S,
    DEFAULT_WINDOW_S,
    DRAWDOWN_DEFINITION,
    NO_OBSERVATION,
    STALE,
    PeakDeque,
    ReservePoint,
    recent_drawdown,
)
from hunter_indicators.meme.rules import EntryFeatures, EntryGate, evaluate_entry
from hunter_indicators.meme.rules_criteria import drawdown_refusals

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 17, 0, 31, 28, tzinfo=UTC)
"""TAXCOIN's first real order (R41, 21:31:28 BRT)."""
PEAK = Decimal("29.638")
NOW = Decimal("5.252")


def _pt(age_s: float, real_sol: str | Decimal, *, lag_s: float = 0.5) -> ReservePoint:
    observed = T0 - timedelta(seconds=age_s)
    return ReservePoint(observed, observed + timedelta(seconds=lag_s), Decimal(real_sol))


TAXCOIN = [_pt(67, PEAK), _pt(55, "6"), _pt(20, "5.5"), _pt(3, NOW)]
"""The peak 67 s before the order, the curve already at 6 SOL 55 s before it."""


def test_the_feature_is_registered_with_its_frozen_windows() -> None:
    assert DRAWDOWN_DEFINITION.key == "recent_drawdown_pct"
    assert DRAWDOWN_DEFINITION.version == 1
    assert DRAWDOWN_DEFINITION.params == {"window_s": 60, "max_gap_s": 30}
    assert DEFAULT_WINDOW_S == 60 and DEFAULT_MAX_GAP_S == 30


def test_taxcoin_peak_67_s_old_is_not_a_recent_drawdown_with_a_60_s_window() -> None:
    dd, peak_age, reason = recent_drawdown(TAXCOIN, as_of=T0, window_s=60, max_gap_s=30)
    assert reason is None
    assert peak_age == Decimal("55.000"), "the peak inside the window is the 6 SOL photo"
    assert dd == (Decimal(1) - NOW / Decimal(6)).quantize(Decimal("0.000001"))
    assert dd == Decimal("0.124667")


def test_taxcoin_is_cut_by_a_120_s_window_as_kb_0118_measured() -> None:
    dd, peak_age, reason = recent_drawdown(TAXCOIN, as_of=T0, window_s=120, max_gap_s=30)
    assert reason is None and peak_age == Decimal("67.000")
    assert dd == Decimal("0.822795"), "1 − 5,252 / 29,638"


def test_the_same_fall_with_a_40_s_old_peak_is_a_recent_drawdown() -> None:
    points = [_pt(40, PEAK), _pt(20, "12"), _pt(3, NOW)]
    dd, peak_age, reason = recent_drawdown(points, as_of=T0)
    assert (dd, peak_age, reason) == (Decimal("0.822795"), Decimal("40.000"), None)


def test_a_newest_observation_older_than_30_s_is_unknown_not_zero() -> None:
    stale = [_pt(70, PEAK), _pt(31, NOW)]
    assert recent_drawdown(stale, as_of=T0) == (None, None, STALE)
    fresh = [_pt(70, PEAK), _pt(30, NOW)]
    assert recent_drawdown(fresh, as_of=T0).reason is None, "30 s is the bound, inclusive"
    assert recent_drawdown([], as_of=T0) == (None, None, NO_OBSERVATION)


def test_a_point_received_after_as_of_does_not_count() -> None:
    """Look-ahead: a peak stamped inside the window but received one second
    after the decision changes nothing — the fold reads ``received_at``."""
    late_peak = replace(_pt(10, "100"), received_at=T0 + timedelta(seconds=1))
    assert recent_drawdown([*TAXCOIN, late_peak], as_of=T0) == recent_drawdown(TAXCOIN, as_of=T0)
    only_late = [replace(_pt(3, NOW), received_at=T0 + timedelta(milliseconds=1))]
    assert recent_drawdown(only_late, as_of=T0) == (None, None, NO_OBSERVATION)


def test_a_rise_is_zero_drawdown_and_an_empty_peak_is_zero_too() -> None:
    rising = [_pt(50, "1"), _pt(10, "2"), _pt(1, "3")]
    dd, peak_age, reason = recent_drawdown(rising, as_of=T0)
    assert (dd, peak_age, reason) == (Decimal("0.000000"), Decimal("1.000"), None)
    empty = [_pt(50, "0"), _pt(1, "0")]
    assert recent_drawdown(empty, as_of=T0).drawdown_pct == Decimal("0.000000")


def _series(n: int) -> list[ReservePoint]:
    """A saw-tooth: up for 7 points, down for 5, one point per second."""
    values: list[Decimal] = []
    v = Decimal(10)
    for i in range(n):
        v = v + 1 if i % 12 < 7 else v - Decimal("1.5")
        values.append(v)
    return [_pt(n - i, values[i]) for i in range(n)]


def test_the_monotonic_deque_gives_the_same_answer_as_the_full_fold_at_every_instant() -> None:
    points = _series(200)
    deque_ = PeakDeque()
    for i, point in enumerate(points):
        deque_.push(point)
        as_of = point.received_at
        deque_.expire(as_of - timedelta(seconds=60))  # the owner's retention
        expected = recent_drawdown(points[: i + 1], as_of=as_of, window_s=60, max_gap_s=30)
        got = recent_drawdown(deque_, as_of=as_of, window_s=60, max_gap_s=30)
        assert got == expected, f"point {i}: {got} != {expected}"
        assert len(deque_) <= 61, "the deque never holds more than the window's points"
        assert recent_drawdown(deque_, as_of=as_of, window_s=30) == recent_drawdown(
            points[: i + 1], as_of=as_of, window_s=30
        ), "a narrower window reads the same deque without consuming it"


def test_the_deque_refuses_an_instant_before_its_newest_receipt() -> None:
    deque_ = PeakDeque()
    for point in TAXCOIN:
        deque_.push(point)
    with pytest.raises(ValueError, match="received after as_of"):
        recent_drawdown(deque_, as_of=T0 - timedelta(seconds=10))


def test_an_out_of_order_point_keeps_the_deque_exact() -> None:
    points = [_pt(50, "10"), _pt(30, "8"), _pt(10, "7"), _pt(40, "9"), _pt(20, "12"), _pt(45, "11")]
    deque_ = PeakDeque()
    for point in points:
        deque_.push(point)
    assert recent_drawdown(deque_, as_of=T0) == recent_drawdown(points, as_of=T0)
    assert deque_.peak is not None and deque_.peak.real_sol == Decimal(12)


# -- the gate ---------------------------------------------------------------

GATE = EntryGate(
    key="teste_porta",
    version=1,
    description="fixture",
    min_age_s=30,
    max_age_s=300,
    min_progress_pct=Decimal(5),
    max_progress_pct=Decimal(50),
    max_participation_pct=Decimal(1),
)
GUARDED = replace(GATE, max_recent_drawdown_pct=Decimal("0.50"))
FEATURES = EntryFeatures(
    mint="TAXCOIN",
    age_s=120,
    progress_pct=Decimal(20),
    creator_net_seller=False,
    curve_volume_1m_sol=Decimal(10),
    intended_size_sol=Decimal("0.05"),
    is_mayhem=False,
)


def test_a_gate_without_the_key_reads_and_judges_exactly_as_before() -> None:
    assert "max_recent_drawdown_pct" not in GATE.as_parameters()
    assert "recent_drawdown_window_s" not in GATE.as_parameters()
    assert evaluate_entry(FEATURES, GATE).allowed, "no feature, no criterion, no refusal"
    assert drawdown_refusals(replace(FEATURES, recent_drawdown_pct=Decimal("0.9")), GATE) == []


def test_the_guarded_gate_names_its_three_parameters() -> None:
    params = GUARDED.as_parameters()
    assert params["max_recent_drawdown_pct"] == "0.50"
    assert params["recent_drawdown_window_s"] == "60"
    assert params["recent_drawdown_max_gap_s"] == "30"


def test_the_guarded_gate_refuses_the_fresh_fall_and_the_unknown_by_name() -> None:
    fresh_fall = replace(
        FEATURES,
        recent_drawdown_pct=Decimal("0.822795"),
        recent_drawdown_peak_age_s=Decimal("40.000"),
    )
    assert evaluate_entry(fresh_fall, GUARDED).refusals == ("recent_drawdown",)
    unknown = replace(FEATURES, recent_drawdown_reason=STALE)
    assert evaluate_entry(unknown, GUARDED).refusals == ("recent_drawdown_unknown",)


def test_the_guarded_gate_lets_the_old_fall_and_the_exact_ceiling_through() -> None:
    old_fall = replace(
        FEATURES,
        recent_drawdown_pct=Decimal("0.822795"),
        recent_drawdown_peak_age_s=Decimal("67.000"),
    )
    assert evaluate_entry(old_fall, GUARDED).allowed, "a peak older than the window is a reset"
    at_ceiling = replace(
        FEATURES, recent_drawdown_pct=Decimal("0.50"), recent_drawdown_peak_age_s=Decimal(10)
    )
    assert evaluate_entry(at_ceiling, GUARDED).allowed, "atual / pico < X is strict (EXP-M13)"
    taxcoin_60 = replace(
        FEATURES, recent_drawdown_pct=Decimal("0.124667"), recent_drawdown_peak_age_s=Decimal(55)
    )
    assert evaluate_entry(taxcoin_60, GUARDED).allowed


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"max_recent_drawdown_pct": Decimal("1.5")}, "fraction in"),
        ({"max_recent_drawdown_pct": Decimal(0)}, "fraction in"),
        ({"recent_drawdown_window_s": 0}, "window_s must be positive"),
        ({"recent_drawdown_max_gap_s": -1}, "max_gap_s must be positive"),
    ],
)
def test_an_impossible_guard_refuses_to_exist(patch: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        replace(GATE, **patch)
