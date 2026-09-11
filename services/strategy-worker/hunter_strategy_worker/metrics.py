"""Prometheus metrics of the shadow worker, on the shared registry.

ARCHITECTURE.md §11 asks for counts per worker; the Shadow Lab additionally
needs *coverage*: how many bars were evaluated and why they produced nothing.
"Zero signals" is a valid result, but only if the number of evaluations that
produced it is visible next to it — otherwise a silent worker and a strict
strategy look identical.
"""

from __future__ import annotations

from collections import deque

from prometheus_client import Counter, Gauge, Histogram

from hunter_core.observability import registry

__all__ = [
    "decision_lag_percentiles",
    "observe_decision_lag",
    "shadow_bars_skipped_total",
    "shadow_decision_lag_seconds",
    "shadow_evaluations_total",
    "shadow_redis_timeouts_total",
    "shadow_stage_seconds",
    "shadow_version_failed_total",
    "shadow_funding_unresolved_total",
    "shadow_outbox_dispatched_total",
    "shadow_outbox_pending",
    "shadow_outcomes_total",
    "shadow_signals_total",
    "shadow_trackings_open",
    "shadow_trackings_unswept",
    "shadow_versions_active",
    "shadow_versions_runnable",
    "shadow_versions_unrunnable",
]

shadow_bars_skipped_total = Counter(
    "hunter_shadow_bars_skipped_total",
    "Closed candles the shadow consumer refused before any evaluation, by reason.",
    ["reason"],
    registry=registry,
)
"""A bar that never reaches a version is not an evaluation in any state, so it
cannot be counted in ``shadow_evaluations_total`` — and it must not be invisible
either: the ``spot`` listing of a symbol is refused at the door (T3.73) and this
is what says so out loud."""

shadow_evaluations_total = Counter(
    "hunter_shadow_evaluations_total",
    "Shadow bar evaluations, by strategy and EvaluationState.",
    ["strategy", "state"],
    registry=registry,
)
shadow_signals_total = Counter(
    "hunter_shadow_signals_total",
    "Shadow decisions persisted, by strategy and initial tracking state.",
    ["strategy", "tracking_state"],
    registry=registry,
)
shadow_outcomes_total = Counter(
    "hunter_shadow_outcomes_total",
    "Shadow trackings that reached a final tracking state, by state and result.",
    ["tracking_state", "result"],
    registry=registry,
)
shadow_funding_unresolved_total = Counter(
    "hunter_shadow_funding_unresolved_total",
    "Terminal outcomes whose R_net stayed null because funding could not be "
    "established, by reason family (the part before ':', so a per-instant "
    "funding_missing reason does not explode cardinality).",
    ["reason"],
    registry=registry,
)
shadow_trackings_open = Gauge(
    "hunter_shadow_trackings_open",
    "Shadow trackings currently pending_entry or active.",
    registry=registry,
)
shadow_outbox_pending = Gauge(
    "hunter_shadow_outbox_pending",
    "Rows in shadow_outbox still waiting to be published.",
    registry=registry,
)
shadow_outbox_dispatched_total = Counter(
    "hunter_shadow_outbox_dispatched_total",
    "Outbox rows published to their stream.",
    ["stream"],
    registry=registry,
)
shadow_trackings_unswept = Gauge(
    "hunter_shadow_trackings_unswept",
    "Open trackings left unvisited by the last sweep (over load_open_trackings' limit).",
    registry=registry,
)
"""``load_open_trackings`` reads at most 500 rows per pass. Past that the sweep
silently stopped advancing the rest; this is what makes the backlog visible."""

shadow_version_failed_total = Counter(
    "hunter_shadow_version_failed_total",
    "Bar evaluations that raised, by strategy key and version. The other "
    "versions of the same bar still ran and the message was still acked.",
    ["strategy_key", "version"],
    registry=registry,
)
"""One broken version used to abort the whole bar: ``handle_candle`` looped over
every due version with no ``try``, so an exception in the first one skipped the
rest and left the message un-acked (review T3.26-risk, A3). Labelled by version
— not only by strategy — because the failure that matters is a *derived
variant* whose frozen parameters raise on every bar while its siblings are fine.
The cardinality is bounded by the roster (a handful of active rows)."""

