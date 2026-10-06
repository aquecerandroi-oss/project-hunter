"""CPU plan step 2 (06/10/2026): repeated or wasted work removed from the hot path, rules unchanged.

Each test pins one removal by the work it no longer does (never by wall time) and, where a helper
is shared with the batch engine, checks it against a frozen copy of the code it replaced; the
whole-engine guard is ``test_wallets_golden`` (digests frozen from commit ``84704fa1``).
Synthetic fixtures (not data).
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_FLOOR, Decimal, localcontext
from typing import SupportsIndex, overload

import pytest

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.meme import curve as curve_mod
from hunter_indicators.meme.wallets import policy as policy_mod
from hunter_indicators.meme.wallets import pricing
from hunter_indicators.meme.wallets.carry import Flow, initial_carry
from hunter_indicators.meme.wallets.clock import NominalClock
from hunter_indicators.meme.wallets.params import FollowPolicy, RankingParams
from hunter_indicators.meme.wallets.policy import (
    _find_exit,  # pyright: ignore[reportPrivateUsage]
    _leader_exit,  # pyright: ignore[reportPrivateUsage]
    simulate_copy,
)
from hunter_indicators.meme.wallets.policy import (
    _stop_floor as stop_floor,  # pyright: ignore[reportPrivateUsage]
)
from hunter_indicators.meme.wallets.pricing import MintTape, sell_lamports
from hunter_indicators.meme.wallets.ranking import cut_of
from hunter_indicators.meme.wallets.stream import StreamInputs, shared_signatures, stream_snapshot
from hunter_indicators.meme.wallets.tape import Fill, Reserves
from packages.indicators.tests.meme.stream_harness import World, mint_windows
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, curve, fill

pytestmark = pytest.mark.unit

_SOL, _TOK = Decimal(SOL), Decimal(TOKEN)
POLICY = FollowPolicy()


def _frozen_curve_sale(state: Reserves, atoms: int, bps: int) -> int:
    """``pricing.sell_lamports`` on a curve as it was at ``84704fa1`` (a full ``quote_sell``)."""
    assert state.real_sol_lamports is not None
    with localcontext(CONTEXT):
        reserves = curve_mod.CurveReserves(
            Decimal(state.sol_lamports) / _SOL, Decimal(state.token_atoms) / _TOK
        )
        quote = curve_mod.quote_sell(reserves, Decimal(atoms) / _TOK, Decimal(0),
                                     real_sol_reserves=Decimal(state.real_sol_lamports) / _SOL)  # fmt: skip
        gross = int((quote.curve_proceeds_sol * _SOL).to_integral_value(rounding=ROUND_FLOOR))
    return gross - -(-gross * bps // 10_000)


def test_a_curve_sale_quote_builds_no_full_sell_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stop check quotes every observed state of every copy; the fee, after-state and
    marginal price of a full ``quote_sell`` were computed there and thrown away."""
    state = curve(40 * SOL)
    expected = _frozen_curve_sale(state, 5_000_000 * TOKEN, 125)

    def full_quote(*_: object, **__: object) -> object:
        raise AssertionError("a full SellQuote was built for a gross-only quote")

    monkeypatch.setattr(pricing, "quote_sell", full_quote, raising=False)
    assert sell_lamports(state, 5_000_000 * TOKEN, fee_bps=125) == expected


def test_the_curve_sale_equals_the_frozen_quote_everywhere() -> None:
    """Same lamport on a seeded grid: cap binding or not, dust to whale sizes, all fee rates."""
    rng = random.Random(6)
    for _ in range(4_000):
        sol = rng.randrange(30 * SOL + 1, 400 * SOL)
        real = rng.choice((sol - 30 * SOL, rng.randrange(0, 3 * SOL), 0))
        state = Reserves("curve", sol, rng.randrange(1, 1_073) * 1_000_000 * TOKEN, real)
        atoms = rng.choice((1, rng.randrange(1, 10**9), rng.randrange(1, 10**16), 10**18))
        bps = rng.choice((0, 1, 95, 100, 125, 9_999))
        assert sell_lamports(state, atoms, fee_bps=bps) == _frozen_curve_sale(state, atoms, bps)


def test_a_negative_real_sol_is_still_refused() -> None:
    state = Reserves("curve", 40 * SOL, 800_000_000 * TOKEN, -1)
    with pytest.raises(ValueError, match="real_sol_reserves"):
        sell_lamports(state, TOKEN, fee_bps=100)


