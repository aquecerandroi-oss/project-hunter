"""Latency distributions of the leader source (H-037): what Everton's "milliseconds" is measured by.

* ``receive_to_emit`` — socket receive of a NATS frame (stamped before any parsing) -> the event
  handed to the consumer's queue. Pure in-process time, measured on the monotonic clock.
* ``first_seen_to_deliver`` — our first sight of a NATS event -> the combined stream yielding it to the
  consumer (the whole in-process path, including the queues).
* ``nats_to_confirm`` — NATS first sight of an event -> its ``confirmed`` LeaderConfirmation received.

Bounded window (the last ``window`` samples) for percentiles; the count is the total ever recorded.
"""

from __future__ import annotations

from collections import Counter, deque
from typing import Any


class LatencyDist:
    def __init__(self, window: int = 4096) -> None:
        self._samples: deque[float] = deque(maxlen=window)
        self._window = window
        self._n = 0

    def record(self, seconds: float) -> None:
        self._samples.append(max(0.0, seconds))
        self._n += 1

    def summary(self) -> dict[str, Any]:
        if not self._samples:
            return {"n": 0}
        ordered = sorted(self._samples)

        def pct(p: float) -> float:
            rank = -(-len(ordered) * p // 100)  # nearest rank, ceil
            return round(ordered[max(0, int(rank) - 1)] * 1000, 3)

        return {
            "n": self._n,
            "window": len(ordered),
            "min_ms": round(ordered[0] * 1000, 3),
            "p50_ms": pct(50),
            "p90_ms": pct(90),
            "p99_ms": pct(99),
            "max_ms": round(ordered[-1] * 1000, 3),
        }


class LeaderSourceStats:
    def __init__(self) -> None:
        self.receive_to_emit = LatencyDist()
        self.nats_to_confirm = LatencyDist()
        self.first_seen_to_deliver = LatencyDist()
        self.counters: Counter[str] = Counter()

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] += n

    def snapshot(self) -> dict[str, Any]:
        return {
            "receive_to_emit": self.receive_to_emit.summary(),
            "nats_to_confirm": self.nats_to_confirm.summary(),
            "first_seen_to_deliver": self.first_seen_to_deliver.summary(),
            "counters": dict(self.counters),
        }
