"""Generic hop-latency math shared by every worker on the market -> paper-fill
chain (T3.79) -- one clock-skew rule, one bounded p50/p95 reservoir, one SLO
classifier, so the four new hops (market-worker ingest/flush, execution-worker
admission/fill) and the existing decision hop (T3.74c,
``hunter_strategy_worker.metrics``, not touched by this module) all answer
"how long did this take" the same way.

**Never zero a negative lag.** Two clocks a hop compares are never exactly the
same clock: the exchange's push time, this process's own ``utcnow()``, and
Postgres's ``now()`` can each be a few milliseconds off in either direction.
A naive ``max(0, end - start)`` would print a perfectly healthy hop as
"instantaneous", which is indistinguishable from a hop that is broken in the
*other* direction (an event whose consumer never actually saw it). So a
negative delta is kept, never clamped, and labelled ``clock_skew`` instead of
folded into the reservoir a p50/p95 answers "how long does this hop normally
take" from — an unlabelled skewed reading would drag that number down.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

CLOCK_SKEW_TOLERANCE_S = 2.0
"""Mirrors ``hunter_api.services.market_status.CLOCK_SKEW_TOLERANCE_S`` --
same value (every producer and this API run on the same NTP-synced hosts),
independently owned copy: ``hunter_core`` may not import from ``hunter_api``
(wrong dependency direction), and the two modules already keep sibling copies
of this constant for the same reason (see that module's own docstring).
Purely documentary here -- :func:`measure_lag` does not change behaviour
inside the tolerance, it only *names* a negative reading as skew whether it is
one millisecond or one hour past zero (see the module docstring)."""

MISSING_TIMESTAMP = "missing_timestamp"
CLOCK_SKEW = "clock_skew"

LagReason = Literal["missing_timestamp", "clock_skew"]


@dataclass(frozen=True, slots=True)
class LagMeasurement:
    """One hop's answer: a number, or a named reason there is none."""

    value_s: float | None
    reason: LagReason | None

    @property
    def ok(self) -> bool:
        """A reading fit to enter a quantile — present and not skew-tagged."""
        return self.value_s is not None and self.reason is None


def measure_lag(start: datetime | None, end: datetime | None) -> LagMeasurement:
    """``end - start`` in seconds, or a named reason there is nothing to report.

    ``start``/``end`` missing (a hop with no timestamp on one side -- the very
    gap T3.79's measurement phase exists to name) -> ``(None, "missing_timestamp")``.
    ``end`` before ``start`` by the clocks available -> the raw (negative) delta,
    ``reason="clock_skew"`` -- never coerced to zero (module docstring).
    Otherwise the plain non-negative delta, ``reason=None``.
    """
    if start is None or end is None:
        return LagMeasurement(None, MISSING_TIMESTAMP)
    delta = (end - start).total_seconds()
    if delta < 0:
        return LagMeasurement(delta, CLOCK_SKEW)
    return LagMeasurement(delta, None)


_WINDOW = 500
"""Same reservoir size ``hunter_strategy_worker.metrics`` chose for the decision
hop (T3.74c): enough to smooth a burst, small enough that a process holds it
for free and a restart losing it costs nothing a few minutes can't rebuild."""


class LagTracker:
    """Bounded p50/p95 reservoir, read with plain ``HGETALL`` -- no Prometheus
    server needed to take a quantile off a histogram (T3.74c's own rationale,
    reused verbatim: see ``hunter_strategy_worker.metrics`` module docstring).

    Only :attr:`LagMeasurement.ok` readings enter the reservoir: a missing
    timestamp or a skewed clock is not "how long this hop took", and must not
    silently pull the p50/p95 toward zero.
    """

    def __init__(self, window: int = _WINDOW) -> None:
        self._samples: deque[float] = deque(maxlen=window)

    def record(self, measurement: LagMeasurement) -> bool:
        """Add ``measurement`` if it is a real reading. Returns whether it was."""
        if not measurement.ok:
            return False
        assert measurement.value_s is not None  # narrows for the type checker
        self._samples.append(measurement.value_s)
        return True

    def percentiles(self) -> tuple[float | None, float | None]:
        """p50/p95 of the last :attr:`_WINDOW` readings. ``(None, None)`` before
        the first one -- never ``(0.0, 0.0)``, which would read as measured
        and instantaneous rather than not measured yet."""
        if not self._samples:
            return None, None
        ordered = sorted(self._samples)
        p50 = ordered[int(0.50 * (len(ordered) - 1))]
        p95 = ordered[int(0.95 * (len(ordered) - 1))]
        return p50, p95


SloStatus = Literal["ok", "warn", "critical", "unknown"]


def classify_slo(p95_s: float | None, *, warn_s: float, critical_s: float) -> SloStatus:
    """Where a hop's own p95 sits against its budget.

    ``unknown`` when there is nothing measured yet (never a fabricated ``ok``
    -- CLAUDE.md's "no fake anything": a hop nobody has observed is not proven
    healthy). ``critical`` past ``critical_s``, ``warn`` past ``warn_s`` but at
    or under ``critical_s``, ``ok`` at or under ``warn_s``.
    """
    if p95_s is None:
        return "unknown"
    if p95_s > critical_s:
        return "critical"
    if p95_s > warn_s:
        return "warn"
    return "ok"


__all__ = [
    "CLOCK_SKEW",
    "CLOCK_SKEW_TOLERANCE_S",
    "MISSING_TIMESTAMP",
    "LagMeasurement",
    "LagReason",
    "LagTracker",
    "SloStatus",
    "classify_slo",
    "measure_lag",
]
