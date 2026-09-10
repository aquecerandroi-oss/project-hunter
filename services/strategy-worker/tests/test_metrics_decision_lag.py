"""``observe_decision_lag``/``decision_lag_percentiles`` — the heartbeat's own
p50/p95, no Prometheus server needed (T3.74c).

``hb:strategy:shadow`` is read directly with ``HGETALL`` on the VPS
(``notes-T3.74.md``, ``notes-T3.74b.md``); reading a quantile out of the
Prometheus histogram needs ``histogram_quantile`` against a running server,
which this worker does not have, so the heartbeat keeps its own small window.
"""

from __future__ import annotations

from typing import cast

import pytest

from hunter_strategy_worker.metrics import (
    _LAG_SAMPLE_WINDOW,  # pyright: ignore[reportPrivateUsage]
    _decision_lag_samples,  # pyright: ignore[reportPrivateUsage]
    decision_lag_percentiles,
    observe_decision_lag,
    shadow_decision_lag_seconds,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_samples() -> None:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    _decision_lag_samples.clear()


def test_no_samples_yet_is_none_none_not_zero_zero() -> None:
    """``None`` reads as "unknown"; ``0.0`` would lie and say "instantaneous"."""
    assert decision_lag_percentiles() == (None, None)


def test_one_sample_is_its_own_p50_and_p95() -> None:
    observe_decision_lag(3.5)
    assert decision_lag_percentiles() == (3.5, 3.5)


def test_percentiles_over_a_known_distribution() -> None:
    for value in range(1, 101):  # 1..100
        observe_decision_lag(float(value))
    p50, p95 = decision_lag_percentiles()
    assert p50 == pytest.approx(50.5, abs=1.0)
    assert p95 == pytest.approx(95.05, abs=1.0)


def test_the_reservoir_is_bounded_and_drops_the_oldest() -> None:
    for value in range(_LAG_SAMPLE_WINDOW + 10):
        observe_decision_lag(float(value))
    assert len(_decision_lag_samples) == _LAG_SAMPLE_WINDOW
    # The oldest 10 (0..9) must have fallen off the left of the deque.
    assert min(_decision_lag_samples) == 10.0


def test_it_also_feeds_the_prometheus_histogram() -> None:
    before = cast("float", shadow_decision_lag_seconds._sum.get())  # pyright: ignore[reportPrivateUsage]
    observe_decision_lag(2.5)
    after = cast("float", shadow_decision_lag_seconds._sum.get())  # pyright: ignore[reportPrivateUsage]
    assert after == pytest.approx(before + 2.5)
