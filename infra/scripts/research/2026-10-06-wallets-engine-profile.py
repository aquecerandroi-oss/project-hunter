"""Reproducible CPU profile of the H-030 bounded wallets engine (CPU plan step 1, 06/10/2026).

SYNTHETIC — NOT MARKET DATA (generator ``kb0183-shape-v2``, ``2026-10-06-wallets-engine-gen.py``).
Runs a sliding window's nights from the origin and measures ONLY the last night's stream call:
0. **bare** — CPU (``process_time``) and wall of the call, nothing wrapped, ``--repeat`` times back
   to back (min kept; the engine's memo is emptied before every measured call);
1. **passes** — again, each pass timed by ``perf_counter`` through thin wrappers (single thread, no
   IO: wall ≈ CPU; Windows' ``process_time`` ticks at 15.6 ms): survey (+ links/entities), bets,
   replay (books, W-PnL FIFO, tallies, copies), carry advance, assembly; ``_prepared`` by caller;
   per-mint replay cost to read the scaling;
2. **cProfile** of the same call: top own time and call counts (copies, stop quotes, and all
   function calls — deterministic work, immune to a loaded machine).
The header freezes revision, engine source digest, Python, platform, CPU and the configuration.
Run: ``uv run python infra/scripts/research/2026-10-06-wallets-engine-profile.py --matrix step1``.
"""

from __future__ import annotations

import argparse
import cProfile
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import platform
import pstats
import subprocess
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from hunter_indicators.meme.wallets import stream, stream_mint
from hunter_indicators.meme.wallets.carry import MintCarry, canonical_order, initial_carry
from hunter_indicators.meme.wallets.leakage import fingerprint
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.ranking import cut_of
from hunter_indicators.meme.wallets.stream import MintWindow, StreamInputs, StreamResult
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location(
    "wgen", Path(__file__).with_name("2026-10-06-wallets-engine-gen.py")
)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
sys.modules["wgen"] = gen
_spec.loader.exec_module(gen)

MATRIX: dict[str, list[dict[str, Any]]] = {
    "smoke": [{"name": "smoke", "per_day": 2_000}],
    "base": [{"name": "base"}],
    "step1": [
        {"name": "base"}, {"name": "seed2", "seed": 2}, {"name": "seed3", "seed": 3},
        {"name": "fills_4k", "per_day": 4_000}, {"name": "fills_16k", "per_day": 16_000},
        {"name": "entities_x0.5", "wallet_scale": 0.5}, {"name": "entities_x2", "wallet_scale": 2.0},
        {"name": "hot_1k", "hot_fills": 1_000}, {"name": "hot_2k", "hot_fills": 2_000},
        {"name": "hot_4k", "hot_fills": 4_000},
        {"name": "triggers_0.1", "trigger_share": 0.1}, {"name": "triggers_0.7", "trigger_share": 0.7},
        {"name": "history_3d", "days": 6}, {"name": "history_5d", "days": 8},
        {"name": "burst_10", "bursts": 20, "burst_size": 10},
        {"name": "burst_40", "bursts": 20, "burst_size": 40},
        {"name": "burst_120", "bursts": 20, "burst_size": 120},
        {"name": "empty_window_big_carry", "days": 8, "quiet": True},
        {"name": "window7", "per_day": 2_000, "days": 9, "window": 7},
    ],
}  # fmt: skip
WATCH = ("_stopped", "quote_stopped", "stop_limit", "_find_exit", "_leader_exit", "simulate_copy", "window_books", "fifo",
         "liquidation_or_none", "_prepared", "_cobuys", "flow_of", "_advance", "__init__")  # fmt: skip


def frozen_env() -> dict[str, str]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip()

    # the engine actually imported (a stage copy when run with PYTHONPATH)
    here = Path(stream.__file__).parent
    digest = hashlib.sha256()
    for p in [*sorted(here.glob("*.py")), here.parent / "curve.py"]:
        digest.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return {
        "revision": git("rev-parse", "HEAD"),
        "engine_dirty": git("status", "--porcelain", "packages/indicators/hunter_indicators/meme")
        .replace("\n", " ") or "clean",
        "engine_path": str(here), "engine_sha256_lf": digest.hexdigest()[:16],
        "python": sys.version.split()[0],
        "platform": platform.platform(), "cpu": platform.processor(),
        "cpu_count": str(os.cpu_count()), "generator": gen.LABEL, "argv": " ".join(sys.argv[1:]),
    }  # fmt: skip


