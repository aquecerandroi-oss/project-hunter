"""Prometheus metrics of the execution-worker, on the shared registry.

The four the brief names, and the reason each exists rather than "for
completeness":

- ``hunter_execution_orders_total{outcome}`` — a wallet that stopped filling and
  a market that stopped printing look identical from outside unless the refusals
  are counted next to the fills;
- ``hunter_execution_protection_delay_seconds`` — how long a fired protection has
  been waiting for a book. This is the number that says a stop is *late*, which
  is the only failure of a paper wallet that costs real information;
- ``hunter_execution_mtm_age_seconds`` — how old the last point of the equity
  curve is. The daily reference, the peak and the kill switch all read that
  curve, so a stalled MTM silently freezes the risk state;
- ``hunter_execution_pending_degraded_total`` — every attempt that found nothing
  to fill against. It is the counter that must stay flat, and the alert when it
  does not.
"""

from __future__ import annotations

from datetime import datetime

from prometheus_client import Counter, Gauge, Histogram

from hunter_core.latency import LagTracker, measure_lag
from hunter_core.observability import registry

__all__ = [
    "admission_lag_percentiles",
    "bridge_candidates_total",
    "execution_admission_lag_seconds",
    "execution_avg_price_clock_skew_total",
    "execution_fill_lag_seconds",
    "execution_mark_quality",
    "execution_mtm_age_seconds",
    "execution_orders_total",
    "execution_pending_degraded_total",
    "execution_pending_requests",
    "execution_protection_delay_seconds",
    "execution_reservations_total",
    "fill_lag_percentiles",
    "observe_admission_lag",
    "observe_fill_lag",
]

execution_orders_total = Counter(
    "hunter_execution_orders_total",
    "Execution attempts, by kind (entry/exit) and outcome.",
    ["kind", "outcome"],
    registry=registry,
)
execution_protection_delay_seconds = Gauge(
    "hunter_execution_protection_delay_seconds",
    "Seconds since the oldest fired-but-unfilled protection went degraded.",
    registry=registry,
)
execution_mtm_age_seconds = Gauge(
    "hunter_execution_mtm_age_seconds",
    "Seconds since the last equity curve point was written.",
    registry=registry,
)
execution_mark_quality = Gauge(
    "hunter_execution_mark_quality",
    "Share of open positions marked with a live price on the last MTM pass "
    "(1 for an empty wallet). The companion of hunter_execution_mtm_age_seconds: "
    "that one says a point was written, this one says the prices in it were observed.",
    registry=registry,
)
execution_pending_degraded_total = Counter(
    "hunter_execution_pending_degraded_total",
    "Protection attempts that found no usable book, by reason.",
    ["reason"],
    registry=registry,
)
execution_reservations_total = Counter(
    "hunter_execution_reservations_total",
    "Reservation cycles closed by this worker, by terminal state.",
    ["state"],
    registry=registry,
)
bridge_candidates_total = Counter(
    "hunter_bridge_candidates_total",
    "Shadow signals screened by the autonomy bridge, by what happened to them.",
    ["outcome"],
    registry=registry,
)
"""T3.14 item 2. ``outcome`` is either a refusal reason (``purpose_mismatch``,
``live_forbidden``, ``research_only``, ``unknown_purpose``, ``cohort_not_live``,
``version_inactive``, ``beta_unavailable``,
``duplicate_position``, ``entry_window_closed``, ...), a deferral
(``spot_book_unavailable``), ``waiting`` for the candidates that lost the slot,
or ``approved``/``rejected`` for the one that was submitted. A bridge that
admits nothing because the beta job is down and a bridge that admits nothing
because nobody is emitting look identical without it."""

execution_pending_requests = Gauge(
    "hunter_execution_pending_requests",
    "Filed requests waiting for a decision, by readability.",
    ["readable"],
    registry=registry,
)

execution_avg_price_clock_skew_total = Counter(
    "hunter_execution_avg_price_clock_skew_total",
    "avgPrice references stamped ahead of the cycle's own now, by what was done "
    "with them (tolerated inside the declared skew, refused past it).",
    ["outcome"],
    registry=registry,
)
"""T3.29b. ``tolerated`` counts the ordering the cycle creates by design (``now``
is read before the snapshot is assembled) and must sit at roughly one per refresh
window per market; ``refused`` counts a reference genuinely ahead of us, which is
a clock incident and never normal. Without the counter the tolerance would be a
silent relaxation of RISK_ENGINE.md §7's "a stamp in the future is unavailable"."""

# T3.79 — the two execution-worker hops of the end-to-end latency budget.
# ``admission``: a shadow signal's own ``agent_signals.emitted_at`` to this
# process persisting the admission decision (``bridge.py``'s one slot per
# cycle) -- the autonomy path only, since a manual request has no signal to
# time against. ``fill``: an approved proposal's ``trade_proposals.decided_at``
# to the instant its paper fill actually applied (``entry.py``), for every
# origin. Same reservoir-plus-histogram design as
# ``hunter_strategy_worker.metrics``'s decision lag (T3.74c) and
# ``hunter_market_worker.latency``'s ingest/flush hops -- a reading only
# reaches the histogram when ``hunter_core.latency.measure_lag`` found no
# clock-skew/missing-timestamp reason; the *_anomalies_total counters are
# where those go instead, by reason, never silently dropped.
execution_admission_lag_seconds = Histogram(
    "hunter_execution_admission_lag_seconds",
    "Shadow signal emitted -> admission decision persisted.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=registry,
)
execution_admission_lag_anomalies_total = Counter(
    "hunter_execution_admission_lag_anomalies_total",
    "Admission-lag readings that could not enter execution_admission_lag_seconds, "
    "by reason (missing_timestamp/clock_skew).",
    ["reason"],
    registry=registry,
)
execution_fill_lag_seconds = Histogram(
    "hunter_execution_fill_lag_seconds",
    "Admission decision persisted -> paper fill applied.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=registry,
)
execution_fill_lag_anomalies_total = Counter(
    "hunter_execution_fill_lag_anomalies_total",
    "Fill-lag readings that could not enter execution_fill_lag_seconds, by "
    "reason (missing_timestamp/clock_skew).",
    ["reason"],
    registry=registry,
)

_admission_lag = LagTracker()
_fill_lag = LagTracker()


def observe_admission_lag(*, emitted_at: datetime | None, decided_at: datetime) -> None:
    measurement = measure_lag(emitted_at, decided_at)
    if _admission_lag.record(measurement):
        execution_admission_lag_seconds.observe(measurement.value_s)  # type: ignore[arg-type]
    else:
        execution_admission_lag_anomalies_total.labels(reason=measurement.reason).inc()


def observe_fill_lag(*, decided_at: datetime | None, filled_at: datetime) -> None:
    measurement = measure_lag(decided_at, filled_at)
    if _fill_lag.record(measurement):
        execution_fill_lag_seconds.observe(measurement.value_s)  # type: ignore[arg-type]
    else:
        execution_fill_lag_anomalies_total.labels(reason=measurement.reason).inc()


def admission_lag_percentiles() -> tuple[float | None, float | None]:
    return _admission_lag.percentiles()


def fill_lag_percentiles() -> tuple[float | None, float | None]:
    return _fill_lag.percentiles()
