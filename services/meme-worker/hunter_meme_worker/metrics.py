"""Prometheus metrics of the meme radar, **on the shared registry** — ARCHITECTURE.md §11.

``hunter_core.observability`` keeps its own ``CollectorRegistry`` and that is what
``/metrics`` exposes: a metric declared without it lands in prometheus_client's
global default and is invisible to every scrape (the scanner's own operational
finding, ``services/scanner-worker/.../metrics.py``).

What is measured here is **coverage**, not opinion. The radar concludes nothing, so
the only questions its metrics can answer are: is discovery connected, how much of
the tracked set the budget actually reached, and how many minutes were folded with
no observation behind them.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

from hunter_core.observability import registry

meme_events_total = Counter(
    "hunter_meme_events_total",
    "PumpPortal frames turned into a durable row, by kind.",
    ["kind"],
    registry=registry,
)

meme_tracked_mints = Gauge(
    "hunter_meme_tracked_mints",
    "Size of the tracked set right now.",
    registry=registry,
)

meme_polls_total = Counter(
    "hunter_meme_polls_total",
    "Curve reads attempted, by source and outcome.",
    ["source", "outcome"],
    registry=registry,
)

meme_budget_skipped_total = Counter(
    "hunter_meme_budget_skipped_total",
    "Tracked mints a cycle could not reach inside the request budget. Each one is "
    "also a row in meme_ingest_gaps: the number here is the alarm, the row is the "
    "evidence.",
    registry=registry,
)

meme_features_rows_total = Counter(
    "hunter_meme_features_rows_total",
    "Per-minute feature rows written, by whether the minute had a curve "
    "observation behind it (covered) or was folded with a reason (uncovered).",
    ["coverage"],
    registry=registry,
)

meme_gaps_total = Counter(
    "hunter_meme_gaps_total",
    "Gap rows written, by stream and reason.",
    ["stream", "reason"],
    registry=registry,
)

meme_tokens_pruned_total = Counter(
    "hunter_meme_tokens_pruned_total",
    "Discovery rows removed by retention (MEME_RETENTION_DAYS).",
    registry=registry,
)

meme_ws_generation = Gauge(
    "hunter_meme_ws_generation",
    "PumpPortal connection generation. It increments on every reconnect, and a "
    "reconnect is what proves a gap — never what recovers one.",
    registry=registry,
)

meme_source_messages_total = Counter(
    "hunter_meme_source_messages_total",
    "Observations accepted per T4.2c source (board messages, tape pages, risk reads).",
    ["source"],
    registry=registry,
)

meme_source_errors_total = Counter(
    "hunter_meme_source_errors_total",
    "Errors per T4.2c source (rate limits, transport, malformed frames).",
    ["source"],
    registry=registry,
)

meme_rows_total = Counter(
    "hunter_meme_rows_total",
    "Rows offered to the T4.2c tables, by table (duplicates are the schema's).",
    ["table"],
    registry=registry,
)