def test_a_state_is_converted_to_decimal_once_not_once_per_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every copy whose stop scan crosses an event re-converted that event's state to Decimal."""
    made: list[object] = []

    def counting(sol: Decimal, tokens: Decimal) -> curve_mod.CurveReserves:
        made.append((sol, tokens))
        return curve_mod.CurveReserves(sol, tokens)

    monkeypatch.setattr(pricing, "CurveReserves", counting)
    pricing._curve_of.cache_clear()  # pyright: ignore[reportPrivateUsage]
    state = curve(41 * SOL + 7, 777_000_000 * TOKEN + 3)
    quotes = {sell_lamports(state, a * TOKEN, fee_bps=125) for a in range(1, 300)}
    assert len(quotes) > 1 and len(made) == 1  # was 299 conversions
    assert sell_lamports(state, 9 * TOKEN, fee_bps=125) == _frozen_curve_sale(state, 9 * TOKEN, 125)


class _Counted(tuple[Fill, ...]):
    """A tape's events that count how many are read (iterated or indexed)."""

    reads: int = 0

    def __iter__(self) -> Iterator[Fill]:
        for item in super().__iter__():
            self.reads += 1
            yield item

    @overload
    def __getitem__(self, i: SupportsIndex, /) -> Fill: ...
    @overload
    def __getitem__(self, i: slice, /) -> tuple[Fill, ...]: ...
    def __getitem__(self, i: SupportsIndex | slice, /) -> Fill | tuple[Fill, ...]:
        if isinstance(i, slice):
            part = super().__getitem__(i)
            self.reads += len(part)
            return part
        self.reads += 1
        return super().__getitem__(i)


def _busy_tape(late: float) -> tuple[MintTape, list[Fill]]:
    """3 000 early events by others, then 40 distinct leaders' buys in consecutive slots."""
    early = [fill(wallet=f"X{i % 50}", side="buy", slot=100 + i, sol=SOL // 10,
                  atoms=TOKEN * 1_000, reserves=curve(40 * SOL)) for i in range(3_000)]  # fmt: skip
    triggers = [fill(wallet=f"L{i}", side="buy", slot=10_000 + i, sol=SOL // 5, atoms=TOKEN * 9_000,
                     reserves=curve(41 * SOL), received_delay=late) for i in range(40)]  # fmt: skip
    tape = MintTape([*early, *triggers])
    tape.fills = _Counted(tape.fills)
    return tape, triggers


def test_the_wallet_index_returns_the_filtered_subsequence_even_with_a_repeated_wallet() -> None:
    """Astra (step-2 review): ``['A', 'A', 'B']`` returned A's events twice."""
    tape, _ = _busy_tape(late=0.5)
    for wallets in (["X1", "X1", "X2"], ["L3", "X1", "L3"], [], ["nobody"]):
        expected = [f for f in tape.fills if f.wallet in set(wallets)]
        assert tape.of_wallets(wallets) == expected


def _no_leader(*_: object, **__: object) -> None:
    return None


def _reads(tape: MintTape) -> int:
    assert isinstance(tape.fills, _Counted)
    return tape.fills.reads


def test_each_copy_does_not_rescan_the_tape_for_its_trigger() -> None:
    """``simulate_copy`` refuses a tape without the trigger; that check walked the tape per copy."""
    tape, triggers = _busy_tape(late=30.0)  # every copy is refused late, right after the check
    for t in triggers:
        out = simulate_copy(t, leader_wallets=frozenset({t.wallet}), tape=tape, policy=POLICY,
                            horizon_slot=20_000)  # fmt: skip
        assert (out.status, out.reason) == ("refused", "late_event")
    assert _reads(tape) < 2 * len(tape.fills)  # was ≈ 40 × 3 040


def _clock(t: Fill) -> NominalClock:
    return NominalClock.anchored_on(t.slot, t.block_time, POLICY.slot_seconds)


def test_each_copy_does_not_refilter_the_tape_for_its_leader() -> None:
    """The leader's arrivals were filtered out of the whole tape once per copy."""
    tape, triggers = _busy_tape(late=0.5)
    for t in triggers:
        entry = t.slot + POLICY.delay_slots
        _leader_exit(t, frozenset({t.wallet, "X3"}), tape, POLICY, _clock(t), entry)
    assert _reads(tape) < 2 * len(tape.fills)  # was 40 × 3 040


