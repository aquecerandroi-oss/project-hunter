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


def metrics_asgi_app() -> ASGIApp:
    """A ``/metrics`` ASGI app exposing :data:`registry` in Prometheus text format."""
    app: ASGIApp = prometheus_client.make_asgi_app(registry=registry)  # type: ignore
    return app
