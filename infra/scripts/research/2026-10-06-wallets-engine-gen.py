"""Synthetic campaign generator for the H-030 wallets-engine profile (CPU plan step 1, 06/10/2026).

SYNTHETIC — NOT MARKET DATA. Generator label ``kb0183-shape-v2``. Change against the 05/10 bench
generator (``2026-10-05-wallets-engine-bench.py``), which drew a NEW wallet for 54 % of events:

- **who trades** follows KB-0183 run 3 (15 min, 73 235 wallets, design §8.2): 13 % of events by
  wallets that swap once (a fresh wallet per event), 41 % by a per-day "mid" pool (avg ≈ 4.8
  swaps), 41 % by a persistent "heavy" pool (≈ 4 % of wallets) and 5 % by a tiny "super" pool
  (8 per 317 700 events). The realized census is measured and printed, not assumed; how the 15-min
  shape stretches to a day/window is UNKNOWN (no multi-day measure);
- **swap sizes** follow the KB-0183 erratum sample (≈ 40 % < 0.01 SOL, ≈ 0.4 % ≥ 10 SOL);
  ``trigger_share`` = share of buys ≥ 0.1 SOL (the trigger floor) — a knob, default 0.35;
- **knobs** varied one at a time by the profile: ``wallet_scale`` (distinct wallets at fixed
  fills), ``hot_fills``/``hot_minutes`` (one hot mint inside the measured window), ``bursts`` ×
  ``burst_size`` (same-slot buyer bursts), ``days`` (history = carried lots/flows) and ``quiet``
  (the measured window is empty: only the carry is replayed).

Mint sizes, venues (10 % pool), slot steps and arrival delays are the 05/10 bench's.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Reserves

SOL = 1_000_000_000
TOKEN = 1_000_000
K = 30 * SOL * 1_073_000_000 * TOKEN
T0 = datetime(2026, 10, 6, tzinfo=UTC)
DAY_SLOTS = 216_000
PUMP, AMM = (
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
)
LABEL = "kb0183-shape-v2"


@dataclass(frozen=True, slots=True)
class Config:
    name: str = "base"
    per_day: int = 8_000
    days: int = 4
    window: int = 2
    seed: int = 1
    trigger_share: float = 0.35
    wallet_scale: float = 1.0
    hot_fills: int = 0
    hot_minutes: int = 60
    bursts: int = 0
    burst_size: int = 0
    quiet: bool = False


def _curve(sol: int) -> Reserves:
    return Reserves("curve", sol, K // sol, sol - 30 * SOL)


def _pool(rng: random.Random) -> Reserves:
    sol = rng.randrange(40, 200) * SOL
    return Reserves("pool", sol, rng.randrange(100, 900) * TOKEN * 1_000_000, None,
                    virtual_quote_lamports=rng.choice((0, 20 * SOL)))  # fmt: skip


class _Gen:
    def __init__(self, cfg: Config) -> None:
        self.cfg, self.rng = cfg, random.Random(cfg.seed)
        self.fills: list[Fill] = []
        self.creates: list[CreateEvent] = []
        self.seq = 0
        scale = cfg.per_day * cfg.wallet_scale
        self.mid_n = max(1, round(0.0851 * scale))
        self.heavy_n = max(1, round(0.00897 * scale))
        self.super_n = max(1, round(scale * 8 / 317_700))

    def wallet(self, day: int) -> str:
        u = self.rng.random()
        if u < 0.13:
            return f"N{self.seq}"
        if u < 0.54:
            return f"m{day}_{self.rng.randrange(self.mid_n)}"
        if u < 0.95:
            return f"h{self.rng.randrange(self.heavy_n)}"
        return f"s{self.rng.randrange(self.super_n)}"

    def lamports(self) -> int:
        rng = self.rng
        if rng.random() < self.cfg.trigger_share:
            u = rng.random()
            return SOL // 5 if u < 0.57 else SOL if u < 0.989 else 12 * SOL
        return SOL // 200 if rng.random() < 0.62 else SOL // 20

    def create(self, mint: str, slot: int) -> None:
        at = T0 + timedelta(seconds=(slot - 2) * 2 // 5)
        self.creates.append(CreateEvent(mint, f"dev{self.seq}", slot - 2, at,
                                        at + timedelta(seconds=0.6)))  # fmt: skip

    def add(
        self, mint: str, slot: int, wallet: str, side: str, atoms: int, state: Reserves
    ) -> None:
        self.seq += 1
        block = T0 + timedelta(seconds=slot * 2 // 5)
        late = self.rng.random() < 0.02
        received = block + timedelta(
            seconds=self.rng.uniform(1, 7_200) if late else self.rng.uniform(0.3, 3.0)
        )
        lamports, pool = self.lamports(), state.venue == "pool"
        self.fills.append(Fill(f"sig{self.seq}", AMM if pool else PUMP, 0, slot, block, received,
                               wallet, mint, state.venue, side, lamports, atoms,  # type: ignore[arg-type]
                               lamports // 100, 100, state, lamports // 400 if pool else 0))  # fmt: skip

    def mint(self, mint: str, day: int, slot: int, size: int, steps: tuple[int, ...]) -> None:
        rng = self.rng
        self.create(mint, slot)
        sol, held, pool = rng.randrange(31, 60) * SOL, dict[str, int](), rng.random() < 0.1
        for _ in range(size):
            slot += rng.choice(steps)
            wallet = self.wallet(day)
            state = _pool(rng) if pool else _curve(sol)
            if held.get(wallet) and rng.random() < 0.5:
                side, atoms = "sell", held.pop(wallet)
                sol = max(31 * SOL, sol - SOL)
            else:
                side, atoms = "buy", rng.randrange(1, 40) * 1_000_000 * TOKEN
                held[wallet] = held.get(wallet, 0) + atoms
                sol = min(84 * SOL, sol + SOL // 2)
            self.add(mint, slot, wallet, side, atoms, state)

    def burst(self, mint: str, day: int, slot: int) -> None:
        """``burst_size`` distinct wallets buy the mint in one slot, then a quiet tail."""
        self.create(mint, slot)
        state = _curve(45 * SOL)
        buyers = {self.wallet(day) for _ in range(self.cfg.burst_size * 3)}
        for wallet in sorted(buyers)[: self.cfg.burst_size]:
            self.add(mint, slot, wallet, "buy", 3_000_000 * TOKEN, state)
        self.mint(mint, day, slot + 1, 20, (1, 2, 5, 20))


def generate(cfg: Config) -> tuple[list[Fill], list[CreateEvent]]:
    g, rng = _Gen(cfg), random.Random(cfg.seed + 1)
    quiet_from = cfg.days - 1 - cfg.window  # first day of the measured night's window
    for day in range(cfg.days):
        if cfg.quiet and day >= quiet_from:
            continue
        for m in range(max(1, cfg.per_day // 60)):
            size = min(int(g.rng.paretovariate(1.1) * 12), cfg.per_day // 4)
            slot = day * DAY_SLOTS + g.rng.randrange(10, DAY_SLOTS - 12_000)
            g.mint(f"M{day}_{m}", day, slot, size, (0, 1, 1, 2, 5, 20, 120))
    hot_day = cfg.days - 2  # inside the measured window, before its cut
    if cfg.hot_fills:
        span = cfg.hot_minutes * 150  # slots at 0.4 s
        step = max(1, 2 * span // cfg.hot_fills)
        g.mint("HOT", hot_day, hot_day * DAY_SLOTS + 30_000, cfg.hot_fills, tuple(range(step + 1)))
    for b in range(cfg.bursts):
        slot = hot_day * DAY_SLOTS + rng.randrange(1_000, DAY_SLOTS - 40_000)
        g.burst(f"B{b}", hot_day, slot)
    return g.fills, g.creates


def census(fills: list[Fill]) -> dict[str, float]:
    """The realized concentration (compare with KB-0183 run 3: 58 % / 13 % / 4 % → 46 %)."""
    per: dict[str, int] = {}
    for f in fills:
        per[f.wallet] = per.get(f.wallet, 0) + 1
    n, e = len(per), len(fills)
    one = [w for w, c in per.items() if c == 1]
    heavy = sum(c for c in per.values() if c >= 20)
    big_buys = [f for f in fills if f.side == "buy"]
    return {
        "wallets": n, "one_swap_wallets_pct": 100 * len(one) / max(1, n),
        "one_swap_events_pct": 100 * len(one) / max(1, e),
        "ge20_wallets_pct": 100 * sum(1 for c in per.values() if c >= 20) / max(1, n),
        "ge20_events_pct": 100 * heavy / max(1, e),
        "lt_0_01_sol_pct": 100 * sum(1 for f in fills if f.sol_lamports < SOL // 100) / max(1, e),
        "trigger_size_buys_pct": 100 * sum(1 for f in big_buys if f.sol_lamports >= SOL // 10)
        / max(1, len(big_buys)),
    }  # fmt: skip
