"""The launch lane's own counters (T4.67a) — the brief's own list, mirroring
``event_gate_stats.py``'s shape: a rolling 60-second window for the rates,
cumulative totals for the rest, an absent number written as ``""``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from hunter_meme_worker.lab_heartbeat import percentile

__all__ = ["LaunchLaneStats", "heartbeat_fields"]

HEARTBEAT_PREFIX = "launch_lane_"
WINDOW_S = 60
LATENCY_SAMPLE = 500


def _trim(window: deque[datetime], now: datetime) -> None:
    horizon = now - timedelta(seconds=WINDOW_S)
    while window and window[0] < horizon:
        window.popleft()


@dataclass
class LaunchLaneStats:
    """Since boot, plus a 60-second rolling count of creates."""

    creates_total: int = 0
    creates_window: deque[datetime] = field(default_factory=lambda: deque[datetime]())
    proposals_total: int = 0
    paper_open: int = 0
    paper_closed_total: int = 0
    born_full_total: int = 0
    """KB-0123's "nasce cheia": progress at or above the threshold within the
    window of the create — counted, and the pending entry abandoned rather
    than opened at what is already the peak."""
    latency_ms: deque[int] = field(default_factory=lambda: deque(maxlen=LATENCY_SAMPLE))
    """``create_to_proposal_ms`` of every proposal this process wrote."""

    def record_create(self, now: datetime) -> None:
        self.creates_total += 1
        self.creates_window.append(now)
        _trim(self.creates_window, now)

    def record_proposal(self, *, latency_ms: int | None) -> None:
        self.proposals_total += 1
        if latency_ms is not None:
            self.latency_ms.append(latency_ms)

    def record_paper_open(self) -> None:
        self.paper_open += 1

    def record_paper_closed(self) -> None:
        self.paper_open = max(0, self.paper_open - 1)
        self.paper_closed_total += 1

    def record_born_full(self) -> None:
        self.born_full_total += 1


def heartbeat_fields(stats: LaunchLaneStats, *, now: datetime, mode: str) -> dict[str, str]:
    _trim(stats.creates_window, now)
    latencies = list(stats.latency_ms)
    p50, p95 = percentile(latencies, 0.50), percentile(latencies, 0.95)
    fields: dict[str, str] = {
        "mode": mode,
        "creates_60s": str(len(stats.creates_window)),
        "creates_total": str(stats.creates_total),
        "proposals_total": str(stats.proposals_total),
        "paper_open": str(stats.paper_open),
        "paper_closed_total": str(stats.paper_closed_total),
        "born_full_60s": str(stats.born_full_total),
        "create_to_proposal_ms_p50": "" if p50 is None else str(p50),
        "create_to_proposal_ms_p95": "" if p95 is None else str(p95),
    }
    return {HEARTBEAT_PREFIX + key: value for key, value in fields.items()}
