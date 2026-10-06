"""pump.fun realtime latency probe (2026-10-06) — the pure statistics half, no IO, no clock.

Every observed frame becomes an event dict ``{"s": source, "k": kind, "id": signature-or-mint, "t": local
wall clock (s, UTC epoch) at the moment the frame woke the reader, ...}``. Deltas between sources are taken
on the **same machine, same process, same clock**, so the local clock's skew against the world cancels in
every pairwise number; only the "delay against block time" figures need the skew (``pump.fun/api/server-time``).
A positive delta ``t_a - t_b`` means source ``a`` delivered the event *later* than ``b``.
"""

from __future__ import annotations

from typing import Any

Event = dict[str, Any]
Interval = tuple[float, float]


def percentile(xs: list[float], q: float) -> float | None:
    """Linear interpolation between order statistics (numpy default); ``None`` on no data."""
    if not xs:
        return None
    s = sorted(xs)
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def describe(xs: list[float]) -> dict[str, Any]:
    return {
        "n": len(xs),
        "p10": percentile(xs, 0.10),
        "p50": percentile(xs, 0.50),
        "p90": percentile(xs, 0.90),
    }


def first_seen(
    events: list[Event], source: str, kind: str, *, t0: float = 0.0, t1: float = float("inf")
) -> dict[str, float]:
    """Earliest arrival per id for one (source, kind) inside ``[t0, t1]``."""
    out: dict[str, float] = {}
    for e in events:
        if e["s"] != source or e["k"] != kind or not (t0 <= e["t"] <= t1):
            continue
        prev = out.get(e["id"])
        if prev is None or e["t"] < prev:
            out[e["id"]] = e["t"]
    return out


def drop_stalls(events: list[Event], stalls: list[Interval]) -> list[Event]:
    """Events that arrived while the process itself was frozen (sleep, loop stall) say nothing about the
    sources: they are removed before any delta is taken."""
    return [e for e in events if not any(a <= e["t"] <= b for a, b in stalls)]


TIE_S = (
    0.010  # a difference under 10 ms is a tie: below the clock stamping and the loop's own jitter
)


def pair_report(a: dict[str, float], b: dict[str, float], tie_s: float = TIE_S) -> dict[str, Any]:
    """``a`` vs ``b`` over the ids both saw: deltas ``t_a - t_b`` (positive = ``a`` later) and, over the common
    ids, the share ``a`` delivered first, ``b`` delivered first, and tied (within ``tie_s``)."""
    common = a.keys() & b.keys()
    deltas = [a[i] - b[i] for i in common]
    n = len(deltas)

    def share(count: int) -> float | None:
        return (count / n) if n else None

    return {
        "common": len(common),
        "only_a": len(a.keys() - b.keys()),
        "only_b": len(b.keys() - a.keys()),
        "delta_s": describe(deltas),
        "a_first_share": share(sum(1 for d in deltas if d < -tie_s)),
        "b_first_share": share(sum(1 for d in deltas if d > tie_s)),
        "tie_share": share(sum(1 for d in deltas if abs(d) <= tie_s)),
    }


def union_coverage(seen: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Each source's share of the union of ids any source saw, and how many ids all of them saw."""
    union: set[str] = set()
    for s in seen.values():
        union |= s.keys()
    n = len(union)
    in_all = set(union)
    for s in seen.values():
        in_all &= s.keys()
    return {
        "union": n,
        "in_all": len(in_all),
        "by_source": {
            name: {"seen": len(s), "share": (len(s) / n) if n else None} for name, s in seen.items()
        },
    }
