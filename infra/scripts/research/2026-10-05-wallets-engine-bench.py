"""Benchmark of the H-030 wallets engine: batch ``build_snapshot`` vs bounded ``stream_snapshot``.

SYNTHETIC — NOT A MEASUREMENT OF THE MARKET. A seeded campaign in the shape measured on 05/10
(KB-0183 run 3: most wallets swap once, a few wallets make most of the events, ~29 % of swaps are
below 0.01 SOL, mints with a heavy-tailed number of events, 10 % migrating to a pool, a few
percent of events received late), scaled down by orders of magnitude. For each scale it runs the
nights of a sliding window from the origin with the bounded engine, then the batch engine on the
last day, checks both snapshots are EQUAL (a differential at scale), and reports:

- wall time per night (no tracing) and Python-heap peak per night (``tracemalloc``, separate run);
- the resident size of the window's ``Fill`` objects (what the batch must hold at once) against
  the largest single mint's (what the bounded engine holds at once);
- the carry: per-mint rows (lots, flows, frontier), weak-link pairs and JSON bytes.

The extrapolation at the end is LINEAR on the per-unit costs measured here, applied to the
volumes of the design (28.5–31 M swaps/day, KB-0183) and to SCENARIOS (not measures) of entities
and lots. Run: ``uv run python infra/scripts/research/2026-10-05-wallets-engine-bench.py``.
"""

from __future__ import annotations

import argparse
import random
import time
import tracemalloc
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from hunter_indicators.meme.wallets.carry import (
    MintCarry,
    canonical_order,
    initial_carry,
    sort_lots,
)
from hunter_indicators.meme.wallets.carry_codec import carry_to_json
from hunter_indicators.meme.wallets.lots import fifo
from hunter_indicators.meme.wallets.params import RankingParams
from hunter_indicators.meme.wallets.ranking import RankInputs, build_snapshot, cut_of
from hunter_indicators.meme.wallets.stream import (
    MintWindow,
    StreamInputs,
    StreamResult,
    shared_signatures,
    stream_snapshot,
)
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Reserves, dedupe

SOL = 1_000_000_000
TOKEN = 1_000_000
K = 30 * SOL * 1_073_000_000 * TOKEN
T0 = datetime(2026, 10, 6, tzinfo=UTC)
DAY_SLOTS = 216_000
PUMP, AMM = (
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
)