shadow_redis_timeouts_total = Counter(
    "hunter_shadow_redis_timeouts_total",
    "redis.exceptions.TimeoutError observed by the shadow consumer, by stage.",
    ["stage"],
    registry=registry,
)
"""T3.83: a Redis timeout is a transient infra failure, not a broken version —
counted apart from ``shadow_version_failed_total`` so the two are never
confused when reading a dashboard. ``stage="version_evaluate"`` is
``handle_candle``'s per-version loop re-raising instead of swallowing (the bar
gets redelivered instead of silently missing that version's decision);
``stage="consumer_loop"`` is ``run_consumer``'s own restart. Found on the VPS:
four shards, same ~12s window, a midnight burst stalling Redis
(notes-T3.83.md)."""

shadow_versions_active = Gauge(
    "hunter_shadow_versions_active",
    "strategy_versions rows with status='active' and an activated_at.",
    registry=registry,
)
shadow_versions_runnable = Gauge(
    "hunter_shadow_versions_runnable",
    "Active versions this build can actually evaluate (code present, code_ref matching).",
    registry=registry,
)
shadow_versions_unrunnable = Gauge(
    "hunter_shadow_versions_unrunnable",
    "Active versions refused, by reason.",
    ["reason"],
    registry=registry,
)
"""``runnable == 0`` with ``active > 0`` is the failure the readiness check
turns red on; the per-reason gauge is what shows a *partly* dead roster, which
one surviving version would otherwise hide."""

shadow_decision_lag_seconds = Histogram(
    "hunter_shadow_decision_lag_seconds",
    "Time from a bar's close to its persisted decision -- the in-process "
    "twin of `agent_signals.emitted_at - supporting_features.observation_ts` "
    "(T3.74c), observed once per signal actually written, not per evaluation.",
    buckets=(0.5, 1, 2, 3, 5, 8, 13, 21, 34, 60, 90, 120, 180, 300),
    registry=registry,
)

shadow_stage_seconds = Histogram(
    "hunter_shadow_stage_seconds",
    "Wall time of one stage of handle_candle, by stage, so a p95 violation "
    "of hunter_shadow_decision_lag_seconds names its own cause instead of a "
    "single end-to-end number. Stages: queue_wait (stream publish to pickup), "
    "market_lookup, family_preload (T3.74b context cache), context_load "
    "(per version), persist (slot lock through outbox write).",
    ["stage"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=registry,
)

_LAG_SAMPLE_WINDOW = 500
"""Bounded reservoir for the heartbeat's own p50/p95 (T3.74c).

Prometheus already has the full histogram (`shadow_decision_lag_seconds`), but
reading a quantile out of it needs a Prometheus server (`histogram_quantile`)
this worker does not run. The heartbeat (`hb:strategy:shadow`) is read directly
with `HGETALL` on the VPS, no scrape needed, so it keeps its own small window
purely for that -- last 500 persisted signals, in memory, lost on restart like
every other `ConsumerHealth` counter.
"""

_decision_lag_samples: deque[float] = deque(maxlen=_LAG_SAMPLE_WINDOW)


def observe_decision_lag(seconds: float) -> None:
    """Record one bar-close-to-persisted-decision latency, in both places."""
    shadow_decision_lag_seconds.observe(seconds)
    _decision_lag_samples.append(seconds)


def decision_lag_percentiles() -> tuple[float | None, float | None]:
    """p50/p95 of the last :data:`_LAG_SAMPLE_WINDOW` persisted signals.

    ``None`` for both before the first signal of this process's lifetime --
    never ``0.0``, which would read as "instantaneous" instead of "unknown".
    """
    if not _decision_lag_samples:
        return None, None
    ordered = sorted(_decision_lag_samples)
    p50 = ordered[int(0.50 * (len(ordered) - 1))]
    p95 = ordered[int(0.95 * (len(ordered) - 1))]
    return p50, p95
