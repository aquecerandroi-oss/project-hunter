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
    "Age of the newest input when the observation it triggered finished: the "
    "scorer ran and the projections went out -- or there was nothing usable to "
    "project, which is a finished cycle too. A Radar row Redis refused is NOT "
    "sampled: that observation was not delivered.",
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

scanner_bootstrap_markets = Gauge(
    "hunter_scanner_bootstrap_markets",
    "Markets by baseline bootstrap state (done / pending / running).",
    ["state"],
    registry=registry,
)

scanner_bootstrap_cuts_total = Counter(
    "hunter_scanner_bootstrap_cuts_total",
    "Minutes replayed by the baseline bootstrap. The unit of its cost.",
    registry=registry,
)

scanner_bootstrap_suspended = Gauge(
    "hunter_scanner_bootstrap_suspended",
    "1 while the baseline bootstrap is standing aside for a late evaluation loop.",
    registry=registry,
)

scanner_hot_rows_resident = Gauge(
    "hunter_scanner_hot_rows_resident",
    "Decoded hot-state rows kept in memory across ticks, over the whole "
    "universe. The price of the incremental context: ~2.4 KB per candle row.",
    ["kind"],
    registry=registry,
)

scanner_hot_rows_decoded_total = Counter(
    "hunter_scanner_hot_rows_decoded_total",
    "Hot-state rows this process had to decode. A steady state costs one candle "
    "per market per minute plus the trades that arrived; a number that tracks "
    "the universe times 3500 means the reuse is not happening.",
    registry=registry,
)

scanner_baseline_revisions_total = Counter(
    "hunter_scanner_baseline_revisions_total",
    "Baseline revisions offered to the archive, by source and outcome. "
    '"written" counts what was sent to the append-only INSERT, including the '
    'idempotent collisions a retry produces; "withheld" counts what was not sent '
    "because it would have replaced a usable baseline with a less mature one.",
    ["source", "outcome"],
    registry=registry,
)

scanner_detectors_disarmed = Gauge(
    "hunter_scanner_detectors_disarmed",
    "Markets whose detector is disarmed, by type and reason -- never armed and mute.",
    ["type", "reason"],
    registry=registry,
)


scanner_consumer_events_total = Counter(
    "hunter_scanner_consumer_events_total",
    "Stream messages handled, by stream.",
    ["stream"],
    registry=registry,
)

scanner_ticks_coalesced_total = Counter(
    "hunter_scanner_ticks_coalesced_total",
    "Notifications absorbed by another one of the same market inside the same "
    "read batch: work that was never worth doing twice, because the evidence is "
    "the hot state at the current cut and not the message. Messages with no "
    "market attached are NOT counted here.",
    ["stream"],
    registry=registry,
)

scanner_stream_delay_seconds = Histogram(
    "hunter_scanner_stream_delay_seconds",
    "Age of the OLDEST message of a read batch when it was read, from the stamp "
    "the market-worker put on it: the queue itself, sampled before coalescence "
    "replaces it with the newest one. Read it per stream and per BATCH, not per "
    "message: for market.ticks it is queue plus publication delay, but for "
    "market.derivatives the stamp is the sample instant of a 5-minute cadence, "
    "so minutes there mean 'the last sample is old', not 'the consumer is late'.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0),
    labelnames=["stream"],
    registry=registry,
)

__all__ = [
    "scanner_anomalies_open",
    "scanner_backfill_requests_total",
    "scanner_baseline_revisions_total",
    "scanner_baselines",
    "scanner_bootstrap_cuts_total",
    "scanner_bootstrap_markets",
    "scanner_bootstrap_suspended",
    "scanner_hot_rows_decoded_total",
    "scanner_hot_rows_resident",
    "scanner_consumer_events_total",
    "scanner_detectors_disarmed",
    "scanner_dirty_markets",
    "scanner_markets_evaluated_total",
    "scanner_opportunities",
    "scanner_persist_batch_seconds",
    "scanner_stage_seconds",
    "scanner_stream_delay_seconds",
    "scanner_tick_to_opportunity_seconds",
    "scanner_ticks_coalesced_total",
    "scanner_universe_size",
]
