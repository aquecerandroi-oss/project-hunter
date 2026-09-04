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


def metrics_asgi_app() -> ASGIApp:
    """A ``/metrics`` ASGI app exposing :data:`registry` in Prometheus text format."""
    app: ASGIApp = prometheus_client.make_asgi_app(registry=registry)  # type: ignore
    return app
