"""Random synthetic campaigns for the wave-1c-bis differential tests (fixtures, not data).

A seeded world of a few wallets and mints over several days, inside the contract of
:mod:`hunter_indicators.meme.wallets.carry` (one ``block_time`` per slot, ``received ≥ mined``,
every event received before its block day + the window, each identity delivered once across
nights), and deliberately full of what breaks a naive incremental engine: late arrivals across
midnight, duplicates within a night, twins merged by links known mid-campaign, weak links from
same-slot buys, transactions touching two mints, migrations (curve complete → pool), pools with a
signed virtual quote, gaps, preserved lots of unknown cost, creates by members and by funders.
Every number is invented; :class:`Census` counts what a world contains so a test can prove the
generator still exercises each path.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from datetime import timedelta

from hunter_indicators.meme.wallets.entities import Link
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Gap, Reserves
from packages.indicators.tests.meme.stream_harness import World
from packages.indicators.tests.meme.test_wallets_builders import AMM, PUMP, SOL, T0, TOKEN

DAY_SLOTS = 216_000  # 0.4 s per slot: block_time = T0 + floor(slot × 0.4 s)
K = 30 * SOL * 1_073_000_000 * TOKEN  # constant product of the launch curve
WALLETS = ("A", "B", "C", "D", "E", "F", "G", "H")


def block_time_of(slot: int) -> timedelta:
    return timedelta(seconds=slot * 2 // 5)


@dataclass(slots=True)
class Census:
    late_across_midnight: int = 0
    duplicates: int = 0
    shared_txs: int = 0
    migrated_mints: int = 0
    pool_fills: int = 0
    links_mid_campaign: int = 0
    weak_slot_buys: int = 0


@dataclass(slots=True)
class _Gen:
    rng: random.Random
    window_days: int
    fills: list[Fill] = field(default_factory=list[Fill])
    census: Census = field(default_factory=Census)
    seq: int = 0

    def delay(self, slot: int) -> float:
        """Seconds from mining to reception; late ones stay inside P1 (< block day + window)."""
        u = self.rng.random()
        if u < 0.80:
            return self.rng.uniform(0.2, 3.0)
        if u < 0.95:
            return self.rng.uniform(3.0, 900.0)
        day_end = (slot // DAY_SLOTS + 1) * DAY_SLOTS
        room = (block_time_of(day_end) - block_time_of(slot)).total_seconds()
        return self.rng.uniform(1.0, room + (self.window_days - 1) * 86_400 - 60.0)

    def add(self, f: Fill) -> Fill:
        if f.received_at.date() != f.block_time.date():
            self.census.late_across_midnight += 1
        self.fills.append(f)
        if self.rng.random() < 0.03:  # a duplicate delivery within the same UTC day
            later = f.received_at + timedelta(seconds=self.rng.uniform(0.0, 5.0))
            if later.date() == f.received_at.date():
                self.fills.append(replace(f, received_at=later))
                self.census.duplicates += 1
        return f

    def make(self, *, wallet: str, mint: str, side: str, slot: int, sol: int, atoms: int,
             state: Reserves, signature: str | None = None, ordinal: int = 0,
             delay: float | None = None) -> Fill:  # fmt: skip
        self.seq += 1
        block_time = T0 + block_time_of(slot)
        bps = self.rng.choice((0, 95, 125, 30))
        fee = sol * bps // 10_000
        lp = fee // 4 if state.venue == "pool" else 0
        wait = self.delay(slot) if delay is None else delay
        return Fill(signature or f"s{self.seq}", PUMP if state.venue == "curve" else AMM, ordinal,
                    slot, block_time, block_time + timedelta(seconds=wait), wallet, mint,
                    state.venue, "buy" if side == "buy" else "sell", sol, atoms, fee, bps, state,
                    lp)  # fmt: skip


def _curve(sol: int, complete: bool = False) -> Reserves:
    return Reserves("curve", sol, K // sol, sol - 30 * SOL, complete=complete)


def _pool(rng: random.Random) -> Reserves:
    sol = rng.randrange(40, 200) * SOL
    virtual = rng.choice((0, 20 * SOL, -(sol // 3)))
    return Reserves("pool", sol, rng.randrange(100, 900) * 1_000_000 * TOKEN, None,
                    virtual_quote_lamports=virtual)  # fmt: skip


def _mint_tape(g: _Gen, mint: str, start_slot: int, end_slot: int, migrate: bool) -> None:
    rng = g.rng
    sol = rng.randrange(31, 60) * SOL
    held: dict[str, int] = {}
    slot = start_slot
    migrated = False
    while slot < end_slot:
        burst_end = min(end_slot, slot + rng.randrange(2_000, 12_000))
        while slot < burst_end:
            slot += rng.choice((1, 1, 2, 5, 30, 200, 900))
            wallet = rng.choice(WALLETS)
            if migrate and not migrated and rng.random() < 0.04:
                migrated = True
                g.census.migrated_mints += 1
                g.add(g.make(wallet=wallet, mint=mint, side="buy", slot=slot, sol=SOL,
                             atoms=10 * TOKEN, state=_curve(85 * SOL, complete=True)))  # fmt: skip
                continue
            state = _pool(rng) if migrated else _curve(sol)
            g.census.pool_fills += migrated
            if held.get(wallet, 0) and rng.random() < 0.45:
                atoms = min(held[wallet], max(1, held[wallet] * rng.choice((1, 1, 2, 3)) // 3))
                atoms += rng.choice((0, 0, 0, TOKEN))  # sometimes beyond the inventory
                held[wallet] = max(0, held[wallet] - atoms)
                sol = max(31 * SOL, sol - rng.randrange(0, 4) * SOL)
                g.add(g.make(wallet=wallet, mint=mint, side="sell", slot=slot,
                             sol=rng.randrange(1, 30) * SOL // 10, atoms=atoms, state=state))  # fmt: skip
            else:
                atoms = rng.randrange(1, 40) * 1_000_000 * TOKEN
                held[wallet] = held.get(wallet, 0) + atoms
                sol = min(84 * SOL, sol + rng.randrange(0, 3) * SOL)
                g.add(g.make(wallet=wallet, mint=mint, side="buy", slot=slot,
                             sol=rng.choice((SOL // 20, SOL // 5, SOL, 2 * SOL)), atoms=atoms,
                             state=state))  # fmt: skip
        slot += rng.randrange(20_000, 120_000)


def _twins_same_slot(g: _Gen, mints: list[str], days: int) -> None:
    """A and B buy the same mint in the same slot in three mints: a weak link mid-campaign."""
    for i, mint in enumerate(mints[:3]):
        slot = (1 + i * (days - 1) // 3) * DAY_SLOTS // 2 + 7_000 + i
        for w in ("A", "B"):
            g.add(g.make(wallet=w, mint=mint, side="buy", slot=slot, sol=SOL // 5,
                         atoms=5_000_000 * TOKEN, state=_curve(45 * SOL)))  # fmt: skip
            g.census.weak_slot_buys += 1


def _shared_txs(g: _Gen, mints: list[str], days: int) -> None:
    for i in range(3):
        slot = g.rng.randrange(DAY_SLOTS // 4, days * DAY_SLOTS - DAY_SLOTS // 4)
        wallet, sig = g.rng.choice(WALLETS), f"multi{i}"
        a, b = g.rng.sample(mints, 2)
        delay = g.delay(slot)
        for ordinal, (mint, side) in enumerate(((a, "sell"), (b, "buy"), (a, "buy"))):
            g.add(g.make(wallet=wallet, mint=mint, side=side, slot=slot, sol=SOL // 2,
                         atoms=2_000_000 * TOKEN, state=_curve(50 * SOL), signature=sig,
                         ordinal=g.rng.choice((ordinal, 2 - ordinal)) if ordinal < 2 else 2,
                         delay=delay))  # fmt: skip
        g.census.shared_txs += 1


def random_world(seed: int, *, window_days: int, days: int) -> tuple[World, Census]:
    rng = random.Random(seed)
    g = _Gen(rng, window_days)
    mints = [f"M{i}" for i in range(rng.randrange(4, 7))]
    creates: list[CreateEvent] = []
    for i, mint in enumerate(mints):
        first = rng.randrange(10, days * DAY_SLOTS // 2)
        creator = rng.choice(("dev", "dev", "C", "FUND"))
        at = T0 + block_time_of(first - 2)
        creates.append(CreateEvent(mint, creator, first - 2, at, at + timedelta(seconds=0.6)))
        if i == 0:  # a later-received copy with another creator never wins
            creates.append(CreateEvent(mint, "A", first - 2, at, at + timedelta(seconds=9)))
        _mint_tape(g, mint, first, days * DAY_SLOTS - 50, migrate=i % 3 == 2)
    _twins_same_slot(g, mints, days)
    _shared_txs(g, mints, days)
    known = T0 + timedelta(days=rng.uniform(0.5, days - 1.0))
    links = (Link("C", "D", "strong", known, "F1"), Link("E", "F", "strong", T0, "F2"))
    g.census.links_mid_campaign += 1
    preserved = (
        Lot("G", mints[0], 7_000_000 * TOKEN, None, -5_000, T0 - timedelta(hours=3)),
        Lot("H", mints[1], 3_000_000 * TOKEN, SOL // 3, -4_000, T0 - timedelta(hours=2)),
    )
    funders = {"C": ("FUND", T0 + timedelta(days=rng.uniform(0.0, days)))}
    gaps = (Gap(DAY_SLOTS + 500, DAY_SLOTS + 900), Gap(3 * DAY_SLOTS // 2, 3 * DAY_SLOTS // 2 + 50))
    world = World(T0, tuple(g.fills), tuple(creates), links, funders, preserved, gaps)
    return world, g.census
