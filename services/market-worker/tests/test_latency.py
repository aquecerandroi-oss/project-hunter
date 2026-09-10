"""T3.79 — ``hunter_market_worker.latency``: ingest/flush lag observation and
heartbeat fields. Pure in-memory reservoirs, no Redis/Postgres.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import align_open_time
from hunter_core.domain.types import utcnow
from hunter_market_worker import latency
from hunter_market_worker.latency import (
    _flush_lag,  # pyright: ignore[reportPrivateUsage]
    _ingest_lag,  # pyright: ignore[reportPrivateUsage]
    heartbeat_fields,
    observe_flush_lag,
    observe_ingest_lag,
)

from . import builders

pytestmark = pytest.mark.unit


def _minute_before(now: datetime) -> datetime:
    """A ``candle`` open_time whose ``close_time`` sits safely before ``now`` --
    ``align_open_time(now, M1)`` alone can land up to a minute in the future."""
    return align_open_time(now - timedelta(minutes=2), Timeframe.M1)


@pytest.fixture(autouse=True)
def _reset_trackers() -> None:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    """Module-level reservoirs (same design as the T3.74c decision-lag one) --
    reset between tests so one test's readings never leak into another's."""
    _ingest_lag._samples.clear()  # pyright: ignore[reportPrivateUsage]
    _flush_lag._samples.clear()  # pyright: ignore[reportPrivateUsage]


def test_observe_ingest_lag_records_a_plain_positive_reading() -> None:
    now = utcnow()
    observe_ingest_lag("trade", event_ts=now - timedelta(milliseconds=120), received_at=now)
    p50, p95 = _ingest_lag.percentiles()
    assert p50 == pytest.approx(0.12, abs=1e-3)
    assert p95 == pytest.approx(0.12, abs=1e-3)


def test_observe_ingest_lag_missing_event_ts_does_not_enter_the_reservoir() -> None:
    observe_ingest_lag("candle", event_ts=None, received_at=utcnow())
    assert _ingest_lag.percentiles() == (None, None)


def test_observe_ingest_lag_clock_skew_does_not_enter_the_reservoir() -> None:
    now = utcnow()
    observe_ingest_lag("trade", event_ts=now + timedelta(seconds=5), received_at=now)
    assert _ingest_lag.percentiles() == (None, None)


def test_observe_flush_lag_only_counts_final_candles() -> None:
    now = utcnow()
    open_time = _minute_before(now)
    forming = builders.candle("ETHUSDT", open_time, is_final=False)
    closed = builders.candle("BTCUSDT", open_time, is_final=True)
    observe_flush_lag([forming, closed], now=now)
    p50, _p95 = _flush_lag.percentiles()
    expected = (now - closed.close_time).total_seconds()
    assert p50 == pytest.approx(expected, abs=1e-3)


def test_observe_flush_lag_negative_delta_is_skipped_as_clock_skew() -> None:
    """``now`` earlier than ``close_time`` (a clock disagreement) must not
    enter the reservoir as a fabricated instantaneous flush."""
    closed = builders.candle("BTCUSDT", is_final=True)
    observe_flush_lag([closed], now=closed.close_time - timedelta(seconds=10))
    assert _flush_lag.percentiles() == (None, None)


def test_heartbeat_fields_are_empty_strings_before_any_reading() -> None:
    fields = heartbeat_fields()
    assert fields == {
        "ingest_lag_p50_s": "",
        "ingest_lag_p95_s": "",
        "flush_lag_p50_s": "",
        "flush_lag_p95_s": "",
    }


def test_heartbeat_fields_report_formatted_percentiles_once_measured() -> None:
    now = utcnow()
    observe_ingest_lag("trade", event_ts=now - timedelta(seconds=0.25), received_at=now)
    closed = builders.candle("BTCUSDT", is_final=True)
    observe_flush_lag([closed], now=closed.close_time + timedelta(seconds=0.8))
    fields = latency.heartbeat_fields()
    assert fields["ingest_lag_p50_s"] == "0.250"
    assert fields["ingest_lag_p95_s"] == "0.250"
    assert fields["flush_lag_p50_s"] == "0.800"
    assert fields["flush_lag_p95_s"] == "0.800"
