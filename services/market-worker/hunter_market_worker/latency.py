"""T3.79 — the market-worker's two hops: exchange event -> our receive
(``ingest``), and candle close -> durably queued for the outbox (``flush``).

Split out of ``ingest.py``/``persist.py`` rather than inlined in either: both
files are read from here, and neither has room left under the 350-line budget
for the reservoir + Prometheus wiring this needs (``check_file_size.py``).

Kept in-process, module-level state, exactly like
``hunter_strategy_worker.metrics``'s decision-lag reservoir (T3.74c): one
:class:`~hunter_core.latency.LagTracker` per hop, read back by
``heartbeat.py`` with plain ``HGETALL`` -- no Prometheus server needed to take
a p50/p95 off this process's own recent history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hunter_core.latency import LagTracker, measure_lag
from hunter_core.observability import (
    candle_flush_lag_anomalies_total,
    candle_flush_lag_seconds,
    market_ingest_lag_anomalies_total,
    market_ingest_lag_seconds,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from hunter_core.domain.market import NormalizedCandle

__all__ = ["heartbeat_fields", "observe_flush_lag", "observe_ingest_lag"]

_ingest_lag = LagTracker()
_flush_lag = LagTracker()


def observe_ingest_lag(kind: str, *, event_ts: datetime | None, received_at: datetime) -> None:
    """One trade/candle: ``event_ts`` (the exchange's own push/trade time) to
    ``received_at`` (this process's parse-time ``utcnow()``, already stamped
    on every ``Normalized*`` model by ``_ReceivedAtMixin``)."""
    measurement = measure_lag(event_ts, received_at)
    if _ingest_lag.record(measurement):
        market_ingest_lag_seconds.labels(kind=kind).observe(measurement.value_s)  # type: ignore[arg-type]
    else:
        market_ingest_lag_anomalies_total.labels(kind=kind, reason=measurement.reason).inc()


def observe_flush_lag(candles: Iterable[NormalizedCandle], *, now: datetime) -> None:
    """Every **final** candle in ``candles``: its own ``close_time`` (the bar
    boundary, not when anyone observed it) to ``now`` -- the instant this
    process finished the flush transaction that queued it for the outbox
    (``persist.py``'s ``drain_loop``, right after ``flush_batch`` commits).

    A non-final candle (still forming) has no closed bar to measure and is
    skipped; a duplicate redelivery of an already-persisted minute is counted
    again here (the caller does not know which candles the ``ON CONFLICT DO
    NOTHING`` actually inserted) -- a known, accepted simplification for a
    diagnostic gauge, not a correctness path (``notes-T3.79.md``).
    """
    for candle in candles:
        if not candle.is_final:
            continue
        measurement = measure_lag(candle.close_time, now)
        if _flush_lag.record(measurement):
            candle_flush_lag_seconds.observe(measurement.value_s)  # type: ignore[arg-type]
        else:
            candle_flush_lag_anomalies_total.labels(reason=measurement.reason).inc()


def heartbeat_fields() -> dict[str, str]:
    """The four fields merged into ``hb:market:{exchange}`` (``heartbeat.py``)."""
    ingest_p50, ingest_p95 = _ingest_lag.percentiles()
    flush_p50, flush_p95 = _flush_lag.percentiles()
    return {
        "ingest_lag_p50_s": "" if ingest_p50 is None else f"{ingest_p50:.3f}",
        "ingest_lag_p95_s": "" if ingest_p95 is None else f"{ingest_p95:.3f}",
        "flush_lag_p50_s": "" if flush_p50 is None else f"{flush_p50:.3f}",
        "flush_lag_p95_s": "" if flush_p95 is None else f"{flush_p95:.3f}",
    }
