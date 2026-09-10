"""Sentry init and the Prometheus metrics registry.

ARCHITECTURE.md §11: "Sentry em api e workers com release = SHA do commit."
"Metricas minimas: eventos por stream (produzidos, consumidos, lag), latencia
por exchange, gaps de candle, propostas aprovadas/rejeitadas por check, fills
simulados, erro por worker."
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import prometheus_client
import sentry_sdk
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

if TYPE_CHECKING:
    from starlette.types import ASGIApp

    from hunter_core.settings import Settings


def init_sentry(settings: Settings, role: str) -> None:
    """Initialize Sentry, or do nothing if ``SENTRY_DSN`` is empty (e.g. dev/test).

    ``send_default_pii=False`` per SECURITY.md §4 — no secret or personal data
    ever leaves the process through an error report. ``release`` comes from
    ``HUNTER_RELEASE`` (the commit SHA, set by CI/the deploy pipeline) when
    present, matching "release = SHA do commit".
    """
    dsn = settings.sentry_dsn.get_secret_value()
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.sentry_environment,
        release=os.environ.get("HUNTER_RELEASE"),
        send_default_pii=False,
    )
    sentry_sdk.set_tag("role", role)


registry = CollectorRegistry()

market_publish_failures_total = Counter(
    "market_publish_failures_total",
    "Market stream publications that failed while the producer was alive.",
    ["stream"],
    registry=registry,
)

events_produced_total = Counter(
    "hunter_events_produced_total",
    "Events published to a Redis Stream.",
    ["stream"],
    registry=registry,
)
events_consumed_total = Counter(
    "hunter_events_consumed_total",
    "Events consumed from a Redis Stream.",
    ["stream", "consumer"],
    registry=registry,
)
stream_lag = Gauge(
    "hunter_stream_lag",
    "Pending entries for a consumer group (approximate lag).",
    ["stream", "group"],
    registry=registry,
)
worker_errors_total = Counter(
    "hunter_worker_errors_total",
    "Unhandled errors caught by a worker's main loop.",
    ["role"],
    registry=registry,
)
exchange_latency_seconds = Histogram(
    "hunter_exchange_latency_seconds",
    "Round-trip latency of exchange REST/WS calls.",
    ["exchange"],
    registry=registry,
)
candle_gaps_total = Counter(
    "hunter_candle_gaps_total",
    "Candle gaps detected and recovered via REST.",
    ["exchange"],
    registry=registry,
)
proposals_total = Counter(
    "hunter_proposals_total",
    "Trade proposals decided, by outcome and the deciding risk check.",
    ["decision", "check"],
    registry=registry,
)
fills_simulated_total = Counter(
    "hunter_fills_simulated_total",
    "Simulated fills produced by paper/shadow execution.",
    ["portfolio_type"],
    registry=registry,
)

market_snapshot_stale_fields_total = Counter(
    "market_snapshot_stale_fields_total",
    "Snapshot fields written as NULL because their own hot-state timestamp was stale.",
    ["field"],
    registry=registry,
)
market_snapshot_skipped_no_data_total = Counter(
    "market_snapshot_skipped_no_data_total",
    "Minute snapshots skipped because no observable field was fresh (no hot state, "
    "or every field gated as stale).",
    registry=registry,
)
market_liquidation_duplicates_total = Counter(
    "market_liquidation_duplicates_total",
    "Liquidation rows collapsed by ON CONFLICT DO NOTHING (redelivered by the exchange).",
    registry=registry,
)
market_persistence_loss_reports_dropped_total = Counter(
    "market_persistence_loss_reports_dropped_total",
    "Loss reports evicted from the bounded loss queue before reaching system_events.",
    registry=registry,
)
market_sampling_bucket_skipped_total = Counter(
    "market_sampling_bucket_skipped_total",
    "Sampling boundaries missed because the previous round overran its interval.",
    ["loop"],
    registry=registry,
)
market_ingestion_gaps = Gauge(
    "market_ingestion_gaps",
    "Ingestion gaps by status for the monitored universe.",
    ["exchange", "status"],
    registry=registry,
)
market_system_event_record_failures_total = Counter(
    "market_system_event_record_failures_total",
    "system_events that could not be recorded because persistence was unavailable "
    "(HIGH-2): the worker keeps running, but the record itself was lost.",
    ["event"],
    registry=registry,
)
market_dropped_events_total = Counter(
    "market_dropped_events_total",
    "Non-final WS events an exchange adapter's bounded internal queue discarded "
    "under load (HIGH-1b). Final klines are never dropped.",
    ["exchange"],
    registry=registry,
)
# T3.0c — the SPOT venue reports separately from the perpetual one. New series
# rather than a ``market_type`` label on the existing ones: adding a label to a
# live counter resets every dashboard and alert built on it, and the two venues
# are collected by different connections with different budgets anyway.
market_spot_universe_size = Gauge(
    "market_spot_universe_size",
    "Spot pairs the wallet may execute on: 24h quote volume >= the D1 floor, "
    "measured on spot itself.",
    ["exchange"],
    registry=registry,
)
market_spot_events_total = Counter(
    "market_spot_events_total",
    "Normalized SPOT events accepted by the collector, by event kind.",
    ["exchange", "kind"],
    registry=registry,
)
market_spot_ingestion_gaps = Gauge(
    "market_spot_ingestion_gaps",
    "Ingestion gaps by status for the SPOT universe. Separate from "
    "``market_ingestion_gaps`` because both collectors would otherwise write "
    "the same {exchange,status} series and overwrite each other.",
    ["exchange", "status"],
    registry=registry,
)
# T3.0e (review-T3.0c-T3.0d.md, "Antes do deploy" item 1): ``run_heartbeat`` is
# shared by both loops and both adapters answer ``adapter.code == "binance"``
# by design, so a label on ``market_dropped_events_total`` cannot tell the two
# venues apart -- same reasoning as the three series above, same fix: a series
# of its own rather than a ``market_type`` label on a live counter.
market_spot_dropped_events_total = Counter(
    "market_spot_dropped_events_total",
    "Non-final WS events the SPOT adapter's bounded internal queue discarded "
    "under load. Separate from ``market_dropped_events_total`` so a spot "
    "reconnect (routine) cannot be misread as the perpetual (the Radar's "
    "primary health signal) losing tape.",
    ["exchange"],
    registry=registry,
)


# T3.79: the market-worker's two new end-to-end-latency hops. Buckets run
# sub-second (the whole point is proving the "<1s exchange->stream" budget of
# docs/PIPELINE.md §11), unlike the decision hop's own histogram
# (hunter_shadow_decision_lag_seconds, T3.74c) which is allowed minutes.
market_ingest_lag_seconds = Histogram(
    "hunter_market_ingest_lag_seconds",
    "Exchange event time to this process's own receive time, by event kind "
    "(trade/candle) -- the network leg of the exchange-to-stream budget. A "
    "reading is only observed here when hunter_core.latency.measure_lag found "
    "no clock-skew/missing-timestamp reason; see the *_anomalies_total "
    "counter below for those.",
    ["kind"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=registry,
)
market_ingest_lag_anomalies_total = Counter(
    "hunter_market_ingest_lag_anomalies_total",
    "Ingest-lag readings that could not enter hunter_market_ingest_lag_seconds, "
    "by kind and reason (missing_timestamp/clock_skew) -- never silently "
    "dropped, never folded into the histogram as a fabricated 0.",
    ["kind", "reason"],
    registry=registry,
)
candle_flush_lag_seconds = Histogram(
    "hunter_candle_flush_lag_seconds",
    "A closed 1m candle's own close_time to this process observing it durably "
    "queued for the outbox -- the docs/PIPELINE.md §6b 'exchange event -> "
    "candle on our stream' budget's dominant term (the outbox's own wake-"
    "triggered dispatch adds only the publication itself on top).",
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0),
    registry=registry,
)
candle_flush_lag_anomalies_total = Counter(
    "hunter_candle_flush_lag_anomalies_total",
    "Flush-lag readings that could not enter hunter_candle_flush_lag_seconds, "
    "by reason (missing_timestamp/clock_skew).",
    ["reason"],
    registry=registry,
)


def metrics_asgi_app() -> ASGIApp:
    """A ``/metrics`` ASGI app exposing :data:`registry` in Prometheus text format."""
    app: ASGIApp = prometheus_client.make_asgi_app(registry=registry)  # type: ignore
    return app
