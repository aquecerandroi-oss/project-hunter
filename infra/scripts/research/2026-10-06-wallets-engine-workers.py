"""1 vs 2 worker processes for the H-030 bounded wallets engine (CPU plan step 3, 06/10/2026).

SYNTHETIC — NOT MARKET DATA (generator ``kb0183-shape-v2``, ``2026-10-06-wallets-engine-gen.py``).
Per config, the nights before the last are streamed serially from the origin; the LAST night is
then measured in three modes, interleaved, the order alternating per round (the machine is shared
and noisy, so the minimum per mode is kept and every round is printed):

- ``serial`` — :func:`stream.stream_snapshot` in this process;
- ``w1`` / ``w2`` — :func:`stream_parallel.stream_snapshot_parallel` with 1 or 2 spawned workers.
  Workers load each mint from a per-mint pickle file (``FileFetch``), so they never hold the world.

Measured: wall; coordinator CPU (``process_time``); per worker CPU (kernel + user) and peak working
set, read from a process handle kept open past the worker's exit (Windows; ``None`` elsewhere);
worker startup CPU (spawn + imports + night unpickle, at its first fetch); the coordinator's
serial part (plan = passes 1–2, finish = assembly) as wall and thread CPU, in both modes; the
largest mint's replay alone (the critical path); and the result digest of each mode (asserted
equal). ``--traced`` adds one
``tracemalloc`` run per mode for the coordinator's Python heap peak (source excluded).
Run: ``uv run python infra/scripts/research/2026-10-06-wallets-engine-workers.py --out <file>``.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
import pickle
import sys
import tempfile
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass, replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from hunter_indicators.meme.wallets import pricing, stream, stream_parallel
from hunter_indicators.meme.wallets.carry import MintCarry, canonical_order, initial_carry
from hunter_indicators.meme.wallets.carry_codec import carry_to_json
from hunter_indicators.meme.wallets.leakage import fingerprint
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.ranking import cut_of
from hunter_indicators.meme.wallets.stream import MintWindow, StreamInputs, StreamResult
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill

_spec = importlib.util.spec_from_file_location(
    "wgen", Path(__file__).with_name("2026-10-06-wallets-engine-gen.py")
)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
sys.modules["wgen"] = gen
_spec.loader.exec_module(gen)

CONFIGS: list[dict[str, Any]] = [
    {"name": "base"}, {"name": "hot_4k", "hot_fills": 4_000},
    {"name": "triggers_0.7", "trigger_share": 0.7}, {"name": "fills_16k", "per_day": 16_000},
    {"name": "window7", "per_day": 2_000, "days": 9, "window": 7},
    {"name": "empty_window_big_carry", "days": 8, "quiet": True},
]  # fmt: skip


@dataclass(frozen=True)
class FileFetch:
    """Loads a mint's window from its pickle file; records the worker pid and its CPU at the
    first load (startup = interpreter + imports + the night unpickled by the initializer)."""

    folder: str
    files: dict[str, str]

    def __call__(self, name: str) -> MintWindow:
        mark = Path(self.folder) / "pids" / f"pid-{os.getpid()}"  # own folder: cheap to poll
        if not mark.exists():
            mark.write_text(f"{time.process_time():.6f}", encoding="utf-8")
        return pickle.loads((Path(self.folder) / self.files[name]).read_bytes())  # noqa: S301 — own files


class Children:
    """Opens a handle to every worker as its pid file appears; reads CPU and peak working set
    after the run (an exited process stays queryable while a handle is open)."""

    _ACCESS = 0x1000 | 0x0400 | 0x0010  # QUERY_LIMITED | QUERY_INFORMATION | VM_READ

    def __init__(self, folder: str) -> None:
        self.folder, self.handles, self.stop = Path(folder), dict[int, int](), threading.Event()
        self.ok = sys.platform == "win32"
        if self.ok:
            from ctypes import wintypes

            self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
            self.psapi = ctypes.WinDLL("psapi", use_last_error=True)  # type: ignore[attr-defined]
            self.k32.OpenProcess.restype = wintypes.HANDLE
            self.k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            self.k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.c_void_p] * 4
            self.k32.GetProcessTimes.restype = wintypes.BOOL
            self.k32.CloseHandle.argtypes = [wintypes.HANDLE]
            self.psapi.GetProcessMemoryInfo.argtypes = [
                wintypes.HANDLE,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            self.psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        self.thread = threading.Thread(target=self._poll, daemon=True)

    def _poll(self) -> None:
        while not self.stop.is_set():
            for mark in self.folder.glob("pid-*"):
                pid = int(mark.name[4:])
                if self.ok and pid not in self.handles:
                    self.handles[pid] = self.k32.OpenProcess(self._ACCESS, False, pid) or 0
            self.stop.wait(0.02)

    def __enter__(self) -> Children:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop.set()
        self.thread.join()

    def read(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for mark in sorted(self.folder.glob("pid-*")):
            pid, startup = int(mark.name[4:]), float(mark.read_text(encoding="utf-8"))
            row: dict[str, Any] = {
                "pid": pid,
                "startup_cpu_s": startup,
                "cpu_s": None,
                "peak_ws_mb": None,
            }
            handle = self.handles.get(pid, 0)
            if handle:
                t = (ctypes.c_ulonglong * 4)()
                if self.k32.GetProcessTimes(handle, *(ctypes.byref(t, 8 * i) for i in range(4))):
                    row["cpu_s"] = (t[2] + t[3]) / 1e7  # kernel + user, 100 ns units
                mem = (ctypes.c_size_t * 10)()
                ctypes.cast(mem, ctypes.POINTER(ctypes.c_uint32))[0] = ctypes.sizeof(mem)
                if self.psapi.GetProcessMemoryInfo(handle, mem, ctypes.sizeof(mem)):
                    row["peak_ws_mb"] = mem[1] / 1e6  # PeakWorkingSetSize (after cb + faults)
                self.k32.CloseHandle(handle)
            mark.unlink()
            out.append(row)
        self.handles.clear()
        return out


def digest(result: StreamResult) -> str:
    body = repr(fingerprint(result.snapshot)) + carry_to_json(result.carry, result.mint_carries)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def nights(cfg: Any) -> tuple[StreamInputs, list[MintWindow], Any, int]:
    fills, creates = gen.generate(cfg)
    by_mint: dict[str, list[Fill]] = {}
    for f in sorted(fills, key=canonical_order):
        by_mint.setdefault(f.mint, []).append(f)
    c_by: dict[str, list[CreateEvent]] = {}
    for c in creates:
        c_by.setdefault(c.mint, []).append(c)
    shared, params = stream.shared_signatures(fills), RankingParams(window_days=cfg.window)
    carry, first = initial_carry(gen.T0, window_days=cfg.window)
    carries: dict[str, MintCarry] = {m.mint: m for m in first}

    def windows(start: Any) -> list[MintWindow]:
        return [MintWindow(carries.get(m, MintCarry(m)),
                           tuple(f for f in by_mint.get(m, ()) if f.received_at >= start),
                           tuple(c for c in c_by.get(m, ()) if c.received_at >= start))
                for m in sorted({*carries, *by_mint})]  # fmt: skip

    days = [(gen.T0 + timedelta(days=k)).date() for k in range(cfg.window, cfg.days)]
    for day in days[:-1]:
        ws = windows(cut_of(day) - timedelta(days=cfg.window))
        out = stream.stream_snapshot(
            StreamInputs(carry, lambda w=ws: iter(w), shared), day, params=params
        )
        carry, carries = out.carry, {m.mint: m for m in out.mint_carries}
    start = cut_of(days[-1]) - timedelta(days=cfg.window)
    ws = windows(start)
    window_fills = sum(1 for w in ws for f in w.fills if start <= f.block_time < cut_of(days[-1]))
    return StreamInputs(carry, lambda: iter(ws), shared), ws, days[-1], window_fills


class SerialTimers:
    """Times the coordinator's plan (passes 1–2) and finish in either mode — wall
    (``perf_counter``) AND CPU of the calling thread (``thread_time``: the pool's and the pid
    poller's threads excluded), so the serial replay CPU = total − plan − finish (Astra, diff
    review: wall and CPU were mixed before)."""

    def __init__(self, module: Any) -> None:
        self.module, self.wall, self.cpu = (
            module,
            {"plan": 0.0, "finish": 0.0},
            {"plan": 0.0, "finish": 0.0},
        )

    def _timed(self, name: str, fn: Any) -> Any:
        def inner(*a: Any, **k: Any) -> Any:
            w0, c0 = time.perf_counter(), time.thread_time()
            try:
                return fn(*a, **k)
            finally:
                self.wall[name] += time.perf_counter() - w0
                self.cpu[name] += time.thread_time() - c0

        return inner

    def __enter__(self) -> SerialTimers:
        self.saved = (self.module.plan_night, self.module.finish_night)
        self.module.plan_night = self._timed("plan", self.saved[0])
        self.module.finish_night = self._timed("finish", self.saved[1])
        return self

    def __exit__(self, *exc: object) -> None:
        self.module.plan_night, self.module.finish_night = self.saved


def measure(
    mode: str, inputs: StreamInputs, day: Any, fetch: FileFetch, traced: bool
) -> dict[str, Any]:
    params = RankingParams(window_days=inputs.carry.window_days)
    pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]  # same cold memo for all
    row: dict[str, Any] = {"mode": mode}
    if traced:
        tracemalloc.start()
    c0, w0 = time.process_time(), time.perf_counter()
    if mode == "serial":
        with SerialTimers(stream) as st:
            result = stream.stream_snapshot(inputs, day, policy=FollowPolicy(), params=params)
    else:
        with (
            Children(str(Path(fetch.folder) / "pids")) as kids,
            SerialTimers(stream_parallel) as st,
        ):
            result = stream_parallel.stream_snapshot_parallel(
                inputs,
                day,
                policy=FollowPolicy(),
                params=params,
                fetch=fetch,
                workers=int(mode[1:]),
            )
        row.update(workers=kids.read())
    row.update(plan_wall_s=st.wall["plan"], finish_wall_s=st.wall["finish"],
               plan_cpu_s=st.cpu["plan"], finish_cpu_s=st.cpu["finish"])  # fmt: skip
    row.update(wall_s=time.perf_counter() - w0, coordinator_cpu_s=time.process_time() - c0)
    if traced:
        row["coordinator_heap_peak_mb"] = tracemalloc.get_traced_memory()[1] / 1e6
        tracemalloc.stop()
    cpus = [w["cpu_s"] for w in row.get("workers", []) if w["cpu_s"] is not None]
    row["total_cpu_s"] = row["coordinator_cpu_s"] + sum(cpus)
    row["digest"] = digest(result)
    return row


def run(cfg: Any, rounds: int, traced: bool) -> dict[str, Any]:
    inputs, ws, day, window_fills = nights(cfg)
    plan = stream.plan_night(inputs, day, params=RankingParams(window_days=cfg.window))
    largest = max(plan.order, key=plan.cost)
    window = next(w for w in ws if w.carry.mint == largest)
    pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
    t0 = time.perf_counter()
    stream.replay_window(plan, window)
    solo = time.perf_counter() - t0
    out: dict[str, Any] = {"config": asdict(cfg), "window_fills": window_fills, "mints": len(ws),
                           "bets": sum(len(v) for v in plan.bets.values()),
                           "largest_mint": {"mint": largest, "events": plan.events[largest],
                                            "replay_alone_s": solo}, "rounds": []}  # fmt: skip
    with tempfile.TemporaryDirectory(prefix="wallets-step3-") as folder:
        (Path(folder) / "pids").mkdir()
        files = {w.carry.mint: f"m{i}.pkl" for i, w in enumerate(ws)}
        for w in ws:
            (Path(folder) / files[w.carry.mint]).write_bytes(pickle.dumps(w))
        fetch = FileFetch(folder, files)
        for r in range(rounds):
            order = ["serial", "w1", "w2"] if r % 2 == 0 else ["w2", "w1", "serial"]
            out["rounds"].append([measure(m, inputs, day, fetch, traced=False) for m in order])
            print(f"  round {r}: " + "  ".join(f"{x['mode']} wall {x['wall_s']:.2f}s cpu {x['total_cpu_s']:.2f}s"
                                              for x in out["rounds"][-1]), flush=True)  # fmt: skip
        if traced:
            out["traced"] = [measure(m, inputs, day, fetch, traced=True) for m in ("serial", "w2")]
    digests = {x["digest"] for rnd in out["rounds"] for x in rnd}
    assert len(digests) == 1, f"modes disagree: {digests}"
    best = {m: min((x for rnd in out["rounds"] for x in rnd if x["mode"] == m), key=lambda x: x["wall_s"])
            for m in ("serial", "w1", "w2")}  # fmt: skip
    out["best"], out["digest"] = best, digests.pop()
    return out


def summary(out: dict[str, Any]) -> str:
    """CPU ratios from CPU only. ``f`` = (plan + finish CPU) / serial CPU; ``k`` = workers' replay
    CPU (startup excluded) / serial replay CPU (serial total − plan − finish); the idealized
    estimate (not a bound: a worker may run while another starts) = coordinator plan + finish +
    the slowest startup + max(replay / 2, the largest mint alone, measured in another call)."""
    b, n = out["best"], out["window_fills"] or 1
    s, w1, w2 = b["serial"], b["w1"], b["w2"]
    s_serial = s["plan_cpu_s"] + s["finish_cpu_s"]
    s_replay = s["coordinator_cpu_s"] - s_serial
    replay2 = sum(w["cpu_s"] or 0 for w in w2["workers"]) - sum(
        w["startup_cpu_s"] for w in w2["workers"]
    )
    startup = max((w["startup_cpu_s"] for w in w2["workers"]), default=0.0)
    ideal = (
        w2["plan_cpu_s"]
        + w2["finish_cpu_s"]
        + startup
        + max(replay2 / 2, out["largest_mint"]["replay_alone_s"])
    )
    other = w2["coordinator_cpu_s"] - w2["plan_cpu_s"] - w2["finish_cpu_s"]
    return (f"  serial wall {s['wall_s']:.2f}s cpu {s['coordinator_cpu_s']:.2f}s (plan+finish cpu {s_serial:.2f}s) "
            f"| w1 wall {w1['wall_s']:.2f}s total cpu {w1['total_cpu_s']:.2f}s | w2 wall {w2['wall_s']:.2f}s "
            f"total cpu {w2['total_cpu_s']:.2f}s\n  serial/w2 {s['wall_s'] / w2['wall_s']:.2f}x  w1/w2 "
            f"{w1['wall_s'] / w2['wall_s']:.2f}x | f {100 * s_serial / s['coordinator_cpu_s']:.1f}% "
            f"({1e6 * s_serial / n:.0f} us cpu/fill) k2 {replay2 / max(1e-9, s_replay):.2f} | w2 coordinator cpu: "
            f"plan+finish {w2['plan_cpu_s'] + w2['finish_cpu_s']:.2f}s, other {other:.2f}s | startup {startup:.2f}s, "
            f"largest mint alone {out['largest_mint']['replay_alone_s']:.2f}s -> idealized T2 {ideal:.2f}s"
            f"\n  worker peak WS MB {[w['peak_ws_mb'] for w in w2['workers']]} | digest {out['digest']}")  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--traced", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    lines = ["SYNTHETIC bench (not market data) — wallets engine, CPU plan step 3 (1 vs 2 workers)",
             "ENV " + json.dumps({"python": sys.version.split()[0], "platform": sys.platform,
                                  "cpu_count": os.cpu_count(), "generator": gen.LABEL,
                                  "argv": " ".join(sys.argv[1:])})]  # fmt: skip
    print("\n".join(lines), flush=True)
    for spec in CONFIGS:
        if args.only and spec["name"] not in args.only.split(","):
            continue
        cfg = replace(gen.Config(), **spec)
        print(f"=== {cfg.name} ===", flush=True)
        out = run(cfg, args.rounds, args.traced)
        block = [f"\n=== {cfg.name} ===", "ROW " + json.dumps(out, default=str), summary(out)]
        print("\n".join(block[2:]), flush=True)
        lines += block
    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