def test_the_stop_scan_starts_after_the_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stop is only checked after the entry slot; the scan walked every earlier event."""
    tape, triggers = _busy_tape(late=0.5)
    monkeypatch.setattr(policy_mod, "_leader_exit", _no_leader)
    for t in triggers:
        entry = t.slot + POLICY.delay_slots
        _find_exit(t, frozenset({t.wallet}), tape, POLICY, _clock(t), entry, TOKEN, (0, 0), None)
    assert _reads(tape) < 2 * len(tape.fills)  # was ≈ 40 × 3 040


class _CountedFlows(tuple[Flow, ...]):
    reads: int = 0

    def __iter__(self) -> Iterator[Flow]:
        for item in super().__iter__():
            self.reads += 1
            yield item


def test_a_mint_replay_reads_its_carried_flows_once_not_once_per_copy() -> None:
    """``MintCarry.flow_of`` rebuilt a dict of every carried flow of the mint for each copy.

    120 wallets buy mint F on day 0 (carried flows at the next window start); 40 of them then
    trigger in the window of the second night (window 2 d)."""
    day_slots = 216_000
    history = [fill(wallet=f"W{i:03d}", side="buy", slot=1_000 + i, sol=SOL // 50,
                    atoms=TOKEN * 1_000, mint="F") for i in range(120)]  # fmt: skip
    triggers = [fill(wallet=f"W{i:03d}", side="buy", slot=2 * day_slots + 1_000 + 20 * i,
                     sol=SOL // 5, atoms=TOKEN * 900, mint="F") for i in range(40)]  # fmt: skip
    world = World(T0, (*history, *triggers))
    params = RankingParams(window_days=2)
    carry, first = initial_carry(world.origin, window_days=2)
    mints = {m.mint: m for m in first}
    shared = shared_signatures(world.fills)
    counted = _CountedFlows()
    copies = 0
    for k in (2, 3):
        day = (T0 + timedelta(days=k)).date()
        if k == 3:
            counted = _CountedFlows(mints["F"].flows)
            mints["F"] = replace(mints["F"], flows=counted)
        windows = mint_windows(world, mints, cut_of(day) - timedelta(days=2))
        out = stream_snapshot(StreamInputs(carry, lambda w=windows: iter(w), shared), day,
                              params=params)  # fmt: skip
        carry, mints = out.carry, {m.mint: m for m in out.mint_carries}
        copies = sum(r.metrics.copies + r.metrics.copies_incomplete
                     for r in out.snapshot.rows.values() if r.metrics is not None)  # fmt: skip
    assert (len(counted), copies) == (120, 40)  # the fixture has the flows and the copies
    assert counted.reads <= 3 * len(counted)  # was (40 copies + 1) × 120


def test_the_stop_floor_is_computed_once_per_copy_not_per_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stop compares each state's quote with ``stop_fraction × budget``; that product was
    recomputed for every event the scan crossed. (The comparison itself stays inside
    ``localcontext(CONTEXT)``, per event, for parity with the old code — review round 3.)
    A non-finite ``stop_fraction``, where computing the floor early or late would differ, is
    refused when the policy is built (``test_wallets_params``)."""
    trigger = fill(wallet="L", side="buy", slot=1_000, sol=SOL // 5, atoms=TOKEN * 9_000)
    after = [fill(wallet=f"Y{i}", side="buy", slot=1_010 + i, sol=SOL // 10, atoms=TOKEN,
                  reserves=curve(45 * SOL)) for i in range(500)]  # fmt: skip
    tape = MintTape([trigger, *after])
    floors: list[Decimal] = []

    def counting(policy: FollowPolicy) -> Decimal:
        floors.append(stop_floor(policy))
        return floors[-1]

    monkeypatch.setattr(policy_mod, "_leader_exit", _no_leader)
    monkeypatch.setattr(policy_mod, "_stop_floor", counting)
    atoms = 10_000_000 * TOKEN  # worth far more than the floor: no stop, the whole hour is scanned
    found = _find_exit(trigger, frozenset({"L"}), tape, POLICY, _clock(trigger), 1_005, atoms,
                       (0, 0), None)  # fmt: skip
    assert found.reason == "time_cap" and len(floors) == 1  # was one per scanned event (500)
