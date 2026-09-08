"""Prometheus metrics of the shadow worker, on the shared registry.

ARCHITECTURE.md §11 asks for counts per worker; the Shadow Lab additionally
needs *coverage*: how many bars were evaluated and why they produced nothing.
"Zero signals" is a valid result, but only if the number of evaluations that
produced it is visible next to it — otherwise a silent worker and a strict
strategy look identical.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

from hunter_core.observability import registry

__all__ = [
    "shadow_evaluations_total",
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
