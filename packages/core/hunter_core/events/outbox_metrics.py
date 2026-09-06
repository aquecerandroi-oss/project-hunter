"""Prometheus series for the generic outbox (T2.9), on the shared registry."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

from hunter_core.observability import registry

outbox_pending = Gauge(
    "hunter_outbox_pending",
    "Outbox rows still waiting to reach their stream (dispatched_at IS NULL).",
    registry=registry,
)
outbox_oldest_pending_seconds = Gauge(
    "hunter_outbox_oldest_pending_seconds",
    "Age of the oldest undispatched outbox row — the dispatcher's real lag.",
    registry=registry,
)
outbox_dispatched_total = Counter(
    "hunter_outbox_dispatched_total",
    "Outbox rows published to a stream (at-least-once: a retry counts again).",
    ["stream"],
    registry=registry,
)
outbox_dispatch_failures_total = Counter(
    "hunter_outbox_dispatch_failures_total",
    "Publication attempts that failed and left the row pending.",
    ["stream"],
    registry=registry,
)
outbox_replayed_total = Counter(
    "hunter_outbox_replayed_total",
    "Already-dispatched rows republished to recover a lost/trimmed stream.",
    ["stream"],
    registry=registry,
)

__all__ = [
    "outbox_dispatch_failures_total",
    "outbox_dispatched_total",
    "outbox_oldest_pending_seconds",
    "outbox_pending",
    "outbox_replayed_total",
]
