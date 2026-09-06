"""Prometheus metrics of the scanner, **on the shared registry** -- ARCHITECTURE.md §11.

``hunter_core.observability`` keeps its own ``CollectorRegistry`` and that is
what ``/metrics`` exposes: a metric declared without it is collected into
prometheus_client's global default and is invisible to every scrape. Found in
the operational proof -- ``/metrics`` answered 200 with not one ``scanner_``
line in it.

The latency histogram is the contract of the joint M2 decision (p99 <= 3 s from
tick to opportunity), so it is measured end to end: the clock starts at the
*event* timestamp the market-worker stamped, not when this process picked the
work up. A queue this worker is behind on is exactly what the number has to
show.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from hunter_core.observability import registry

scanner_markets_evaluated_total = Counter(
    "hunter_scanner_markets_evaluated_total",
    "Feature vectors computed, by outcome.",
    ["outcome"],
    registry=registry,
)

scanner_tick_to_opportunity_seconds = Histogram(
    "hunter_scanner_tick_to_opportunity_seconds",
    "Age of the newest input when the opportunity it produced was scored.",
    buckets=(0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0),
    registry=registry,
)

scanner_stage_seconds = Histogram(
    "hunter_scanner_stage_seconds",
    "Wall time of one pipeline stage, so a p99 violation names its own cause.",
    ["stage"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=registry,
)

scanner_dirty_markets = Gauge(
    "hunter_scanner_dirty_markets",
    "Markets waiting for an evaluation right now.",
    registry=registry,
)

scanner_universe_size = Gauge(
    "hunter_scanner_universe_size",
    "Markets the scanner is responsible for.",
    registry=registry,
)

scanner_baselines = Gauge(
    "hunter_scanner_baselines",
    "Baseline buckets by reader verdict (usable / under construction).",
    ["state"],
    registry=registry,
)

scanner_anomalies_open = Gauge(
    "hunter_scanner_anomalies_open",
    "Anomalies currently active, by evaluation state.",
    ["state"],
    registry=registry,
)

scanner_opportunities = Gauge(
    "hunter_scanner_opportunities",
    "Open opportunity episodes by status.",
    ["status"],
    registry=registry,
)

scanner_persist_batch_seconds = Histogram(
    "hunter_scanner_persist_batch_seconds",
    "Wall time of one persistence transaction.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=registry,
)

scanner_backfill_requests_total = Counter(
    "hunter_scanner_backfill_requests_total",
    "Candle backfills asked of the market-worker (the scanner never calls REST).",
    registry=registry,
)

scanner_consumer_events_total = Counter(
    "hunter_scanner_consumer_events_total",
    "Stream messages handled, by stream.",
    ["stream"],
    registry=registry,
)

__all__ = [
    "scanner_anomalies_open",
    "scanner_backfill_requests_total",
    "scanner_baselines",
    "scanner_consumer_events_total",
    "scanner_dirty_markets",
    "scanner_markets_evaluated_total",
    "scanner_opportunities",
    "scanner_persist_batch_seconds",
    "scanner_stage_seconds",
    "scanner_tick_to_opportunity_seconds",
    "scanner_universe_size",
]
