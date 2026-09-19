"""T4.63 — the counters of the event-driven exits, and their heartbeat fields.

One object per process (``ExecutorContext.event_exits``), written by the
loops of ``event_exits.py`` and read by ``heartbeat.py`` — so the desk can
re-read, after the deploy, the number CITIZEN (18/09/2026) was lost to: the
seconds between a curve update and the sell being submitted
(``event_to_sell_submit_s_p50``/``_p95``). Everything here is memory only and
bounded (deques); a restart starts at zero, never at a guess.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

__all__ = ["EventExitsStats", "heartbeat_fields", "percentile"]

UPDATES_WINDOW_S = 60
_UPDATES_MAXLEN = 20_000
_LATENCY_MAXLEN = 200


def percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile (``pct`` in ``(0, 1]``) — one sample answers
    with itself, never with a fabricated interpolation."""
    ordered = sorted(samples)
    rank = max(1, math.ceil(pct * len(ordered)))
    return ordered[rank - 1]


@dataclass(slots=True)
class EventExitsStats:
    ws_state: str = "off"
    subscriptions: int = 0
    updates: deque[datetime] = field(default_factory=lambda: deque(maxlen=_UPDATES_MAXLEN))
    """Receipt instants of the account/trade notifications of watched
    positions — ``updates_60s`` counts the ones inside the window."""
    triggered_total: int = 0
    """Times ``decide_exit`` fired on an event (a sell attempt followed, under
    the position's lock — which may have found it already closed)."""
    submit_latencies: deque[float] = field(default_factory=lambda: deque(maxlen=_LATENCY_MAXLEN))
    """``submitted_at − received_at`` of the notification that fired, seconds."""
    bad_frames_total: int = 0
    restarts_total: int = 0
    reconnects_total: int = 0
    dropped_total: int = 0
    creator_sells_seen_total: int = 0
    """Creator sells seen in a ``TradeEvent`` of a watched mint (stamped on the row)."""
    marks_written_total: int = 0
    sell_errors_total: int = 0
    """Sell tasks that raised (RPC, DB) — the tick retries; counted, never hidden."""
    third_party_sells_seen_total: int = 0
    """T4.67b: first third-party sells seen on watched launch curves."""

    def record_update(self, now: datetime) -> None:
        self.updates.append(now)

    def updates_60s(self, now: datetime) -> int:
        since = now - timedelta(seconds=UPDATES_WINDOW_S)
        return sum(1 for at in self.updates if at >= since)

    def record_trigger(self) -> None:
        self.triggered_total += 1

    def record_submit_latency(self, seconds: float) -> None:
        self.submit_latencies.append(max(0.0, seconds))

    def record_bad_frame(self) -> None:
        self.bad_frames_total += 1

    def record_restart(self) -> None:
        self.restarts_total += 1

    def record_reconnect(self) -> None:
        self.reconnects_total += 1

    def record_dropped(self) -> None:
        self.dropped_total += 1

    def record_creator_sell(self) -> None:
        self.creator_sells_seen_total += 1

    def record_third_party_sell(self) -> None:
        self.third_party_sells_seen_total += 1


def heartbeat_fields(stats: EventExitsStats, *, now: datetime, enabled: bool) -> dict[str, str]:
    """The ``event_exits_*`` fields of ``hb:meme:executor``. With the flag off
    the state reads ``off`` and every counter is ``0`` — published anyway, so
    a desk that expects the field sees "off", not "missing"."""
    latencies = list(stats.submit_latencies)
    return {
        "event_exits_enabled": str(enabled).lower(),
        "event_exits_ws_state": stats.ws_state if enabled else "off",
        "event_exits_subscriptions": str(stats.subscriptions),
        "event_exits_updates_60s": str(stats.updates_60s(now)),
        "event_exits_triggered_total": str(stats.triggered_total),
        "event_to_sell_submit_s_p50": (
            "" if not latencies else f"{statistics.median(latencies):.3f}"
        ),
        "event_to_sell_submit_s_p95": (
            "" if not latencies else f"{percentile(latencies, 0.95):.3f}"
        ),
        "event_exits_bad_frames": str(stats.bad_frames_total),
        "event_exits_restarts_total": str(stats.restarts_total),
        "event_exits_reconnects": str(stats.reconnects_total),
        "event_exits_dropped": str(stats.dropped_total),
        "event_exits_creator_sells_seen": str(stats.creator_sells_seen_total),
        "event_exits_marks_written": str(stats.marks_written_total),
        "event_exits_sell_errors": str(stats.sell_errors_total),
        "event_exits_third_party_sells_seen": str(stats.third_party_sells_seen_total),
    }