def _curve(sol: int) -> Reserves:
    return Reserves("curve", sol, K // sol, sol - 30 * SOL)


def _pool(rng: random.Random) -> Reserves:
    sol = rng.randrange(40, 200) * SOL
    return Reserves("pool", sol, rng.randrange(100, 900) * TOKEN * 1_000_000, None,
                    virtual_quote_lamports=rng.choice((0, 20 * SOL)))  # fmt: skip


def generate(per_day: int, days: int, seed: int) -> tuple[list[Fill], list[CreateEvent]]:
    """``per_day`` swaps a day over ``per_day // 60`` new mints a day (heavy-tailed sizes)."""
    rng = random.Random(seed)
    fills: list[Fill] = []
    creates: list[CreateEvent] = []
    active = [f"W{i}" for i in range(max(20, per_day // 200))]  # ~4 % of wallets, most events
    seq = 0
    for day in range(days):
        for m in range(max(1, per_day // 60)):
            mint = f"M{day}_{m}"
            size = min(int(rng.paretovariate(1.1) * 12), per_day // 4)
            slot = day * DAY_SLOTS + rng.randrange(10, DAY_SLOTS - 12_000)
            at = T0 + timedelta(seconds=(slot - 2) * 2 // 5)
            creates.append(
                CreateEvent(mint, f"dev{seq}", slot - 2, at, at + timedelta(seconds=0.6))
            )
            sol, held, pool = rng.randrange(31, 60) * SOL, dict[str, int](), rng.random() < 0.1
            for _ in range(size):
                seq += 1
                slot += rng.choice((0, 1, 1, 2, 5, 20, 120))
                wallet = rng.choice(active) if rng.random() < 0.46 else f"N{seq}"
                state = _pool(rng) if pool else _curve(sol)
                block = T0 + timedelta(seconds=slot * 2 // 5)
                late = rng.random() < 0.02
                received = block + timedelta(
                    seconds=rng.uniform(1, 7_200) if late else rng.uniform(0.3, 3.0)
                )
                if held.get(wallet) and rng.random() < 0.5:
                    side, atoms = "sell", held.pop(wallet)
                    sol = max(31 * SOL, sol - SOL)
                else:
                    side, atoms = "buy", rng.randrange(1, 40) * 1_000_000 * TOKEN
                    held[wallet] = held.get(wallet, 0) + atoms
                    sol = min(84 * SOL, sol + SOL // 2)
                lamports = rng.choice((SOL // 200, SOL // 20, SOL // 5, SOL, 12 * SOL))
                fills.append(Fill(f"sig{seq}", PUMP if not pool else AMM, 0, slot, block, received,
                                  wallet, mint, state.venue, side, lamports, atoms,
                                  lamports // 100, 100, state, lamports // 400 if pool else 0))  # fmt: skip
    return fills, creates


def _windows(by_mint: dict[str, list[Fill]], creates: dict[str, list[CreateEvent]],
             carries: dict[str, MintCarry], start: datetime) -> list[MintWindow]:  # fmt: skip
    names = sorted({*carries, *by_mint})
    return [
        MintWindow(carries.get(m, MintCarry(m)),
                   tuple(f for f in by_mint.get(m, ()) if f.received_at >= start),
                   tuple(c for c in creates.get(m, ()) if c.received_at >= start))
        for m in names
    ]  # fmt: skip


def _measure(fn: Callable[[], object], traced: bool) -> tuple[object, float, int]:
    if traced:
        tracemalloc.start()
        tracemalloc.reset_peak()
    t = time.perf_counter()
    out = fn()
    elapsed = time.perf_counter() - t
    peak = tracemalloc.get_traced_memory()[1] if traced else 0
    if traced:
        tracemalloc.stop()
    return out, elapsed, peak


def _fill_bytes(sample: list[Fill]) -> float:
    """Resident bytes per ``Fill`` (with its ``Reserves`` and strings), by tracing a rebuild."""
    tracemalloc.start()
    before = tracemalloc.get_traced_memory()[0]
    copies = [Fill(f.signature + "x", f.program, f.event_ordinal, f.slot, f.block_time,
                   f.received_at, f.wallet + "x", f.mint + "x", f.venue, f.side, f.sol_lamports,
                   f.token_atoms, f.fee_lamports, f.fee_bps,
                   Reserves(f.reserves.venue, f.reserves.sol_lamports, f.reserves.token_atoms,
                            f.reserves.real_sol_lamports), f.lp_fee_lamports)
              for f in sample]  # fmt: skip
    size = tracemalloc.get_traced_memory()[0] - before
    tracemalloc.stop()
    return size / max(1, len(copies))


def run(per_day: int, days: int, window: int, traced: bool) -> dict[str, float]:
    fills, creates = generate(per_day, days, seed=per_day)
    params = RankingParams(window_days=window)
    canon = sorted(fills, key=canonical_order)
    by_mint: dict[str, list[Fill]] = {}
    for f in canon:
        by_mint.setdefault(f.mint, []).append(f)
    c_by_mint: dict[str, list[CreateEvent]] = {}
    for c in creates:
        c_by_mint.setdefault(c.mint, []).append(c)
    shared = shared_signatures(fills)
    carry, first = initial_carry(T0, window_days=window)
    carries = {m.mint: m for m in first}
    nights: list[date] = [(T0 + timedelta(days=k)).date() for k in range(window, days)]
    times, peaks, result = list[float](), list[int](), None
    for day in nights:
        ws = _windows(by_mint, c_by_mint, carries, cut_of(day) - timedelta(days=window))
        inputs = StreamInputs(carry=carry, mints=lambda w=ws: iter(w), shared_signatures=shared)
        out, elapsed, peak = _measure(
            lambda i=inputs, d=day: stream_snapshot(i, d, params=params), traced
        )
        assert isinstance(out, StreamResult)
        result, carry = out, out.carry
        carries = {m.mint: m for m in out.mint_carries}
        times.append(elapsed)
        peaks.append(peak)
    assert result is not None
    last, cut = nights[-1], cut_of(nights[-1])
    start = cut - timedelta(days=window)
    mined = [f for f in dedupe(canon) if f.block_time < start and f.received_at < cut]
    opening = sort_lots(fifo(mined, owner_of=str).open_lots)
    batch_inputs = RankInputs(fills=tuple(canon), creates=tuple(creates), opening_lots=opening)
    snap, b_time, b_peak = _measure(
        lambda: build_snapshot(batch_inputs, last, params=params), traced
    )
    assert snap == result.snapshot, "bounded and batch snapshots differ"
    window_fills = [f for f in canon if start <= f.block_time < cut]
    per_mint = [sum(1 for f in by_mint[m] if f.received_at >= start) for m in by_mint]
    mints = result.mint_carries
    return {
        "fills_per_day": per_day, "window_fills": len(window_fills),
        "largest_mint_fills": max(per_mint), "entities": len(result.snapshot.rows),
        "stream_s": times[-1], "batch_s": b_time, "stream_peak_mb": peaks[-1] / 1e6,
        "batch_peak_mb": b_peak / 1e6, "fill_bytes": _fill_bytes(window_fills[:5_000]),
        "carry_mints": len(mints), "carry_lots": sum(len(m.lots) for m in mints),
        "carry_flows": sum(len(m.flows) for m in mints),
        "carry_frontier": sum(len(m.frontier) for m in mints),
        "carry_pending_pairs": len(carry.pending), "carry_weak_links": len(carry.weak_links),
        "carry_json_mb": len(carry_to_json(carry, mints)) / 1e6,
    }  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scales", default="4000,8000,16000")
    parser.add_argument("--days", type=int, default=4)
    parser.add_argument("--window", type=int, default=2)
    args = parser.parse_args()
    print("SYNTHETIC benchmark (not market data); window", args.window, "d; days", args.days)
    rows: list[dict[str, float]] = []
    for scale in (int(s) for s in args.scales.split(",")):
        timing = run(scale, args.days, args.window, traced=False)
        memory = run(scale, args.days, args.window, traced=True)
        row = {**memory, "stream_s": timing["stream_s"], "batch_s": timing["batch_s"]}
        rows.append(row)
        print({k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()})
    big = rows[-1]
    s_per_fill = big["stream_s"] / big["window_fills"]
    b_per_fill = big["batch_s"] / big["window_fills"]
    heap_per_fill = big["batch_peak_mb"] * 1e6 / big["window_fills"]
    print(
        "\nEXTRAPOLATION (linear on the largest scale; volumes from KB-0183; SCENARIOS, not measures)"
    )
    for per_day in (28_500_000, 31_000_000):
        w = 7 * per_day
        fills_gb = w * (big["fill_bytes"] + heap_per_fill) / 1e9
        print(f"  {per_day / 1e6:.1f} M/day x 7 d = {w / 1e6:.0f} M window fills:"
              f" batch heap ~ {fills_gb:.0f} GB (Fill objects + engine);"
              f" CPU one core: batch ~ {w * b_per_fill / 3600:.1f} h, bounded ~ {w * s_per_fill / 3600:.1f} h/night")  # fmt: skip
    per_entity = (big["stream_peak_mb"] * 1e6) / max(1, big["entities"])
    for entities in (1_000_000, 5_000_000, 20_000_000):
        print(f"  bounded heap with {entities / 1e6:.0f} M entities in the window ~"
              f" {entities * per_entity / 1e9:.1f} GB (tallies; ~ {per_entity:.0f} B/entity measured)")  # fmt: skip


if __name__ == "__main__":
    main()
