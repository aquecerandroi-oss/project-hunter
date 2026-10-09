"""CPU plan step 4 (09/10/2026), part 2: the stop scan by threshold decides exactly like the quote.

``policy._find_exit`` now asks a per-tape stop index (``stops.StopIndex``) for the first event
that stops a copy, instead of quoting the copy's sale in Decimal at every event of its exit
window. These tests compare it with a frozen copy of the loop it replaced (the per-(copy, event)
quote of ``policy.py`` before step 4) on random tapes that mix curves, pools with a negative /
zero / positive virtual quote, completed curves, states outside the monotone region (the Decimal
fallback) and a refusing state (``ValueError`` must still propagate), with two policies (two
floors) sharing one tape. The global guard stays ``test_wallets_golden``. Synthetic (not data).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext

import pytest

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme.wallets import policy as policy_mod
from hunter_indicators.meme.wallets import stops
from hunter_indicators.meme.wallets.clock import NominalClock
from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.policy import _find_exit  # pyright: ignore[reportPrivateUsage]
from hunter_indicators.meme.wallets.pricing import MintTape, buy_atoms, sell_lamports
from hunter_indicators.meme.wallets.tape import Fill, Reserves
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, curve, fill, pool

pytestmark = pytest.mark.unit

_K = 30 * SOL * 1_073_000_000 * TOKEN
POLICIES = (FollowPolicy(), FollowPolicy(stop_fraction=Decimal("0.8"), budget_lamports=SOL // 7))


@dataclass(frozen=True, slots=True)
class _Frozen:
    reason: str
    fire_slot: int
    landing_slot: int


def _frozen_find_exit(
    trigger: Fill, tape: MintTape, policy: FollowPolicy, clock: NominalClock, entry: int, atoms: int
) -> _Frozen:
    """``policy._find_exit`` before step 4: the leader and the timer as they are, then the stop
    quoted in Decimal for the copy at EVERY event of the tape after the entry, in slot order."""
    instant = clock.instant(entry)
    cap = clock.first_slot_at_or_after(instant + timedelta(seconds=policy.time_cap_seconds))
    best = _Frozen("time_cap", cap, cap + policy.delay_slots)
    leader = policy_mod._leader_exit(  # pyright: ignore[reportPrivateUsage]
        trigger, frozenset({trigger.wallet}), tape, policy, clock, entry
    )
    if leader is not None and leader.landing_slot < best.landing_slot:
        best = _Frozen(leader.reason, leader.fire_slot, leader.landing_slot)
    with localcontext(CONTEXT):
        floor = policy.stop_fraction * policy.budget_lamports
    for event in tape.fills:
        if event.slot <= entry:
            continue
        if event.slot > best.landing_slot:
            break
        quote = sell_lamports(event.reserves, atoms, fee_bps=event.fee_bps)
        with localcontext(CONTEXT):
            stopped = quote is not None and Decimal(quote) <= floor
        if stopped:
            landing = policy_mod._landing(event, policy, clock, entry)  # pyright: ignore[reportPrivateUsage]
            if landing < best.landing_slot:
                best = _Frozen("stop", event.slot, landing)
    return best


def _state(rng: random.Random, sol: int, *, refusing: bool, extreme: bool) -> Reserves:
    u = rng.random()
    if extreme and u < 0.02:  # outside the monotone region for a copy's atoms
        return Reserves("curve", 10**21 + rng.randrange(10**20), 10**6, 0)
    if u < 0.05:
        return curve(sol, _K // sol, complete=True)
    if refusing and u < 0.06:
        return curve(sol, _K // sol, real_sol=-1)
    if u < 0.45:
        return curve(sol, _K // sol)
    virtual = rng.choice((0, 20 * SOL, -(sol // 2)))
    return pool(sol, _K // sol, virtual=virtual)


def _tape(seed: int, n: int, *, refusing: bool = False, extreme: bool = True) -> MintTape:
    rng = random.Random(seed)
    sol, slot, events = 45 * SOL, 1_000, list[Fill]()
    for i in range(n):
        slot += rng.choice((0, 0, 1, 1, 2, 5))
        side = "buy" if rng.random() < 0.55 else "sell"
        sol = min(84 * SOL, sol + SOL // 2) if side == "buy" else max(31 * SOL, sol - 3 * SOL)
        late = rng.choice((0.3, 0.5, 2.0, 40.0)) if rng.random() < 0.2 else 0.5
        events.append(fill(wallet=f"W{i % 37}", side=side, slot=slot, sol=SOL // 5,
                           atoms=TOKEN * rng.randrange(1, 9_000), received_delay=late,
                           fee_bps=rng.choice((0, 25, 100, 125, 130, 9_999)),
                           reserves=_state(rng, sol, refusing=refusing, extreme=extreme)))  # fmt: skip
    return MintTape(events)


def _outcome(fn: object, *args: object) -> object:
    try:
        return fn(*args)  # type: ignore[operator]
    except ValueError as exc:
        return ("ValueError", str(exc))


def _differential(tape: MintTape, seed: int, copies: int) -> int:
    rng = random.Random(seed)
    buys = [f for f in tape.fills if f.side == "buy"]
    stops_seen = 0
    for _ in range(copies):
        trigger, policy = rng.choice(buys), rng.choice(POLICIES)
        clock = NominalClock.anchored_on(trigger.slot, trigger.block_time, policy.slot_seconds)
        entry = trigger.slot + policy.delay_slots
        atoms = rng.choice((1, rng.randrange(1, 10**9), rng.randrange(10**11, 10**14), 10**16))
        old = _outcome(_frozen_find_exit, trigger, tape, policy, clock, entry, atoms)
        new = _outcome(_find_exit, trigger, frozenset({trigger.wallet}), tape, policy, clock,
                       entry, atoms, (0, 0), None)  # fmt: skip
        if isinstance(old, _Frozen):
            assert isinstance(new, policy_mod._Exit), (old, new)  # pyright: ignore[reportPrivateUsage]
            assert (new.reason, new.fire_slot, new.landing_slot) == (
                old.reason, old.fire_slot, old.landing_slot)  # fmt: skip
            stops_seen += old.reason == "stop"
        else:
            assert new == old
    return stops_seen


@pytest.mark.parametrize("seed", range(6))
def test_the_threshold_scan_finds_the_same_exit_as_the_quote_scan(seed: int) -> None:
    tape = _tape(seed, 700)
    assert _differential(tape, 100 + seed, 400) > 20  # the fixture does stop copies


def test_a_refusing_state_still_refuses_through_the_threshold_scan() -> None:
    """A curve with a negative real SOL refuses every sale (``ValueError``); a copy whose window
    crosses it must still raise — the index never turns a refusal into "not stopped"."""
    tape = _tape(7, 500, refusing=True)
    assert any(f.reserves.real_sol_lamports == -1 for f in tape.fills)
    rng, raised = random.Random(8), 0
    for _ in range(300):
        trigger = rng.choice([f for f in tape.fills if f.side == "buy"])
        clock = NominalClock.anchored_on(trigger.slot, trigger.block_time, POLICIES[0].slot_seconds)
        entry, atoms = trigger.slot + 5, rng.randrange(10**11, 10**14)
        old = _outcome(_frozen_find_exit, trigger, tape, POLICIES[0], clock, entry, atoms)
        new = _outcome(_find_exit, trigger, frozenset({trigger.wallet}), tape, POLICIES[0], clock,
                       entry, atoms, (0, 0), None)  # fmt: skip
        raised += isinstance(old, tuple)
        if isinstance(old, tuple):
            assert new == old  # the same refusal, message included (Astra, diff review)
        else:
            assert not isinstance(new, tuple)
    assert raised > 10


def _steady_tape(n: int) -> MintTape:
    """A busy hour that stops nobody: the price wobbles ±2 SOL around 45 SOL, curve and pool
    (no virtual quote) alternating on the same numbers — every copy scans to its time cap."""
    rng = random.Random(11)
    events: list[Fill] = []
    for i in range(n):
        sol = 45 * SOL + rng.randrange(-2 * SOL, 2 * SOL)
        state = curve(sol, _K // sol) if i % 2 else pool(sol, _K // sol)
        events.append(fill(wallet=f"W{i % 37}", side="buy", slot=1_000 + i // 2, sol=SOL // 5,
                           atoms=TOKEN, reserves=state, fee_bps=125))  # fmt: skip
    return MintTape(events)


def test_the_stop_quotes_are_per_event_not_per_copy_and_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of step 4: 300 copies over one busy tape quoted every event of their exit
    window each (copies × events); the index quotes each event a bounded number of times."""
    tape = _steady_tape(12_000)  # 2 per slot: 6 000 slots, inside the 9 000-slot time cap
    calls = [0]

    def counted(state: Reserves, atoms: int, *, fee_bps: int) -> int | None:
        calls[0] += 1
        return sell_lamports(state, atoms, fee_bps=fee_bps)

    monkeypatch.setattr(stops, "sell_lamports", counted)
    rng = random.Random(10)
    triggers = rng.sample(tape.fills[:4_000], 300)
    atoms = buy_atoms(curve(45 * SOL, _K // (45 * SOL)), POLICIES[0].budget_lamports, fee_bps=125)
    assert atoms is not None
    frozen_quotes = 0
    for trigger in triggers:
        clock = NominalClock.anchored_on(trigger.slot, trigger.block_time, POLICIES[0].slot_seconds)
        entry = trigger.slot + 5
        found = _find_exit(trigger, frozenset({trigger.wallet}), tape, POLICIES[0], clock, entry,
                           atoms, (0, 0), None)  # fmt: skip
        assert found.reason == "time_cap"
        frozen_quotes += sum(1 for f in tape.fills if entry < f.slot <= found.landing_slot)
    assert calls[0] <= 3 * len(tape.fills)  # each event solved once, ≈ 2 certifying quotes
    assert frozen_quotes > 100 * calls[0]  # the old scan: one quote per (copy, event)
