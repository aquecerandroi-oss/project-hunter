"""pump.fun realtime latency probe (2026-10-06) — from a capture's events to the numbers. Pure: no IO.

Conventions (docs in ``pumpfun_rt_probe_stats``): a delta ``a_vs_b`` is ``t_a - t_b`` on the same local clock,
positive = ``a`` delivered later. Creations are keyed by signature (NATS ``tx``, PumpPortal ``signature``,
``logsSubscribe`` signature) and the board feed by mint; the cohort is every id whose *first* arrival (any
source) falls inside the interior window, and each source's arrival is then looked up over the whole capture,
so an arrival that straddles the window edge still finds its partner. Trades live in
``pumpfun_rt_probe_trades`` (exposure intervals, program split, replay-like frames).
"""

from __future__ import annotations

import json
import statistics
from typing import Any, cast

from pumpfun_rt_probe_stats import (
    Event,
    describe,
    drop_stalls,
    first_seen,
    pair_report,
    union_coverage,
)
from pumpfun_rt_probe_trades import END_GUARD_S, analyze_trades

WARMUP_S, COOLDOWN_S, LONG_STALL_S = 90.0, 15.0, 60.0


def _entry(e: Event) -> dict[str, Any]:
    v = e.get("entry")
    return cast("dict[str, Any]", v) if isinstance(v, dict) else {}


def _window(events: list[Event], t0: float, t1: float) -> list[Event]:
    return [e for e in events if t0 <= e["t"] <= t1]


def _sel(events: list[Event], source: str, kind: str) -> list[Event]:
    return [e for e in events if e["s"] == source and e["k"] == kind]


def _clock(events: list[Event]) -> dict[str, Any]:
    samples = _sel(events, "clock", "sample")
    offsets = [e["offset"] for e in samples]
    rtts = [e["rtt"] for e in samples]
    return {
        "samples": len(samples),
        "offset_s": statistics.median(offsets) if offsets else 0.0,
        "offset_min_s": min(offsets) if offsets else None,
        "offset_max_s": max(offsets) if offsets else None,
        "rtt_median_s": statistics.median(rtts) if rtts else None,
    }


