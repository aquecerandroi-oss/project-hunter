"""T3.79 — the execution-worker's two hops: signal emitted -> admission
decision persisted, and decision persisted -> paper fill applied. Pure
in-memory reservoirs, no Postgres/Redis.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_core.domain.types import utcnow
from hunter_execution_worker import metrics

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_trackers() -> None:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    metrics._admission_lag._samples.clear()  # pyright: ignore[reportPrivateUsage]
    metrics._fill_lag._samples.clear()  # pyright: ignore[reportPrivateUsage]


def test_observe_admission_lag_records_a_plain_positive_reading() -> None:
    now = utcnow()
    metrics.observe_admission_lag(emitted_at=now - timedelta(seconds=0.8), decided_at=now)
    p50, p95 = metrics.admission_lag_percentiles()
    assert p50 == pytest.approx(0.8, abs=1e-3)
    assert p95 == pytest.approx(0.8, abs=1e-3)


def test_observe_admission_lag_missing_emitted_at_does_not_enter_the_reservoir() -> None:
    metrics.observe_admission_lag(emitted_at=None, decided_at=utcnow())
    assert metrics.admission_lag_percentiles() == (None, None)


def test_observe_admission_lag_clock_skew_does_not_enter_the_reservoir() -> None:
    now = utcnow()
    metrics.observe_admission_lag(emitted_at=now + timedelta(seconds=3), decided_at=now)
    assert metrics.admission_lag_percentiles() == (None, None)


def test_observe_fill_lag_records_a_plain_positive_reading() -> None:
    now = utcnow()
    metrics.observe_fill_lag(decided_at=now - timedelta(seconds=1.2), filled_at=now)
    p50, p95 = metrics.fill_lag_percentiles()
    assert p50 == pytest.approx(1.2, abs=1e-3)
    assert p95 == pytest.approx(1.2, abs=1e-3)


def test_observe_fill_lag_missing_decided_at_does_not_enter_the_reservoir() -> None:
    metrics.observe_fill_lag(decided_at=None, filled_at=utcnow())
    assert metrics.fill_lag_percentiles() == (None, None)


def test_observe_fill_lag_clock_skew_does_not_enter_the_reservoir() -> None:
    now = utcnow()
    metrics.observe_fill_lag(decided_at=now + timedelta(seconds=2), filled_at=now)
    assert metrics.fill_lag_percentiles() == (None, None)


def test_admission_and_fill_reservoirs_are_independent() -> None:
    now = utcnow()
    metrics.observe_admission_lag(emitted_at=now - timedelta(seconds=1), decided_at=now)
    assert metrics.fill_lag_percentiles() == (None, None)
