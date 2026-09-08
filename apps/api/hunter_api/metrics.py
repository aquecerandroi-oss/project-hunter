"""Prometheus counters meaningful only inside the ``api`` process.

``hunter_core.observability`` owns the shared registry mounted at
``/metrics`` (``app.py``); the series it declares are the ones useful to
both ``api`` and the workers. Rate limiting only runs in ``api``, so its
counter lives here, registered against that same shared registry rather than
a second one -- a second registry would need a second ``/metrics`` mount.
"""

from __future__ import annotations

from prometheus_client import Counter

from hunter_core.observability import registry

rate_limit_internal_peer_total = Counter(
    "hunter_rate_limit_internal_peer_total",
    "Requests whose per-address rate-limit bucket widened to "
    "rate_limit_per_minute_internal because the TCP peer is listed in "
    "INTERNAL_PEER_IPS (T3.28a). Staying at zero after a deploy is the "
    "signal that the compose IP and the list drifted apart and the widening "
    "silently stopped matching (T3.28d, security-reviewer finding 3).",
    registry=registry,
)

ws_closed_total = Counter(
    "hunter_ws_closed_total",
    "Every /ws gateway close, by close code (T3.44b) -- gateway-initiated "
    "(realtime.session.close_socket) and client-initiated ones the gateway "
    "merely observed while waiting on receive_text(). A 4401 count with no "
    "matching structured log line was the gap that hid the auth-race bug for "
    "days; this and the ws_closed log line close it together.",
    ["code"],
    registry=registry,
)
