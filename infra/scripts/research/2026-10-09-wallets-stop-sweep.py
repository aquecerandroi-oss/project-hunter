"""One hot key's replay vs its events per hour, curve or pool (CPU plan step 4, 09/10/2026).

SYNTHETIC — NOT MARKET DATA (generator ``kb0183-shape-v2`` for the background and the hot key's
wallets, sides and sizes). The step-3 sweep (``2026-10-06-wallets-hot-mint-sweep.py``) could not
pack more than ≈ 18 000 events in an hour (slot steps ≥ 1 per event) and let the generator draw
the hot mint's venue, with a random pool state per event. KB-0187 measured the real hot keys as
POOLS with up to 124 069 events in one hour (≈ 14 per slot). So this sweep REBUILDS the hot key
after generation, keeping the generator's wallets, sides, sizes and arrival delays in its order:

- slots: event ``i`` of ``n`` lands at ``start + i * span // n`` (``span`` = the hour in slots);
- states: one coherent walk (45 SOL; a buy +0.5 SOL, a sale −1 SOL, kept in [31, 84] SOL, the
  generator's own walk; ``--walk time`` scales both steps by 1 000 / events per hour, so the price
  path in TIME is the same at any density and a copy scans more events where there are more —
  the case the step-3 cost curve assumed), quoted as a curve (``Reserves("curve", sol, K // sol, sol − 30 SOL)``)
  or as a pool on the same numbers (``Reserves("pool", sol, K // sol, None, virtual)``), so the
  two venues differ only in the quote arithmetic.

Measured per point, on the engine importable at run time:

- CPU of ``stream.replay_window`` of the hot key alone (``process_time``, min of ``--repeat``,
  the pricing memo and the tape's caches fresh each time: a new window → a new ``MintTape``);
- deterministic work: copies (bets), ``sell_lamports`` calls from the stop path (``policy`` and,
  when present, ``stops``), and a digest of the replay's result (must be equal before/after).

Run: ``uv run python infra/scripts/research/2026-10-09-wallets-stop-sweep.py --venue pool
--hot 16000,32000 --out <file>``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import sys
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

from hunter_indicators.meme.wallets import policy, pricing, stream
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.tape import Fill, Reserves

_spec = importlib.util.spec_from_file_location(
    "wbench", Path(__file__).with_name("2026-10-06-wallets-engine-workers.py")
)
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
sys.modules["wbench"] = bench
_spec.loader.exec_module(bench)
gen = bench.gen
SOL, K = gen.SOL, gen.K


def _rebuilt(
    fills: list[Fill], venue: str, virtual: int, minutes: int, walk: str = "event"
) -> list[Fill]:
    hot = sorted((f for f in fills if f.mint == "HOT"), key=lambda f: int(f.signature[3:]))
    if not hot:
        return fills
    span, start, n = minutes * 150, hot[0].slot, len(hot)
    sol, out = 45 * SOL, list[Fill]()
    scale = (1, 1) if walk == "event" else (1_000, n * 60 // minutes)  # see --walk
    up, down = SOL // 2 * scale[0] // scale[1], SOL * scale[0] // scale[1]
    for i, f in enumerate(hot):
        if venue == "curve":
            state = Reserves("curve", sol, K // sol, sol - 30 * SOL)
        else:
            state = Reserves("pool", sol, K // sol, None, virtual_quote_lamports=virtual)
        slot = start + i * span // n
        block = gen.T0 + timedelta(seconds=slot * 2 // 5)
        out.append(replace(f, program=gen.AMM if venue == "pool" else gen.PUMP, slot=slot,
                           block_time=block, received_at=block + (f.received_at - f.block_time),
                           venue=venue, reserves=state,
                           lp_fee_lamports=f.sol_lamports // 400 if venue == "pool" else 0))  # fmt: skip
        sol = max(31 * SOL, sol - down) if f.side == "sell" else min(84 * SOL, sol + up)
    return [f for f in fills if f.mint != "HOT"] + out


def _stop_modules() -> list[Any]:
    mods: list[Any] = [policy]
    try:
        mods.append(importlib.import_module("hunter_indicators.meme.wallets.stops"))
    except ImportError:
        pass
    return [m for m in mods if hasattr(m, "sell_lamports")]


def point(
    hot: int, minutes: int, venue: str, virtual: int, repeat: int, walk: str = "event"
) -> dict[str, Any]:
    cfg = replace(gen.Config(), name=f"hot_{hot}", hot_fills=hot, hot_minutes=minutes)
    original = gen.generate

    def patched(c: Any) -> Any:
        fills, creates = original(c)
        return _rebuilt(fills, venue, virtual, minutes, walk), creates

    gen.generate = patched
    try:
        inputs, ws, day, _ = bench.nights(cfg)
    finally:
        gen.generate = original
    plan = stream.plan_night(inputs, day, params=RankingParams(window_days=cfg.window))
    window = next(w for w in ws if w.carry.mint == "HOT")
    calls, saved = [0], [(m, m.sell_lamports) for m in _stop_modules()]

    def wrap(fn: Any) -> Any:
        def counted(*a: Any, **k: Any) -> Any:
            calls[0] += 1
            return fn(*a, **k)

        return counted

    for m, fn in saved:
        m.sell_lamports = wrap(fn)
    try:
        pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
        part = stream.replay_window(plan, window)
    finally:
        for m, fn in saved:
            m.sell_lamports = fn
    cpus: list[float] = []
    for _ in range(repeat):
        pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
        c0 = time.process_time()
        stream.replay_window(plan, window)
        cpus.append(time.process_time() - c0)
    return {"venue": venue, "virtual": virtual, "walk": walk, "hot_fills": hot,
            "hot_minutes": minutes,
            "events": plan.events["HOT"], "copies": len(plan.bets.get("HOT", ())),
            "stop_path_quotes": calls[0], "cpu_s": min(cpus), "cpu_runs": cpus,
            "digest": hashlib.sha256(repr(part).encode()).hexdigest()[:16]}  # fmt: skip


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hot", default="1000,4000,16000")
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--venue", choices=("curve", "pool"), default="pool")
    ap.add_argument("--virtual", type=int, default=0, help="pool virtual quote, lamports")
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument(
        "--walk",
        choices=("event", "time"),
        default="event",
        help="event: the generator's step per event; time: the step scaled by "
        "1 000 / (events per hour), the same price path in time at any density",
    )
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    lines = ["SYNTHETIC sweep (not market data) — one hot key's replay vs its events per hour",
             f"python {sys.version.split()[0]} venue {args.venue} virtual {args.virtual} "
             f"walk {args.walk}"]  # fmt: skip
    for hot in (int(x) for x in args.hot.split(",")):
        row = point(hot, args.minutes, args.venue, args.virtual, args.repeat, args.walk)
        line = (f"{args.venue} hot {hot:>6} in {args.minutes} min: events {row['events']:>6} "
                f"copies {row['copies']:>5} stop-path quotes {row['stop_path_quotes']:>10,} "
                f"cpu {row['cpu_s']:.2f}s digest {row['digest']}")  # fmt: skip
        print(line, flush=True)
        lines += ["ROW " + json.dumps(row), line]
        if args.out:
            Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
