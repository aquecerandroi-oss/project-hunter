"""``hunter_core.latency`` — the hop-lag math shared by T3.79's four new
histograms: clock skew never reads as zero, a missing timestamp never reads
as measured, and the reservoir never fabricates a quantile before it has a
reading.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_core.latency import (
    CLOCK_SKEW,
    MISSING_TIMESTAMP,
    LagMeasurement,
    LagTracker,
    classify_slo,
    measure_lag,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 9, 10, 12, 0, 0, tzinfo=UTC)


def test_measure_lag_plain_positive_delta() -> None:
    measurement = measure_lag(T0, T0 + timedelta(seconds=1.5))
    assert measurement == LagMeasurement(1.5, None)
    assert measurement.ok


def test_measure_lag_zero_delta_is_a_real_reading_not_a_reason() -> None:
    measurement = measure_lag(T0, T0)
    assert measurement == LagMeasurement(0.0, None)
    assert measurement.ok


def test_measure_lag_missing_start_is_named_never_zero() -> None:
    measurement = measure_lag(None, T0)
    assert measurement.value_s is None
    assert measurement.reason == MISSING_TIMESTAMP
    assert not measurement.ok


def test_measure_lag_missing_end_is_named_never_zero() -> None:
    measurement = measure_lag(T0, None)
    assert measurement.value_s is None
    assert measurement.reason == MISSING_TIMESTAMP
    assert not measurement.ok


def test_measure_lag_both_missing_is_still_missing_timestamp() -> None:
    measurement = measure_lag(None, None)
    assert measurement.value_s is None
    assert measurement.reason == MISSING_TIMESTAMP


def test_measure_lag_negative_delta_is_named_clock_skew_and_kept_raw() -> None:
    """The end happened (by our clocks) before the start -- never coerced to
    0.0, which would read as "instantaneous" instead of "a clock disagrees"."""
    measurement = measure_lag(T0, T0 - timedelta(milliseconds=300))
    assert measurement.value_s == pytest.approx(-0.3)
    assert measurement.reason == CLOCK_SKEW
    assert not measurement.ok


def test_measure_lag_large_negative_delta_is_still_named_not_clamped() -> None:
    """A skew far past the 2s tolerance is still ``clock_skew`` and still the
    raw value -- severity is a caller's concern, never this function's job to
    hide."""
    measurement = measure_lag(T0, T0 - timedelta(hours=1))
    assert measurement.value_s == pytest.approx(-3600.0)
    assert measurement.reason == CLOCK_SKEW


class TestLagTracker:
    def test_percentiles_are_none_before_any_reading(self) -> None:
        tracker = LagTracker()
        assert tracker.percentiles() == (None, None)

    def test_record_returns_false_and_skips_the_reservoir_for_missing_timestamp(self) -> None:
        tracker = LagTracker()
        recorded = tracker.record(measure_lag(None, T0))
        assert recorded is False
        assert tracker.percentiles() == (None, None)

    def test_record_returns_false_and_skips_the_reservoir_for_clock_skew(self) -> None:
        tracker = LagTracker()
        recorded = tracker.record(measure_lag(T0, T0 - timedelta(seconds=5)))
        assert recorded is False
        assert tracker.percentiles() == (None, None)

    def test_record_true_readings_enter_the_reservoir(self) -> None:
        tracker = LagTracker()
        for seconds in (1.0, 2.0, 3.0, 4.0, 5.0):
            assert tracker.record(measure_lag(T0, T0 + timedelta(seconds=seconds))) is True
        p50, p95 = tracker.percentiles()
        # Nearest-rank on 5 sorted samples [1..5]: p50 index int(0.5*4)=2 -> 3.0,
        # p95 index int(0.95*4)=3 -> 4.0 -- the same formula T3.74c already uses
        # for the decision hop (hunter_strategy_worker.metrics).
        assert p50 == pytest.approx(3.0)
        assert p95 == pytest.approx(4.0)

    def test_reservoir_is_bounded(self) -> None:
        tracker = LagTracker(window=5)
        for seconds in range(1, 11):
            tracker.record(measure_lag(T0, T0 + timedelta(seconds=float(seconds))))
        p50, p95 = tracker.percentiles()
        # The first five (1..5) were evicted; sorted survivors are [6,7,8,9,10].
        assert p50 == pytest.approx(8.0)
        assert p95 == pytest.approx(9.0)


class TestClassifySlo:
    def test_unknown_with_no_data(self) -> None:
        assert classify_slo(None, warn_s=1.0, critical_s=2.0) == "unknown"

    def test_ok_at_or_under_warn(self) -> None:
        assert classify_slo(1.0, warn_s=1.0, critical_s=2.0) == "ok"
        assert classify_slo(0.5, warn_s=1.0, critical_s=2.0) == "ok"

    def test_warn_past_warn_at_or_under_critical(self) -> None:
        assert classify_slo(1.5, warn_s=1.0, critical_s=2.0) == "warn"
        assert classify_slo(2.0, warn_s=1.0, critical_s=2.0) == "warn"

    def test_critical_past_critical(self) -> None:
        assert classify_slo(2.1, warn_s=1.0, critical_s=2.0) == "critical"
