"""Copy-trade pilot (H-037): balance legs -> LeaderEvent, offline and pure.

The channel carries absolute balances, so the delta needs the previous balance: learned from the
previous leg, or seeded once per (re)connect with a per-asset slot cut. A SOL leg that has not arrived is
``None``, never zero; a buy waits (bounded) for it, a sell does not. Placeholders only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hunter_exchanges.pumpfun.leader_events import LeaderEvent
from hunter_exchanges.pumpfun.leader_source_nats_io import WalletSnapshot
from hunter_exchanges.pumpfun.leader_source_nats_state import (
    PAIR_WAIT_S,
    BalanceBook,
    LegOutcome,
    LegProcessor,
)
from hunter_exchanges.pumpfun.leader_source_nats_wire import BalanceLeg

pytestmark = pytest.mark.unit

W, M = "WalletA", "MintA"
WSOL = "So11111111111111111111111111111111111111112"
T0 = datetime(2026, 10, 9, 12, 0, 0, tzinfo=UTC)
SERVER = datetime(2026, 10, 9, 11, 59, 59, 800000, tzinfo=UTC)


def leg(
    mint: str, atoms: int, sig: str, slot: int = 100, idx: int = 1, wallet: str = W
) -> BalanceLeg:
    return BalanceLeg(wallet, mint, atoms, slot, idx, sig, SERVER)


def at(ms: int) -> datetime:
    return T0 + timedelta(milliseconds=ms)


def seeded(tokens: dict[str, int] | None = None, sol: int = 10**10, slot: int = 90) -> LegProcessor:
    book = BalanceBook()
    held = {m: (a, slot) for m, a in (tokens or {}).items()}
    book.seed(W, WalletSnapshot(sol_lamports=sol, sol_slot=slot, tokens=held, tokens_slot=slot))
    return LegProcessor(book)


def feed(proc: LegProcessor, item: BalanceLeg, ms: int = 0, mono: float = 0.0) -> LegOutcome:
    return proc.on_leg(item, seen_at=at(ms), now_mono=mono)


def settled(proc: LegProcessor, item: BalanceLeg) -> tuple[LeaderEvent, ...]:
    """The events of a leg once its buy-wait is over (no SOL leg comes in these tests)."""
    out = feed(proc, item, mono=0.0)
    return out.events or tuple(proc.expire(now_mono=99.0, now_wall=at(500)))


# ----------------------------------------------------------------------------- baselines
def test_first_sighting_without_a_seed_learns_the_baseline_and_emits_nothing() -> None:
    proc = LegProcessor(BalanceBook())
    out = feed(proc, leg(M, 5_000_000, "s1"))
    assert out.events == () and out.reason == "no_baseline"
    out2 = feed(proc, leg(M, 8_000_000, "s2", slot=101), mono=5.0)
    assert out2.reason == "pending_sol"  # a buy: it now waits for the SOL leg
    (ev,) = proc.expire(now_mono=6.0, now_wall=at(1000))
    assert ev.token_delta_atoms == 3_000_000 and ev.sol_delta_lamports is None


def test_a_seeded_wallet_treats_an_unlisted_mint_as_zero_after_the_cut() -> None:
    proc = seeded()
    feed(proc, leg("SOL", 9_000_000_000, "s1"), 0)
    (ev,) = feed(proc, leg(M, 4_000_000, "s1"), 1).events
    assert (ev.side, ev.token_delta_atoms, ev.position_after_atoms) == ("buy", 4_000_000, 4_000_000)
    assert ev.sol_delta_lamports == -1_000_000_000 and not ev.multi_mint and ev.kind == "unknown"
    assert (ev.source, ev.confirmed, ev.block_time) == ("nats", False, None)
    assert (ev.wallet, ev.mint, ev.signature, ev.slot, ev.server_ts) == (W, M, "s1", 100, SERVER)


def test_a_leg_at_or_before_the_snapshot_slot_is_not_a_delta_of_the_snapshot() -> None:
    """A snapshot read at slot 90 already contains every transaction of slot 90: a leg of that slot
    (or older) compared with it would be comparing past with future."""
    proc = seeded({M: 12_000_000}, slot=90)
    same = feed(proc, leg(M, 7_000_000, "late", slot=90, idx=999))
    older = feed(proc, leg(M, 7_000_000, "old", slot=89))
    assert same.events == () and older.events == ()
    assert same.reason == "stale" and older.reason == "stale"
    (ev,) = settled(proc, leg(M, 20_000_000, "next", slot=91))
    assert ev.token_delta_atoms == 8_000_000


def test_a_mint_the_snapshot_did_not_list_is_zero_only_after_the_newest_token_read() -> None:
    book = BalanceBook()
    book.seed(
        W,
        WalletSnapshot(sol_lamports=1, sol_slot=100, tokens={"X": (5, 98)}, tokens_slot=100),
    )
    proc = LegProcessor(book)
    early = feed(proc, leg(M, 4_000_000, "s1", slot=99))  # inside the read window: cannot say
    assert early.events == () and early.reason == "stale"
    (ev,) = settled(proc, leg(M, 9_000_000, "s2", slot=101))
    assert (
        ev.token_delta_atoms == 9_000_000
    )  # the snapshot said zero at the cut: the 4 never counts
    fresh = settled(proc, leg("Y", 3_000_000, "s3", slot=102))
    assert fresh[0].token_delta_atoms == 3_000_000  # unlisted, after the cut: it was zero


def test_a_seed_that_does_not_list_a_mint_discards_a_baseline_learned_before_its_cut() -> None:
    book = BalanceBook()
    proc = LegProcessor(book)
    feed(proc, leg(M, 4_000_000, "s1", slot=99))  # learned while unseeded, older than the cut
    book.seed(W, WalletSnapshot(sol_lamports=1, sol_slot=100, tokens={}, tokens_slot=100))
    (ev,) = settled(proc, leg(M, 2_000_000, "s2", slot=101))
    assert (ev.side, ev.token_delta_atoms) == ("buy", 2_000_000)  # not a false -2 sell


def test_a_late_seed_never_overwrites_a_newer_leg() -> None:
    book = BalanceBook()
    proc = LegProcessor(book)
    feed(proc, leg(M, 7_000_000, "s1", slot=120))
    book.seed(
        W,
        WalletSnapshot(
            sol_lamports=5, sol_slot=110, tokens={M: (1, 110), "O": (9, 110)}, tokens_slot=110
        ),
    )
    (ev,) = settled(proc, leg(M, 9_000_000, "s2", slot=121))
    assert ev.token_delta_atoms == 2_000_000
    (other,) = settled(proc, leg("O", 10, "s3", slot=122))
    assert other.token_delta_atoms == 1


def test_wallets_do_not_share_baselines_and_forget_drops_one() -> None:
    book = BalanceBook()
    book.seed("W1", WalletSnapshot(0, 1, {}, 1))
    proc = LegProcessor(book)
    assert feed(proc, leg(M, 5, "s1", wallet="W2")).reason == "no_baseline"
    assert book.is_seeded("W1")
    book.forget("W1")
    assert not book.is_seeded("W1")


def test_wrapped_sol_and_unchanged_balances_are_not_events() -> None:
    proc = seeded({M: 1_000_000})
    assert feed(proc, leg(WSOL, 1_000_000, "s1")).reason == "wsol"
    assert feed(proc, leg(M, 1_000_000, "s2", slot=101)).reason == "no_change"


# ----------------------------------------------------------------------------- the SOL leg
def test_a_sell_is_emitted_at_once_and_a_missing_sol_leg_is_none_not_zero() -> None:
    proc = seeded({M: 10_000_000})
    out = feed(proc, leg(M, 6_000_000, "s1"), 3)
    (ev,) = out.events
    assert (ev.side, ev.token_delta_atoms, ev.position_after_atoms) == (
        "sell",
        -4_000_000,
        6_000_000,
    )
    assert ev.sol_delta_lamports is None and ev.first_seen_at == ev.fields_complete_at == at(3)
    assert out.deadline_mono is None


def test_a_sell_with_the_sol_leg_already_seen_carries_it() -> None:
    proc = seeded({M: 10_000_000})
    feed(proc, leg("SOL", 10**10 + 2_000_000, "s1"), 0)
    (ev,) = feed(proc, leg(M, 0, "s1"), 4).events
    assert ev.sol_delta_lamports == 2_000_000 and ev.position_after_atoms == 0
    assert (ev.first_seen_at, ev.fields_complete_at) == (at(0), at(4))


def test_a_buy_waits_for_the_sol_leg_and_completes_the_instant_it_arrives() -> None:
    proc = seeded()
    waiting = feed(proc, leg(M, 4_000_000, "s1"), 0, mono=10.0)
    assert waiting.events == () and waiting.reason == "pending_sol"
    assert waiting.deadline_mono == pytest.approx(10.0 + PAIR_WAIT_S)
    out = feed(proc, leg("SOL", 9_000_000_000, "s1"), 5, mono=10.005)
    (ev,) = out.events
    assert ev.side == "buy" and ev.sol_delta_lamports == -1_000_000_000
    assert (ev.first_seen_at, ev.fields_complete_at) == (at(0), at(5))


def test_a_buy_whose_sol_leg_never_comes_is_emitted_with_none_at_the_deadline() -> None:
    proc = seeded()
    feed(proc, leg(M, 4_000_000, "s1"), 0, mono=10.0)
    assert proc.expire(now_mono=10.1, now_wall=at(100)) == []
    (ev,) = proc.expire(now_mono=10.0 + PAIR_WAIT_S, now_wall=at(300))
    assert ev.sol_delta_lamports is None and ev.fields_complete_at == at(300)
    assert proc.expire(now_mono=11.0, now_wall=at(400)) == []  # emitted once


def test_the_pairing_deadline_is_decided_by_the_clock_not_by_callback_order() -> None:
    """The event loop was late: the SOL leg is processed at 350 ms, before the overdue timer ran. The
    buy was already out of time, so it goes out with None — the same as if the timer had come first."""
    proc = seeded()
    feed(proc, leg(M, 4_000_000, "s1"), 0, mono=10.0)
    out = feed(proc, leg("SOL", 9_000_000_000, "s1"), 350, mono=10.35)
    (ev,) = out.events
    assert ev.sol_delta_lamports is None


def test_pending_buys_are_never_evicted_by_a_bound() -> None:
    proc = seeded()
    for i in range(700):
        feed(proc, leg(M, 1_000_000 * (i + 1), f"s{i}", slot=100 + i), 0, mono=1.0)
    assert len(proc.expire(now_mono=2.0, now_wall=at(500))) == 700


def test_a_sol_leg_that_arrives_after_the_event_never_rewrites_it() -> None:
    proc = seeded()
    feed(proc, leg(M, 4_000_000, "s1"), 0, mono=10.0)
    proc.expire(now_mono=11.0, now_wall=at(1000))
    late = feed(proc, leg("SOL", 9_000_000_000, "s1"), 1200, mono=11.2)
    assert late.events == () and late.reason == "sol_leg"


def test_two_mints_in_one_transaction_are_multi_mint_with_no_sol_attributed() -> None:
    proc = seeded()
    feed(proc, leg(M, 4_000_000, "s1"), 0, mono=1.0)
    feed(proc, leg("OtherMint", 2_000_000, "s1"), 1, mono=1.001)
    out = feed(proc, leg("SOL", 9_000_000_000, "s1"), 2, mono=1.002)
    assert sorted((e.mint, e.multi_mint, e.sol_delta_lamports) for e in out.events) == [
        (M, True, None),
        ("OtherMint", True, None),
    ]


def test_the_second_mint_after_the_first_was_emitted_is_multi_mint_too() -> None:
    proc = seeded()
    feed(proc, leg("SOL", 9_000_000_000, "s1"), 0)
    (first,) = feed(proc, leg(M, 4_000_000, "s1"), 1).events
    assert first.multi_mint is False and first.sol_delta_lamports == -1_000_000_000
    (second,) = feed(proc, leg("OtherMint", 2_000_000, "s1"), 2).events
    assert second.multi_mint is True and second.sol_delta_lamports is None


def test_tokens_in_without_sol_out_are_labelled_transfers_not_dropped() -> None:
    proc = seeded()
    feed(proc, leg("SOL", 10**10 + 2_000_000, "s1"), 0)  # SOL came IN
    (ev,) = feed(proc, leg(M, 4_000_000, "s1"), 1).events
    assert ev.kind == "transfer" and ev.side == "buy"


def test_tokens_out_without_sol_in_are_labelled_transfers_so_the_exit_still_sees_them() -> None:
    proc = seeded({M: 5_000_000})
    feed(proc, leg("SOL", 10**10 - 5_000, "s1"), 0)  # only the fee left
    (ev,) = feed(proc, leg(M, 0, "s1"), 1).events
    assert ev.kind == "transfer" and ev.side == "sell" and ev.position_after_atoms == 0


def test_a_redelivered_leg_is_stale_and_never_a_second_event() -> None:
    proc = seeded()
    feed(proc, leg("SOL", 9_000_000_000, "s1", slot=100, idx=5), 0)
    assert feed(proc, leg(M, 1_000_000, "s1", slot=100, idx=5), 1).events
    dup = feed(proc, leg(M, 1_000_000, "s1", slot=100, idx=5), 2)
    assert dup.events == () and dup.reason == "stale"


def test_the_metadata_of_a_pending_buy_survives_the_bound_that_trims_old_transactions() -> None:
    """Two buys of different mints wait on signature S; 600 other transactions pass before the SOL leg
    arrives. S must still be known as multi-mint and keep its first-seen stamp."""
    proc = seeded()
    feed(proc, leg(M, 4_000_000, "S"), 0, mono=1.0)
    feed(proc, leg("Other", 2_000_000, "S"), 1, mono=1.001)
    for i in range(600):
        item = BalanceLeg("Noisy", "SOL", 10 + i, 200 + i, 1, f"n{i}", SERVER)
        proc.on_leg(item, seen_at=at(5), now_mono=1.002)
    out = feed(proc, leg("SOL", 9_000_000_000, "S"), 9, mono=1.003)
    assert sorted((e.mint, e.multi_mint, e.sol_delta_lamports) for e in out.events) == [
        (M, True, None),
        ("Other", True, None),
    ]
    assert all(e.first_seen_at == at(0) for e in out.events)