def _first_by(events: list[Event], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in sorted(events, key=lambda x: x["t"]):
        k = e.get(key)
        if isinstance(k, str):
            out.setdefault(k, e["t"])
    return out


def _cohort(seen: dict[str, dict[str, float]], t0: float, t1: float) -> set[str]:
    """Ids whose first arrival, over every source, lies in ``[t0, t1 - END_GUARD_S]``."""
    first: dict[str, float] = {}
    for src in seen.values():
        for k, t in src.items():
            first[k] = min(first.get(k, t), t)
    return {k for k, t in first.items() if t0 <= t <= t1 - END_GUARD_S}


def _only(seen: dict[str, float], keep: set[str]) -> dict[str, float]:
    return {k: t for k, t in seen.items() if k in keep}


def _creates(events: list[Event], t0: float, t1: float) -> dict[str, Any]:
    nats_ev = [e for e in _sel(events, "nats_u", "create") if e.get("program") == "pump"]
    pp_ev = [e for e in _sel(events, "pp", "create") if e.get("pool") == "pump"]
    rpc_ev = [e for e in _sel(events, "rpc", "logs") if e.get("create")]
    nats_a = first_seen(nats_ev, "nats_u", "create")
    pp_a = first_seen(pp_ev, "pp", "create")
    rpc_a = first_seen(rpc_ev, "rpc", "logs")
    keep = _cohort({"nats_u": nats_a, "pp": pp_a, "rpc": rpc_a}, t0, t1)
    nats, pp, rpc = _only(nats_a, keep), _only(pp_a, keep), _only(rpc_a, keep)
    nats_all_m = _first_by(nats_ev, "mint")
    tr_all = _first_by(
        [e for e in _sel(events, "tr_new", "add") if _entry(e).get("pg") == "pump"], "id"
    )
    keep_m = _cohort({"nats": nats_all_m, "tr": tr_all}, t0, t1)
    nats_m, tr = _only(nats_all_m, keep_m), _only(tr_all, keep_m)
    return {
        "coverage": union_coverage({"nats_u": nats, "pp": pp, "rpc": rpc}),
        "pairs": {
            "pp_vs_nats": pair_report(pp, nats),
            "rpc_vs_nats": pair_report(rpc, nats),
            "rpc_vs_pp": pair_report(rpc, pp),
            "tr_new_vs_nats": pair_report(tr, nats_m),  # by mint: the board has no signature
        },
        "tr_new_seen_of_nats_mints": (len(tr.keys() & nats_m.keys()) / len(nats_m))
        if nats_m
        else None,
        "nats_mints": len(nats_m),
    }


def _migration(events: list[Event], t0: float, t1: float) -> dict[str, Any]:
    pp_a = _first_by(_sel(events, "pp", "migration"), "mint")
    tr_a = _first_by(_sel(events, "tr_grad", "add"), "id")
    keep = _cohort({"pp": pp_a, "tr": tr_a}, t0, t1)
    pp, tr = _only(pp_a, keep), _only(tr_a, keep)
    return {"pp_migrations": len(pp), "tr_grad_adds": len(tr), "tr_grad_vs_pp": pair_report(tr, pp)}


def _kol(events: list[Event], t0: float, t1: float) -> dict[str, Any]:
    """Distinct coins at their *first* add in the window (a coin can come back to the board)."""
    add_events = [
        e for e in _window(_sel(events, "tr_new", "add"), t0, t1) if _entry(e).get("pg") == "pump"
    ]
    first_add: dict[str, Event] = {}
    for e in sorted(add_events, key=lambda x: x["t"]):
        first_add.setdefault(e["id"], e)
    delays: dict[str, float] = {}
    for e in sorted(_sel(events, "tr_new", "kol"), key=lambda x: x["t"]):
        a = first_add.get(e["id"])
        if a is not None and (e.get("kol") or 0) > 0 and e["t"] >= a["t"]:
            delays.setdefault(e["id"], e["t"] - a["t"])
    return {
        "add_events_pump": len(add_events),
        "adds_pump": len(first_add),
        "kol_gt0_at_add": sum(1 for e in first_add.values() if (_entry(e).get("kol") or 0) > 0),
        "kol_updates": len(_sel(events, "tr_new", "kol")),
        "kol_update_delay_s": describe(list(delays.values())),
    }


def _health(events: list[Event]) -> dict[str, dict[str, int]]:
    """Connection events per source inside the analysed segment (drops, refusals, send failures)."""
    out: dict[str, dict[str, int]] = {}
    for e in events:
        if e["k"] == "sys" and e["id"] not in ("connect", "ready"):
            d = out.setdefault(e["s"], {})
            d[e["id"]] = d.get(e["id"], 0) + 1
    return out


def _block_time_check(events: list[Event], blocktime: dict[str, int | None]) -> dict[str, Any]:
    by_slot: dict[int, float] = {}
    for e in _sel(events, "nats_u", "trade"):
        if isinstance(e.get("slot"), int) and isinstance(e.get("bt"), (int, float)):
            by_slot.setdefault(e["slot"], e["bt"])
    diffs = [
        by_slot[int(s)] - v for s, v in blocktime.items() if v and s.isdigit() and int(s) in by_slot
    ]
    return {"n": len(diffs), "nats_minus_chain_s": describe(diffs)}


def _segment(
    started: float, ended: float, stalls: list[tuple[float, float]]
) -> tuple[float, float, int]:
    """A stall longer than ``LONG_STALL_S`` (a sleeping machine) breaks the capture; the sockets died and
    came back cold, so only the longest unbroken segment is analysed."""
    cuts = sorted((a, b) for a, b in stalls if b - a > LONG_STALL_S)
    bounds: list[tuple[float, float]] = []
    cur = started
    for a, b in cuts:
        bounds.append((cur, a))
        cur = b
    bounds.append((cur, ended))
    best = max(bounds, key=lambda x: x[1] - x[0])
    return best[0], best[1], len(bounds)


def analyze(
    events: list[Event], meta: dict[str, Any], blocktime: dict[str, int | None]
) -> dict[str, Any]:
    stalls = [(float(a), float(b)) for a, b in meta.get("stalls", [])]
    seg_start, seg_end, n_segments = _segment(float(meta["started"]), float(meta["ended"]), stalls)
    t0, t1 = seg_start + WARMUP_S, seg_end - COOLDOWN_S
    if t1 - t0 <= END_GUARD_S:
        raise ValueError(f"analysis window too short: {t1 - t0:.0f} s after warm-up and cool-down")
    inside = [e for e in events if seg_start <= e["t"] <= seg_end]
    evs = drop_stalls(inside, stalls)
    clock = _clock(evs)
    return {
        "segment": {"start": seg_start, "end": seg_end, "segments": n_segments},
        "window_s": t1 - t0,
        "stalls_dropped": len(events) - len(evs),
        "clock": clock,
        "create": _creates(evs, t0, t1),
        "trade": analyze_trades(evs, t0, t1, clock["offset_s"]),
        "migration": _migration(evs, t0, t1),
        "kol": _kol(evs, t0, t1),
        "block_time_check": _block_time_check(evs, blocktime),
        "health": _health(evs),
    }


def entry_fields(events: list[Event], source: str) -> list[str]:
    """Union of the wire keys of the board entries a trenches source added."""
    keys: set[str] = set()
    for e in _sel(events, source, "add"):
        keys |= set(_entry(e))
    return sorted(keys)


def sample_fields(samples: dict[str, list[str]]) -> dict[str, list[str]]:
    """Top-level keys of the first parseable JSON sample of each group (the field inventory)."""
    out: dict[str, list[str]] = {}
    for name, raws in samples.items():
        for raw in raws:
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out[name] = sorted(cast("dict[str, Any]", obj))
                break
    return out
