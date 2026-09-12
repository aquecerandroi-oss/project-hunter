"""Per-source liveness and budget — the numbers ``hb:meme:radar`` carries since
T4.2c and ``GET /meme/sources`` renders. Pure: no IO, injectable clock.

The adendo's finding was that the heartbeat had ``ts/last_success/errors/version``
and nothing an operator could read a degraded source from. Every counter here
answers one question over a **sliding window** (:class:`RollingCounter`): how many
requests did a budget spend in the last 60 s, how many frames were malformed, how
many errors in the last hour, how far behind the source's clock is ours. A source
that is switched off says ``enabled = false``; a source that never spoke says
``last_observed_at = null`` — never a zero that looks like health.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

PUMPPORTAL_WS = "pumpportal_ws"
PUMPFUN_REST = "pumpfun_rest"
SOLANA_RPC = "solana_rpc"
TRENCHES_WS = "trenches_ws"
SWAP_API = "swap_api"
INDEXER_RISK = "indexer_risk"
SOURCE_NAMES: tuple[str, ...] = (
    PUMPPORTAL_WS,
    PUMPFUN_REST,
    SOLANA_RPC,
    TRENCHES_WS,
    SWAP_API,
    INDEXER_RISK,
)


class RollingCounter:
    """Events inside the last ``window_s`` seconds; older ones fall off on read."""

    def __init__(self, window_s: float) -> None:
        self._window = timedelta(seconds=window_s)
        self._events: deque[tuple[datetime, int]] = deque()

    def add(self, at: datetime, count: int = 1) -> None:
        if count > 0:
            self._events.append((at, count))

    def total(self, now: datetime) -> int:
        cutoff = now - self._window
        while self._events and self._events[0][0] < cutoff:
            self._events.popleft()
        return sum(count for _, count in self._events)


@dataclass
class SourceStats:
    """One source. ``connected`` is ``None`` for a request/response source."""

    name: str
    enabled: bool = True
    budget_60s: int | None = None
    connected: bool | None = None
    last_observed_at: datetime | None = None
    last_received_at: datetime | None = None
    last_error: str | None = None
    last_error_at: datetime | None = None
    reason: str | None = None
    """Why the source has nothing to say (``disabled``, ``never_connected``…)."""
    used_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    errors_1h: RollingCounter = field(default_factory=lambda: RollingCounter(3600))

    def record_ok(self, *, observed_at: datetime, received_at: datetime, count: int = 1) -> None:
        self.used_60s.add(received_at, count)
        if self.last_observed_at is None or observed_at >= self.last_observed_at:
            self.last_observed_at = observed_at
        if self.last_received_at is None or received_at >= self.last_received_at:
            self.last_received_at = received_at
        self.reason = None

    def record_spent(self, at: datetime, count: int = 1) -> None:
        """A request that cost budget but produced no observation (an error)."""
        self.used_60s.add(at, count)

    def record_error(self, at: datetime, error: str) -> None:
        self.errors_1h.add(at)
        self.last_error = error
        self.last_error_at = at

    def lag_s(self, now: datetime) -> float | None:
        if self.last_observed_at is None or self.last_received_at is None:
            return None
        return round((self.last_received_at - self.last_observed_at).total_seconds(), 3)

    def as_fields(self, now: datetime) -> dict[str, object]:
        reason = self.reason
        if not self.enabled:
            reason = "disabled"
        elif self.last_observed_at is None:
            reason = reason or "never_observed"
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "last_observed_at": _iso(self.last_observed_at),
            "last_received_at": _iso(self.last_received_at),
            "lag_s": self.lag_s(now),
            "age_s": None
            if self.last_received_at is None
            else round((now - self.last_received_at).total_seconds(), 1),
            "used_60s": self.used_60s.total(now),
            "budget_60s": self.budget_60s,
            "errors_1h": self.errors_1h.total(now),
            "last_error": self.last_error,
            "last_error_at": _iso(self.last_error_at),
            "reason": reason,
        }


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


@dataclass
class SourcesState:
    """Every source the radar has, plus the three radar-wide rolling counts."""

    sources: dict[str, SourceStats] = field(
        default_factory=lambda: {name: SourceStats(name) for name in SOURCE_NAMES}
    )
    gaps_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    ws_malformed_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    trenches_patches_60s: RollingCounter = field(default_factory=lambda: RollingCounter(60))
    last_snapshot_observed_at: datetime | None = None
    last_snapshot_received_at: datetime | None = None
    _sampled: dict[str, int] = field(default_factory=dict[str, int])

    def __getitem__(self, name: str) -> SourceStats:
        return self.sources[name]

    def sample_counter(self, key: str, value: int, at: datetime, into: RollingCounter) -> int:
        """Turn a monotonic counter (a client's ``state.malformed``) into events:
        the increase since the last sample lands in the rolling window."""
        previous = self._sampled.get(key, 0)
        delta = max(0, value - previous)
        self._sampled[key] = value
        into.add(at, delta)
        return delta

    def record_snapshot(self, *, observed_at: datetime, received_at: datetime) -> None:
        if self.last_snapshot_observed_at is None or observed_at >= self.last_snapshot_observed_at:
            self.last_snapshot_observed_at = observed_at
            self.last_snapshot_received_at = received_at

    def heartbeat_fields(self, now: datetime, *, tracked: int) -> dict[str, str]:
        """The flat fields the adendo names, plus one JSON field per source."""
        lag = (
            None
            if self.last_snapshot_observed_at is None or self.last_snapshot_received_at is None
            else round(
                (self.last_snapshot_received_at - self.last_snapshot_observed_at).total_seconds(),
                3,
            )
        )
        trenches = self.sources[TRENCHES_WS]
        fields: dict[str, object] = {
            "tracked": tracked,
            "budget_used_60s": self.sources[PUMPFUN_REST].used_60s.total(now),
            "budget_60s": self.sources[PUMPFUN_REST].budget_60s,
            "gaps_60s": self.gaps_60s.total(now),
            "ws_malformed_60s": self.ws_malformed_60s.total(now),
            "last_snapshot_observed_at": _iso(self.last_snapshot_observed_at),
            "lag_s": lag,
            "trenches_connected": "disabled"
            if not trenches.enabled
            else ("true" if trenches.connected else "false"),
            "trenches_patches_60s": self.trenches_patches_60s.total(now),
            "swap_api_used_60s": self.sources[SWAP_API].used_60s.total(now),
            "swap_api_budget_60s": self.sources[SWAP_API].budget_60s,
            "sources_at": now.isoformat(),
            "sources": json.dumps(
                {name: stats.as_fields(now) for name, stats in self.sources.items()},
                sort_keys=True,
            ),
        }
        return {key: "" if value is None else str(value) for key, value in fields.items()}