def peak_rss_mb() -> float | None:
    """Process peak RSS of the WHOLE process (generated tape, earlier nights, harness), not the
    engine's increment; ``None`` when the OS call fails (Astra: it silently read 0 before the
    signatures were declared)."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class _Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (n, ctypes.c_size_t) for n in ("peak_ws", "ws", "a", "b", "c", "d", "e", "f")]  # fmt: skip

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
        psapi = ctypes.WinDLL("psapi", use_last_error=True)  # type: ignore[attr-defined]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        c = _Counters()
        c.cb = ctypes.sizeof(c)
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return None
        return c.peak_ws / 1e6
    import resource

    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e3


class Timers:
    def __init__(self) -> None:
        self.t: dict[str, list[float]] = {}
        self.current = "other"
        self.mints: list[tuple[str, int, int, float]] = []  # mint, fills, copies, wall s
        self.copies = 0
        self.bets = self.pairs = 0

    def add(self, name: str, cpu: float, wall: float) -> None:
        row = self.t.setdefault(name, [0.0, 0.0, 0])
        row[0] += cpu
        row[1] += wall
        row[2] += 1

    def wrap(self, name: str, fn: Callable[..., Any], *, phase: bool = False) -> Callable[..., Any]:
        def inner(*args: Any, **kw: Any) -> Any:
            before, c0, w0 = self.current, time.process_time(), time.perf_counter()
            if phase:
                self.current = name
            try:
                return fn(*args, **kw)
            finally:
                self.current = before
                self.add(name, time.process_time() - c0, time.perf_counter() - w0)

        return inner


@contextmanager
def instrumented(tm: Timers) -> Generator[None]:
    saved_s = {n: getattr(stream, n) for n in ("_survey", "_bets", "_weak", "entities_as_of",
                                               "_fee_seeds", "replay_mint", "assemble_snapshot", "_prepared")}  # fmt: skip
    saved_m = {
        n: getattr(stream_mint, n) for n in ("_advance", "simulate_copy", "window_books", "fifo")
    }
    prepared = saved_s["_prepared"]

    def prep(*a: Any, **k: Any) -> Any:
        return tm.wrap(f"_prepared[{tm.current}]", prepared)(*a, **k)

    def survey(*a: Any, **k: Any) -> Any:
        out = tm.wrap("survey", saved_s["_survey"], phase=True)(*a, **k)
        tm.pairs = len(out.pairs)
        return out

    def bets(*a: Any, **k: Any) -> Any:
        out = tm.wrap("bets", saved_s["_bets"], phase=True)(*a, **k)
        tm.bets = sum(len(v) for v in out[0].values())  # per mint since step 3
        return out

    def replay(carry: MintCarry, fills: tuple[Fill, ...], *a: Any) -> Any:
        w0, k0 = time.perf_counter(), tm.copies
        out = tm.wrap("replay(total)", saved_s["replay_mint"], phase=True)(carry, fills, *a)
        tm.mints.append((carry.mint, len(fills), tm.copies - k0, time.perf_counter() - w0))
        return out

    def copy(*a: Any, **k: Any) -> Any:
        tm.copies += 1
        return tm.wrap("replay.copies", saved_m["simulate_copy"])(*a, **k)

    patches_s = {"_survey": survey, "_bets": bets, "replay_mint": replay, "_prepared": prep,
                 "_weak": tm.wrap("links(_weak)", saved_s["_weak"]),
                 "entities_as_of": tm.wrap("entities_as_of", saved_s["entities_as_of"]),
                 "_fee_seeds": tm.wrap("fee_seeds", saved_s["_fee_seeds"]),
                 "assemble_snapshot": tm.wrap("assemble_snapshot", saved_s["assemble_snapshot"])}  # fmt: skip
    patches_m = {"_advance": tm.wrap("replay.carry_advance", saved_m["_advance"]),
                 "simulate_copy": copy, "window_books": tm.wrap("replay.window_books", saved_m["window_books"]),
                 "fifo": tm.wrap("replay.fifo(w_pnl)", saved_m["fifo"])}  # fmt: skip
    for n, f in patches_s.items():
        setattr(stream, n, f)
    for n, f in patches_m.items():
        setattr(stream_mint, n, f)
    try:
        yield
    finally:
        for n, f in saved_s.items():
            setattr(stream, n, f)
        for n, f in saved_m.items():
            setattr(stream_mint, n, f)


def _windows(by_mint: dict[str, list[Fill]], creates: dict[str, list[CreateEvent]],
             carries: dict[str, MintCarry], start: Any) -> list[MintWindow]:  # fmt: skip
    return [
        MintWindow(carries.get(m, MintCarry(m)),
                   tuple(f for f in by_mint.get(m, ()) if f.received_at >= start),
                   tuple(c for c in creates.get(m, ()) if c.received_at >= start))
        for m in sorted({*carries, *by_mint})
    ]  # fmt: skip


def run(cfg: Any, top: int, profile: bool = True, repeat: int = 1) -> tuple[dict[str, Any], str]:
    fills, creates = gen.generate(cfg)
    params, policy = RankingParams(window_days=cfg.window), FollowPolicy()
    by_mint: dict[str, list[Fill]] = {}
    for f in sorted(fills, key=canonical_order):
        by_mint.setdefault(f.mint, []).append(f)
    c_by: dict[str, list[CreateEvent]] = {}
    for c in creates:
        c_by.setdefault(c.mint, []).append(c)
    shared = stream.shared_signatures(fills)
    carry, first = initial_carry(gen.T0, window_days=cfg.window)
    carries = {m.mint: m for m in first}
    nights: list[date] = [(gen.T0 + timedelta(days=k)).date() for k in range(cfg.window, cfg.days)]
    for day in nights[:-1]:
        ws = _windows(by_mint, c_by, carries, cut_of(day) - timedelta(days=cfg.window))
        out = stream.stream_snapshot(
            StreamInputs(carry, lambda w=ws: iter(w), shared), day, params=params
        )
        carry, carries = out.carry, {m.mint: m for m in out.mint_carries}
    last = nights[-1]
    start = cut_of(last) - timedelta(days=cfg.window)
    ws = _windows(by_mint, c_by, carries, start)
    inputs = StreamInputs(carry, lambda: iter(ws), shared)
    runs: list[tuple[float, float]] = []  # bare (nothing wrapped), ``repeat`` times back to back
    result: StreamResult | None = None
    for _ in range(max(1, repeat)):
        cold()  # every measured call starts with the same (empty) memo, whatever the stage
        c0, w0 = time.process_time(), time.perf_counter()
        result = stream.stream_snapshot(inputs, last, policy=policy, params=params)
        runs.append((time.process_time() - c0, time.perf_counter() - w0))
    assert result is not None
    cpu, wall = min(runs)
    tm = Timers()
    cold()
    with instrumented(tm):
        c1, w1 = time.process_time(), time.perf_counter()
        again = stream.stream_snapshot(inputs, last, policy=policy, params=params)
        wrapped_cpu, wrapped_wall = time.process_time() - c1, time.perf_counter() - w1
    assert again.snapshot == result.snapshot
    calls: dict[str, int] = {}
    buf, prof_wall = io.StringIO(), 0.0
    if profile:
        cold()
        prof = cProfile.Profile()
        w1 = time.perf_counter()
        prof.enable()
        again = stream.stream_snapshot(inputs, last, policy=policy, params=params)
        prof.disable()
        prof_wall = time.perf_counter() - w1
        assert again.snapshot == result.snapshot
        st = pstats.Stats(prof)
        calls = {f"{Path(k[0]).stem}.{k[2]}": v[1] for k, v in st.stats.items() if k[2] in WATCH}  # type: ignore[attr-defined]
        calls["ALL_FUNCTION_CALLS"] = st.total_calls  # type: ignore[attr-defined]  # deterministic work
        pstats.Stats(prof, stream=buf).sort_stats("tottime").print_stats(top)
    window_fills = sum(1 for w in ws for f in w.fills if start <= f.block_time < cut_of(last))
    mints = result.mint_carries
    row: dict[str, Any] = {
        "config": asdict(cfg), "window_fills": window_fills, "window_mints": len(ws),
        "largest_mint_fills": max((len(w.fills) for w in ws), default=0),
        "entities": len(result.snapshot.rows), "bets": tm.bets, "copies": tm.copies,
        "same_slot_pairs": tm.pairs, "carry_lots": sum(len(m.lots) for m in mints),
        "carry_flows": sum(len(m.flows) for m in mints), "carry_pending": len(result.carry.pending),
        "cpu_s": cpu, "wall_s": wall, "bare_runs": runs, "wrapped_cpu_s": wrapped_cpu,
        "wrapped_wall_s": wrapped_wall, "profiled_wall_s": prof_wall,
        "us_per_window_fill": 1e6 * cpu / max(1, window_fills),
        "passes": {k: {"cpu_s": round(v[0], 4), "wall_s": round(v[1], 4), "calls": int(v[2])}
                   for k, v in sorted(tm.t.items())},
        "calls": calls, "census": gen.census([f for w in ws for f in w.fills]),
        "top_mints": sorted(tm.mints, key=lambda m: -m[3])[:5], "peak_rss_mb": peak_rss_mb(),
        "snapshot_digest": hashlib.sha256(repr(fingerprint(result.snapshot)).encode()).hexdigest()[:16],
    }  # fmt: skip
    return row, buf.getvalue()


def cold() -> None:
    """Empty the engine's memo (``pricing._curve_of``, step 2 change F) when the stage has it."""
    pricing = importlib.import_module("hunter_indicators.meme.wallets.pricing")
    if (memo := getattr(pricing, "_curve_of", None)) is not None:
        memo.cache_clear()


