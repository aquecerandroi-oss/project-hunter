"""The three hooks the bounded-memory engine (wave 1c-bis) needs in the batch modules.

Each hook keeps the batch rule and only lets a caller feed part of the input as a summary:

1. ``simulate_copy(leader_prior=, leader_since=)`` — the leader's totals of what arrived before
   ``since`` replace those events in the "> half sold" count (``_leader_exit`` reads the leader's
   whole history in the mint, the trigger arms it);
2. ``fifo(charged=)`` and ``window_books(charged=)`` — the 5 000-lamport tx fee is charged once per
   (owner, signature) across mints; a caller replaying one mint at a time pre-seeds the pairs whose
   fee belongs to a fill of another mint.

Synthetic fixtures (not data): invented numbers, UTC.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.episodes import window_books
from hunter_indicators.meme.wallets.lots import fifo
from hunter_indicators.meme.wallets.params import FollowPolicy
from hunter_indicators.meme.wallets.policy import simulate_copy
from hunter_indicators.meme.wallets.pricing import MintTape
from hunter_indicators.meme.wallets.tape import Fill
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, at, curve, fill

pytestmark = pytest.mark.unit

S100 = curve(40 * SOL, 800_000_000 * TOKEN)
POLICY = FollowPolicy()


def _history() -> tuple[list[Fill], Fill]:
    """L bought 100 M and sold 100 M before ``S`` (slot 80/90); the 25 M trigger comes after."""
    old = [
        fill(wallet="L", side="buy", slot=80, sol=SOL // 20, atoms=100_000_000 * TOKEN, reserves=S100),
        fill(wallet="L", side="sell", slot=90, sol=SOL, atoms=100_000_000 * TOKEN, reserves=S100),
    ]  # fmt: skip
    trigger = fill(
        wallet="L", side="buy", slot=100, sol=SOL, atoms=25_000_000 * TOKEN, reserves=S100
    )
    return old, trigger


def test_the_leader_prior_replaces_the_events_received_before_since() -> None:
    old, trigger = _history()
    since = trigger.received_at - timedelta(seconds=1)  # both old events arrived before it
    full = simulate_copy(trigger, leader_wallets=frozenset({"L"}), tape=MintTape([*old, trigger]),
                         policy=POLICY, horizon_slot=20_000)  # fmt: skip
    # 100 M sold > 0.5 × 125 M: the exit fires on the trigger itself (whole-history rule)
    assert (full.reason, full.exit_fire_slot) == ("leader_sold", 100)
    # the reduced tape keeps only the last slot before ``since`` (the frontier) and later arrivals
    reduced = MintTape([old[1], trigger])
    blind = simulate_copy(trigger, leader_wallets=frozenset({"L"}), tape=reduced, policy=POLICY,
                          horizon_slot=20_000, leader_since=since)  # fmt: skip
    assert blind.reason == "time_cap"  # without the prior the history is lost
    summarized = simulate_copy(
        trigger,
        leader_wallets=frozenset({"L"}),
        tape=reduced,
        policy=POLICY,
        horizon_slot=20_000,
        leader_prior=(100_000_000 * TOKEN, 100_000_000 * TOKEN),
        leader_since=since,
    )
    assert summarized == full


def test_a_late_arrival_mined_before_since_still_counts_in_arrival_order() -> None:
    old, trigger = _history()
    since = trigger.received_at - timedelta(seconds=1)
    late_sale = fill(wallet="L", side="sell", slot=95, sol=SOL, atoms=10_000_000 * TOKEN,
                     reserves=S100, received_delay=30.0)  # fmt: skip
    full = simulate_copy(trigger, leader_wallets=frozenset({"L"}),
                         tape=MintTape([*old, late_sale, trigger]), policy=POLICY,
                         horizon_slot=20_000)  # fmt: skip
    reduced = simulate_copy(
        trigger,
        leader_wallets=frozenset({"L"}),
        tape=MintTape([old[1], late_sale, trigger]),
        policy=POLICY,
        horizon_slot=20_000,
        leader_prior=(100_000_000 * TOKEN, 100_000_000 * TOKEN),
        leader_since=since,
    )
    assert reduced == full


def _two_mint_tx() -> list[Fill]:
    """One signature buys X (ordinal 1) and Y (ordinal 0); only X is sold later."""
    return [
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=10 * TOKEN, mint="X", signature="tx", ordinal=1, fee_bps=0),
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=10 * TOKEN, mint="Y", signature="tx", ordinal=0, fee_bps=0),
        fill(wallet="A", side="sell", slot=20, sol=2 * SOL, atoms=10 * TOKEN, mint="X", fee_bps=0),
    ]  # fmt: skip


def test_fifo_charges_the_fee_where_a_preseeded_set_says() -> None:
    tape = _two_mint_tx()
    whole = fifo(tape, owner_of=str)
    # the fee of "tx" is Y's (ordinal 0): X's lot costs exactly 1 SOL
    x_only = fifo([f for f in tape if f.mint == "X"], owner_of=str, charged={("A", "tx")})
    assert x_only.realized_lamports == whole.realized_lamports == SOL - 5_000
    naive = fifo([f for f in tape if f.mint == "X"], owner_of=str)
    assert naive.realized_lamports == SOL - 10_000  # charged in X: the realized PnL is wrong


def test_window_books_take_the_same_preseeded_set() -> None:
    tape = _two_mint_tx()
    tapes = {"X": MintTape(tape[::2]), "Y": MintTape(tape[1:2])}
    whole = window_books(tape, owner_of=str, opening=(), tapes=tapes, start=T0, days=1)
    x_only = window_books([tape[0], tape[2]], owner_of=str, opening=(), tapes={"X": tapes["X"]},
                          start=at(0), days=1, charged={("A", "tx")})  # fmt: skip
    x_whole = next(e for e in whole["A"].episodes if e.mint == "X")
    assert x_only["A"].episodes[0].daily == x_whole.daily
    assert x_whole.result_lamports == SOL - 5_000
