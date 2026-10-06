"""Frozen independent reference of the wallets engine (CPU plan step 2, 06/10/2026).

Why: the step-2 optimizations touch helpers the batch :func:`~hunter_indicators.meme.wallets.
ranking.build_snapshot` shares with the bounded engine (``policy.simulate_copy``, ``pricing``), so
a wrong change could move both sides of the differential tests together and still pass them. This
module recomputes, from fixed synthetic worlds (fixtures, not data), digests of:

- every night's snapshot of both engines (``leakage.fingerprint``) and the bounded engine's next
  carry (``carry_codec.carry_to_json``);
- ``simulate_copy`` on EVERY buy of a dense world as a trigger (default policy, the 13-slot stress
  delay, and the bounded engine's ``leader_prior``/``leader_since`` form);
- ``sell_lamports``/``buy_atoms`` on a seeded grid of curve/pool states (cap binding, complete
  curves, negative virtual quote).

``wallets_golden.json`` holds the digests produced by the code of commit ``84704fa1`` (before any
step-2 change). Regenerating it is NOT a way to make a test pass: a rule change is a new version.
Regenerate only with ``uv run python -m packages.indicators.tests.meme.wallets_golden --write``
on the untouched engine.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path

from hunter_indicators.meme.wallets.carry import canonical_order, initial_carry
from hunter_indicators.meme.wallets.carry_codec import carry_to_json
from hunter_indicators.meme.wallets.leakage import fingerprint
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.policy import simulate_copy
from hunter_indicators.meme.wallets.pricing import MintTape, buy_atoms, sell_lamports
from hunter_indicators.meme.wallets.ranking import cut_of
from hunter_indicators.meme.wallets.stream import StreamInputs, shared_signatures, stream_snapshot
from hunter_indicators.meme.wallets.tape import CreateEvent, Fill, Reserves, dedupe
from packages.indicators.tests.meme.stream_harness import World, mint_windows, reference_snapshot
from packages.indicators.tests.meme.stream_world import (
    DAY_SLOTS,
    _curve,  # pyright: ignore[reportPrivateUsage]
    _Gen,  # pyright: ignore[reportPrivateUsage]
    _pool,  # pyright: ignore[reportPrivateUsage]
    block_time_of,
    random_world,
)
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN

GOLDEN = Path(__file__).with_name("wallets_golden.json")
_SIZES = (SOL // 200, SOL // 20, SOL // 5, SOL, 12 * SOL)


def _digest(items: Iterable[object]) -> str:
    h = hashlib.sha256()
    for item in items:
        h.update(repr(item).encode())
        h.update(b"\n")
    return h.hexdigest()


def _dense_mint(g: _Gen, mint: str, start: int, n: int, wallets: list[str], pool: bool) -> None:
    """``n`` events: a dense run (many distinct buyers = triggers, sells, same-slot bursts), a
    migration two thirds in (then pool states, or ``pool=False``: only completed-curve states, so
    landings are censored) and a sparse tail of the last 40 events (the 1 h time cap lands)."""
    rng, held, sol, slot = g.rng, dict[str, int](), 40 * SOL, start
    done = _curve(85 * SOL, complete=True)
    for k in range(n):
        slot += rng.choice((0, 1, 1, 2, 3, 8)) if k < n - 40 else rng.randrange(300, 900)
        if k == 2 * n // 3:
            g.add(g.make(wallet=rng.choice(wallets), mint=mint, side="buy", slot=slot, sol=SOL,
                         atoms=10 * TOKEN, state=done))  # fmt: skip
            continue
        state = (_pool(rng) if pool else done) if k > 2 * n // 3 else _curve(sol)
        if k % 97 == 0:  # a burst: several distinct wallets buy in the same slot
            for w in rng.sample(wallets, 6):
                g.add(g.make(wallet=w, mint=mint, side="buy", slot=slot, sol=SOL // 5,
                             atoms=3_000_000 * TOKEN, state=state))  # fmt: skip
            continue
        wallet = rng.choice(wallets) if rng.random() < 0.85 else f"one{g.seq}"
        if held.get(wallet, 0) and rng.random() < 0.45:
            atoms = max(1, held[wallet] * rng.choice((1, 1, 2, 3)) // 3)
            held[wallet] = max(0, held[wallet] - atoms)
            sol = max(31 * SOL, sol - rng.randrange(0, 3) * SOL)
            g.add(g.make(wallet=wallet, mint=mint, side="sell", slot=slot,
                         sol=rng.randrange(1, 30) * SOL // 10, atoms=atoms, state=state))  # fmt: skip
        else:
            atoms = rng.randrange(1, 40) * 1_000_000 * TOKEN
            held[wallet] = held.get(wallet, 0) + atoms
            sol = min(84 * SOL, sol + rng.randrange(0, 2) * SOL)
            g.add(g.make(wallet=wallet, mint=mint, side="buy", slot=slot, sol=rng.choice(_SIZES),
                         atoms=atoms, state=state))  # fmt: skip


def dense_world(seed: int) -> World:
    """3 mints, 60 wallets, ~1 200 events over 4 days; late arrivals and duplicates come from
    ``stream_world._Gen`` (inside the contract)."""
    g = _Gen(random.Random(seed), window_days=2)
    wallets = [f"D{i:02d}" for i in range(60)]
    creates: list[CreateEvent] = []
    for i, (mint, start, n) in enumerate((("H", DAY_SLOTS + 900, 700), ("X", 2 * DAY_SLOTS + 50,
                                          300), ("Y", DAY_SLOTS // 2, 200))):  # fmt: skip
        at = T0 + block_time_of(start - 2)
        creates.append(CreateEvent(mint, "dev" if i else "D07", start - 2, at,
                                   at + timedelta(seconds=0.6)))  # fmt: skip
        _dense_mint(g, mint, start, n, wallets, pool=mint != "Y")
    return World(T0, tuple(g.fills), tuple(creates))


def _nights(world: World, days: list[date], params: RankingParams) -> list[str]:
    """Per night: the batch fingerprint, the bounded one, and the bounded next carry."""
    carry, first = initial_carry(world.origin, world.preserved, window_days=params.window_days)
    mints = {m.mint: m for m in first}
    shared = shared_signatures(world.fills)
    out: list[str] = []
    for day in days:
        start = cut_of(day) - timedelta(days=params.window_days)
        windows = mint_windows(world, mints, start)
        inputs = StreamInputs(carry=carry, mints=lambda w=windows: iter(w), links=world.links,
                              funders=world.funders, gaps=world.gaps, shared_signatures=shared)  # fmt: skip
        result = stream_snapshot(inputs, day, params=params)
        batch = reference_snapshot(world, day, params=params)
        out += [_digest(fingerprint(batch)), _digest(fingerprint(result.snapshot)),
                _digest([carry_to_json(result.carry, result.mint_carries)])]  # fmt: skip
        carry, mints = result.carry, {m.mint: m for m in result.mint_carries}
    return out


def _copies(world: World) -> dict[str, str]:
    tapes: dict[str, list[Fill]] = {}
    for f in dedupe(sorted(world.fills, key=canonical_order)):
        tapes.setdefault(f.mint, []).append(f)
    out: dict[str, str] = {}
    for name, policy in (("default", FollowPolicy()), ("delay13", FollowPolicy(delay_slots=13))):
        rows: list[object] = []
        for _mint, fills in sorted(tapes.items()):
            tape, horizon = MintTape(fills), max(f.slot for f in fills) - 400
            since = fills[len(fills) // 3].received_at
            for f in tape.fills:
                if f.side != "buy":
                    continue
                rows.append(simulate_copy(f, leader_wallets=frozenset({f.wallet}), tape=tape,
                                          policy=policy, horizon_slot=horizon))  # fmt: skip
                pair = frozenset({f.wallet, "D00"})
                before = [e for e in fills if e.wallet in pair and e.received_at < since]
                prior = (sum(e.token_atoms for e in before if e.side == "buy"),
                         sum(e.token_atoms for e in before if e.side == "sell"))  # fmt: skip
                rows.append(simulate_copy(f, leader_wallets=pair, tape=tape, policy=policy,
                                          horizon_slot=horizon, leader_prior=prior,
                                          leader_since=since))  # fmt: skip
        out[name] = _digest(rows)
        out[f"{name}_count"] = str(len(rows))
    return out


def _quotes(seed: int) -> str:
    rng, rows = random.Random(seed), list[object]()
    for _ in range(3_000):
        kind = rng.random()
        if kind < 0.5:
            sol = rng.randrange(30 * SOL + 1, 90 * SOL)
            real = rng.choice((sol - 30 * SOL, rng.randrange(0, 2 * SOL)))  # cap may bind
            state = Reserves("curve", sol, rng.randrange(200, 1_073) * 1_000_000 * TOKEN, real,
                             complete=rng.random() < 0.05)  # fmt: skip
        else:
            quote = rng.randrange(1, 300) * SOL
            state = Reserves("pool", quote, rng.randrange(1, 900) * 1_000_000 * TOKEN, None,
                             virtual_quote_lamports=rng.choice((0, 20 * SOL, -(quote // 3))))  # fmt: skip
        bps = rng.choice((0, 30, 95, 100, 125, 9_999))
        atoms = rng.choice((1, rng.randrange(1, 10**6), rng.randrange(1, 10**15), 10**17))
        rows.append((sell_lamports(state, atoms, fee_bps=bps),
                     buy_atoms(state, rng.choice((1, SOL // 20, 7 * SOL)), fee_bps=bps)))  # fmt: skip
    return _digest(rows)


def compute() -> dict[str, object]:
    small = RankingParams(window_days=2, min_episodes=2, min_mints=1, min_active_days=1,
                          min_e_pnl_lamports=0, min_positive_days=1, top_n=2)  # fmt: skip
    first = (T0 + timedelta(days=2)).date()
    days = [first + timedelta(days=k) for k in range(5)]
    out: dict[str, object] = {}
    for seed in range(4):
        world, _ = random_world(seed, window_days=2, days=6)
        out[f"random{seed}"] = _nights(world, days, small)
    dense = dense_world(7)
    out["dense_nights"] = _nights(dense, days[:3], small)
    out["dense_copies"] = _copies(dense)
    out["quotes"] = _quotes(11)
    return out


if __name__ == "__main__":
    data = compute()
    if "--write" in sys.argv:
        GOLDEN.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=1, sort_keys=True))
