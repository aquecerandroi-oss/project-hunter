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

from prometheus_client import Counter, Gauge

from hunter_core.observability import registry

__all__ = [
    "execution_mtm_age_seconds",
    "execution_orders_total",
    "execution_pending_degraded_total",
    "execution_pending_requests",
    "execution_protection_delay_seconds",
    "execution_reservations_total",
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
execution_pending_requests = Gauge(
    "hunter_execution_pending_requests",
    "Filed requests waiting for a decision, by readability.",
    ["readable"],
    registry=registry,
)
