"""The copy lane's counters and latency samples (H-037) and the ``copy_*`` fields of
``hb:meme:radar`` they become — mirroring ``launch_lane_stats.py``: strings, an absent number is
``""`` (never a ``0`` that reads as a measurement).

Latencies are kept in microseconds as integers (bounded samples) and published in milliseconds with
three decimals: ``observed→decided`` (our own decision latency, what the hot path controls) and
``block_time→decided`` (the end-to-end figure, limited by the chain's whole-second ``block_time``),
the decision's own CPU cost, and — separately, never inside the first two — the confirmation delay.
"""

from __future__ import annotations

import json
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from hunter_meme_worker.copy_events import ms_iso
from hunter_meme_worker.lab_heartbeat import percentile

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

__all__ = ["CopyStats", "heartbeat_fields"]

HEARTBEAT_PREFIX = "copy_"
SAMPLE = 2000


def _samples() -> deque[int]:
    return deque(maxlen=SAMPLE)


@dataclass
class LeaderCounters:
    events: int = 0
    entries: int = 0
    exits: int = 0
    censored: int = 0
    last_event_at: datetime | None = None


@dataclass
class CopyStats:
    wallets: Iterable[str]
    leaders: dict[str, LeaderCounters] = field(default_factory=dict[str, LeaderCounters])
    events_seen: int = 0
    entries: int = 0
    exits: int = 0
    invalidated: int = 0
    gaps_seen: int = 0
    funnel_collisions: int = 0
    queue_full: int = 0
    outbox_dropped: int = 0
    closed_elsewhere: int = 0
    bad_items: int = 0
    last_error: str = ""
    persist_dropped: int = 0
    last_event_at: datetime | None = None
    censored_by_reason: Counter[str] = field(default_factory=Counter[str])
    skipped_by_reason: Counter[str] = field(default_factory=Counter[str])
    rejected_by_reason: Counter[str] = field(default_factory=Counter[str])
    observed_to_decided_us: deque[int] = field(default_factory=_samples)
    block_to_decided_us: deque[int] = field(default_factory=_samples)
    fields_to_decided_us: deque[int] = field(default_factory=_samples)
    decide_us: deque[int] = field(default_factory=_samples)
    confirm_delay_ms: deque[int] = field(default_factory=_samples)
    decided_to_priced_ms: deque[int] = field(default_factory=_samples)
    persist_ms: deque[int] = field(default_factory=_samples)

    def __post_init__(self) -> None:
        self.leaders = {wallet: LeaderCounters() for wallet in self.wallets}

    def record_event(self, wallet: str, *, at: datetime) -> None:
        self.events_seen += 1
        self.last_event_at = at
        counters = self.leaders.get(wallet)
        if counters is not None:
            counters.events += 1
            counters.last_event_at = at

    def record_decision(
        self,
        wallet: str,
        *,
        observed_to_decided_us: int,
        fields_to_decided_us: int,
        block_to_decided_us: int | None,
        decide_us: int,
        at: datetime,
    ) -> None:
        self.record_event(wallet, at=at)
        self.observed_to_decided_us.append(observed_to_decided_us)
        self.fields_to_decided_us.append(fields_to_decided_us)
        if block_to_decided_us is not None:
            self.block_to_decided_us.append(block_to_decided_us)
        self.decide_us.append(decide_us)

    def record_entry(self, wallet: str, *, at: datetime) -> None:
        self.entries += 1
        self.leaders[wallet].entries += 1

    def record_exit(self, wallet: str) -> None:
        self.exits += 1
        self.leaders[wallet].exits += 1

    def record_censored(self, wallet: str, reason: str) -> None:
        self.censored_by_reason[reason] += 1
        counters = self.leaders.get(wallet)
        if counters is not None:
            counters.censored += 1

    def record_skip(self, reason: str) -> None:
        self.skipped_by_reason[reason] += 1

    def record_rejected(self, reason: str) -> None:
        self.rejected_by_reason[reason] += 1

    def record_confirmation(self, delay_ms: int) -> None:
        self.confirm_delay_ms.append(delay_ms)

    def record_invalidated(self) -> None:
        self.invalidated += 1

    def record_priced(self, decided_to_priced_ms: int) -> None:
        self.decided_to_priced_ms.append(decided_to_priced_ms)

    def record_persisted(self, persist_ms: int) -> None:
        self.persist_ms.append(persist_ms)


def _ms(values: deque[int], fraction: float) -> str:
    value = percentile(list(values), fraction)
    return "" if value is None else f"{value / 1000:.3f}"


def _int(values: deque[int], fraction: float) -> str:
    value = percentile(list(values), fraction)
    return "" if value is None else str(value)


def heartbeat_fields(
    stats: CopyStats, *, now: datetime, open_count: int, queue_depth: int, outbox_depth: int = 0
) -> dict[str, str]:
    per_leader = {
        wallet: {
            "events": c.events,
            "entries": c.entries,
            "exits": c.exits,
            "censored": c.censored,
            "last_event_at": "" if c.last_event_at is None else ms_iso(c.last_event_at),
        }
        for wallet, c in stats.leaders.items()
    }
    fields: dict[str, str] = {
        "leaders": str(len(stats.leaders)),
        "events_seen": str(stats.events_seen),
        "open": str(open_count),
        "entries": str(stats.entries),
        "exits": str(stats.exits),
        "censored": str(sum(stats.censored_by_reason.values())),
        "censored_by_reason": json.dumps(dict(stats.censored_by_reason), sort_keys=True),
        "skipped_by_reason": json.dumps(dict(stats.skipped_by_reason), sort_keys=True),
        "rejected_by_reason": json.dumps(dict(stats.rejected_by_reason), sort_keys=True),
        "funnel_collisions": str(stats.funnel_collisions),
        "invalidated": str(stats.invalidated),
        "gaps_seen": str(stats.gaps_seen),
        "last_event_at": "" if stats.last_event_at is None else ms_iso(stats.last_event_at),
        "per_leader": json.dumps(per_leader, sort_keys=True),
        "persist_queue_depth": str(queue_depth),
        "persist_dropped": str(stats.persist_dropped),
        "queue_full": str(stats.queue_full),
        "outbox_depth": str(outbox_depth),
        "outbox_dropped": str(stats.outbox_dropped),
        "closed_elsewhere": str(stats.closed_elsewhere),
        "bad_items": str(stats.bad_items),
        "last_error": stats.last_error,
        "decide_us_p99": _int(stats.decide_us, 0.99),
        "confirm_delay_ms_p50": _int(stats.confirm_delay_ms, 0.50),
        "confirm_delay_ms_p95": _int(stats.confirm_delay_ms, 0.95),
        "decided_to_priced_ms_p50": _int(stats.decided_to_priced_ms, 0.50),
        "decided_to_priced_ms_p95": _int(stats.decided_to_priced_ms, 0.95),
        "persist_ms_p95": _int(stats.persist_ms, 0.95),
    }
    for name, samples in (
        ("observed_to_decided_ms", stats.observed_to_decided_us),
        ("block_to_decided_ms", stats.block_to_decided_us),
        ("fields_to_decided_ms", stats.fields_to_decided_us),
    ):
        for label, fraction in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
            fields[f"{name}_{label}"] = _ms(samples, fraction)
    return {HEARTBEAT_PREFIX + key: value for key, value in fields.items()}