def table(row: dict[str, Any]) -> str:
    p, total = row["passes"], row["wrapped_wall_s"] or 1e-9

    def g(k: str) -> float:
        return p.get(k, {}).get("wall_s", 0.0)

    replay = g("replay(total)")
    parts = {
        "survey (+_prepared)": g("survey"), "links+entities": g("links(_weak)") + g("entities_as_of"),
        "bets (+_prepared)": g("bets"), "fee seeds": g("fee_seeds"),
        "replay: window_books (E-PnL)": g("replay.window_books"), "replay: fifo (W-PnL)": g("replay.fifo(w_pnl)"),
        "replay: copies (simulate_copy)": g("replay.copies"), "replay: carry advance": g("replay.carry_advance"),
        "replay loop: _prepared (3rd pass)": g("_prepared[other]"),
        "replay: rest (tape, tallies, loop)": replay - g("replay.window_books") - g("replay.fifo(w_pnl)")
        - g("replay.copies") - g("replay.carry_advance"),
        "assembly (metrics, rank)": g("assemble_snapshot"),
    }  # fmt: skip
    parts["unattributed"] = total - sum(parts.values())
    lines = [f"  {k:<36} {v:8.3f} s  {100 * v / total:5.1f} %" for k, v in parts.items()]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="base", choices=sorted(MATRIX))
    ap.add_argument("--only", default="", help="comma-separated config names")
    ap.add_argument("--top", type=int, default=18)
    ap.add_argument("--out", default="")
    ap.add_argument("--timing-only", action="store_true", help="skip the cProfile run")
    ap.add_argument("--repeat", type=int, default=1, help="bare runs back to back; min kept")
    args = ap.parse_args()
    env = frozen_env()
    lines = ["SYNTHETIC profile (not market data) — wallets engine 1c-bis, CPU plan step 1",
             "ENV " + json.dumps(env)]  # fmt: skip
    print("\n".join(lines), flush=True)
    for spec in MATRIX[args.matrix]:
        if args.only and spec["name"] not in args.only.split(","):
            continue
        cfg = replace(gen.Config(), **spec)
        row, prof = run(cfg, args.top, profile=not args.timing_only, repeat=args.repeat)
        block = [f"\n=== {cfg.name} ===", "ROW " + json.dumps(row, default=str),
                 f"  cpu {row['cpu_s']:.3f} s  wall {row['wall_s']:.3f} s  window fills {row['window_fills']}"
                 f"  -> {row['us_per_window_fill']:.1f} us CPU/fill  copies {row['copies']}"
                 f"  stop quotes {row['calls'].get('policy._stopped', 0) + row['calls'].get('stops.quote_stopped', 0)}", table(row), prof]  # fmt: skip
        print("\n".join(block), flush=True)
        lines += block
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
