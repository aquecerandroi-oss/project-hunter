"""Does pump.fun's own realtime feed deliver information EARLIER than what we use today? (2026-10-06)

Opens, anonymously and read-only, the feeds an anonymous visitor of pump.fun has (NATS ``unified`` and
``core`` with the static ``subscriber`` credential the home page itself ships, the ``/ws/trenches`` boards),
plus the references we already use (PumpPortal free WS, Solana public RPC ``logsSubscribe`` on the pump
program), and stamps every frame with the local clock the instant it arrives. One connection per source, a
bounded set of per-coin and per-wallet NATS subjects (never a wildcard), a refusal (403/418/429/auth) stops
that source. Never signs or sends anything, never reads ``.env``, no login, no cookie, no header spoofing.

Raw output in ``--out`` (default ``.claude/state/pumpfun-rt-latency/run1``): ``events.jsonl`` (every frame),
``samples.json`` (a few raw frames per source: the field inventory), ``meta.json``, ``blocktime.json``.
Analysis: ``2026-10-06-pumpfun-realtime-latency-read.py --run <dir>``.

    uv run --no-sync python infra/scripts/research/2026-10-06-pumpfun-realtime-latency.py --seconds 2700 \\
        --keep-awake --out .claude/state/pumpfun-rt-latency/run1 > .claude/state/pumpfun-rt-latency/run1.log 2>&1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import threading
import time
from collections.abc import Coroutine
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from pumpfun_rt_probe_conv import parse_block_time
from pumpfun_rt_probe_feeds import (
    fetch_nats_configs,
    run_nats,
    run_pumpportal,
    run_rpc_logs,
    run_trenches,
)
from pumpfun_rt_probe_io import Ctx, Recorder, Refused, clock_sampler, guarded, watchdog
from pumpfun_rt_probe_sel import MintPlan, WalletPlan

RPC_HTTP = "https://api.mainnet-beta.solana.com"


async def block_times(slots: list[int], out: Path) -> dict[str, Any]:
    """After the capture: ``getBlockTime`` of a sample of the slots the feeds named (public RPC, 2 req/s,
    stop on the first refusal). Tells how the NATS ``timestamp`` second relates to the chain's block time."""
    got: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=15.0) as client:
        for slot in slots:
            body = {"jsonrpc": "2.0", "id": 1, "method": "getBlockTime", "params": [slot]}
            try:
                r = await client.post(RPC_HTTP, json=body)
            except httpx.HTTPError as exc:
                got["_error"] = None
                print(f"blocktime: {exc}", flush=True)
                break
            if r.status_code in (403, 418, 429):
                print(f"blocktime: refused HTTP {r.status_code}, stopped", flush=True)
                got["_refused"] = r.status_code
                break
            value, why = parse_block_time(r.json())
            if why is not None and why[:3] in ("413", "429", "403"):
                print(
                    f"blocktime: refused ({why}), stopped; no more calls to this endpoint",
                    flush=True,
                )
                got["_refused"] = why
                break
            got[str(slot)] = value
            await asyncio.sleep(0.5)
    (out / "blocktime.json").write_text(json.dumps(got), encoding="utf-8")
    answered = sum(1 for k, v in got.items() if v and not k.startswith("_"))
    return {"requested": len(slots), "answered": answered, "refused": got.get("_refused")}


def slots_to_sample(events_path: Path, n: int) -> list[int]:
    seen: dict[int, None] = {}
    for line in events_path.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        if e["s"] == "nats_u" and e["k"] == "trade" and isinstance(e.get("slot"), int):
            seen.setdefault(e["slot"], None)
    slots = list(seen)
    step = max(1, len(slots) // n)
    return slots[::step][:n]


def others(ctx: Ctx) -> dict[str, Coroutine[Any, Any, None]]:
    """The feeds that do not need the NATS credential."""
    return {
        "pp": run_pumpportal(ctx),
        "rpc": run_rpc_logs(ctx),
        "tr_new": run_trenches(ctx, "new", "tr_new"),
        "tr_grad": run_trenches(ctx, "graduated", "tr_grad"),
    }


async def main_async(args: argparse.Namespace) -> None:
    out = Path(args.out)
    rec = Recorder(out)
    ctx = Ctx(rec=rec, stop=asyncio.Event())
    mints = MintPlan(max_mints=args.max_mints, hold_s=args.hold, lite_max=args.lite_max)
    wallets = WalletPlan(max_wallets=args.max_wallets, min_trades=2)
    started = time.time()
    tasks = [asyncio.create_task(c) for c in (rec.flusher(), watchdog(ctx), clock_sampler(ctx))]
    try:
        cfgs = await fetch_nats_configs(ctx)
        print(f"nats instances in the page: {sorted(cfgs)}", flush=True)
        feeds = {"nats": run_nats(ctx, cfgs, mints, wallets), **others(ctx)}
    except (Refused, ValueError) as exc:
        rec.refused["nats"] = f"requires auth / not available: {exc}"
        print(f"NATS: {rec.refused['nats']}", flush=True)
        feeds = others(ctx)
    tasks += [asyncio.create_task(guarded(ctx, name, f)) for name, f in feeds.items()]
    try:
        await asyncio.wait_for(ctx.stop.wait(), args.seconds)
    except TimeoutError:
        pass
    ctx.stop.set()
    await asyncio.sleep(1.0)
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    ended = time.time()
    rec.close()
    lags = sorted(ctx.lags)
    meta = {
        "started": started, "ended": ended, "args": vars(args), "counts": dict(rec.counts),
        "refused": rec.refused, "stalls": ctx.stalls, "mints_opened": dict(mints.opened),
        "mints_skipped_cap": mints.skipped, "wallets_followed": len(wallets.followed),
        "loop_lag_s": {"n": len(lags), "p50": statistics.median(lags) if lags else None,
                       "p99": lags[int(len(lags) * 0.99)] if lags else None,
                       "max": lags[-1] if lags else None},
    }  # fmt: skip
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    meta["blocktime"] = await block_times(
        slots_to_sample(out / "events.jsonl", args.blocktime_slots), out
    )
    (out / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(
        json.dumps(
            {k: meta[k] for k in ("counts", "refused", "stalls", "loop_lag_s", "blocktime")},
            indent=1,
        )
    )


def hold_awake() -> threading.Event:
    """Windows: a thread that holds ``ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED`` until the
    returned event is set (the state belongs to the thread and dies with it). The first run (06/10) slept for
    7.8 h under ``ES_SYSTEM_REQUIRED`` alone, so the display flag is added; a closed lid still wins, which is
    why the analysis splits the capture at any long stall instead of trusting this guard."""
    release = threading.Event()
    if sys.platform == "win32":
        import ctypes

        def hold() -> None:
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
            release.wait()
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

        threading.Thread(target=hold, name="keep-awake", daemon=True).start()
    return release


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--seconds", type=float, default=2700)
    p.add_argument("--max-mints", type=int, default=30)
    p.add_argument(
        "--hold", type=float, default=360.0, help="seconds a new coin's subjects stay open"
    )
    p.add_argument("--lite-max", type=int, default=10)
    p.add_argument("--max-wallets", type=int, default=20)
    p.add_argument("--blocktime-slots", type=int, default=60)
    p.add_argument(
        "--keep-awake", action="store_true", help="Windows: no sleep while this process runs"
    )
    p.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[3] / ".claude/state/pumpfun-rt-latency/run1"),
    )
    args = p.parse_args()
    release = hold_awake() if args.keep_awake else None
    try:
        asyncio.run(main_async(args))
    finally:
        if release is not None:
            release.set()


if __name__ == "__main__":
    main()
