"""Episodes and the E-PnL (§1 item 2): window cash flows of matched trades plus
the liquidation value of the inventory at the end minus at the start; the same
valuation at every boundary, so daily contributions telescope to the window.
Fees and the tx fee are zero here so every expected value is a hand sum.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from hunter_indicators.meme.wallets.episodes import window_books
from hunter_indicators.meme.wallets.lots import Lot
from hunter_indicators.meme.wallets.pricing import MintTape, sell_lamports
from hunter_indicators.meme.wallets.tape import Fill, Gap, Reserves
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, curve, fill

pytestmark = pytest.mark.unit

DAY_SLOTS = 216_000  # 86 400 s / 0.4 s
S1 = curve(40 * SOL, 800_000_000 * TOKEN)
S2 = curve(60 * SOL, 533_333_333 * TOKEN)


def _value(state: Reserves, atoms: int) -> int:
    v = sell_lamports(state, atoms, fee_bps=0)
    assert v is not None
    return v


def _books(fills: list[Fill], market: list[Fill] | None = None, opening: tuple[Lot, ...] = ()):
    everything = [*fills, *(market or [])]
    tapes = {"MINT": MintTape([f for f in everything if f.mint == "MINT"])}
    return window_books(
        fills,
        owner_of=lambda w: w,
        opening=opening,
        tapes=tapes,
        start=T0,
        days=7,
        tx_fee_lamports=0,
    )


def test_a_round_trip_inside_one_day_is_one_closed_episode_with_its_cash_result() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=100 * TOKEN, fee_bps=0),
        fill(wallet="A", side="sell", slot=200, sol=3 * SOL // 2, atoms=100 * TOKEN, fee_bps=0),
    ]
    (book,) = _books(fills).values()
    (ep,) = book.episodes
    assert ep.closed
    assert ep.result_lamports == SOL // 2
    assert ep.cost_lamports == SOL
    assert ep.daily == (SOL // 2, 0, 0, 0, 0, 0, 0)
    assert ep.hold_seconds == 76.0  # block_time floors: slot 10 → +4 s, slot 200 → +80 s
    assert book.e_pnl_lamports == SOL // 2


def test_a_bag_held_to_the_cut_counts_its_loss_once_through_liquidation() -> None:
    held = 100_000_000 * TOKEN
    buy = fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=held, reserves=S1, fee_bps=0)
    later = fill(
        wallet="X", side="sell", slot=3 * DAY_SLOTS, sol=SOL, atoms=TOKEN, reserves=S2, fee_bps=0
    )
    (book,) = _books([buy], market=[later]).values()
    (ep,) = book.episodes
    v1, v7 = _value(S1, held), _value(S2, held)
    assert not ep.closed
    assert ep.daily[0] == -SOL + v1
    assert ep.daily[3] == v7 - v1  # the trade at exactly T0+3d is first seen by boundary 4
    assert sum(ep.daily) == ep.result_lamports == -SOL + v7
    assert book.e_pnl_lamports == -SOL + v7


def test_an_opening_lot_is_valued_at_the_window_start_not_at_its_old_cost() -> None:
    # Astra's case: bought for 1 before, worth v0 at the start, sold in the window for 2.1 SOL
    before = fill(
        wallet="X", side="buy", slot=-100, sol=SOL, atoms=TOKEN, reserves=S1, fee_bps=0, t=-40
    )
    lot = Lot("A", "MINT", 50 * TOKEN, SOL, -500, T0 - timedelta(hours=1))
    sale = fill(wallet="A", side="sell", slot=10, sol=21 * SOL // 10, atoms=50 * TOKEN, fee_bps=0)
    (book,) = _books([sale], market=[before], opening=(lot,)).values()
    (ep,) = book.episodes
    v0 = _value(S1, 50 * TOKEN)
    assert ep.open_at_start
    assert ep.result_lamports == 21 * SOL // 10 - v0
    assert ep.cost_lamports == v0


def test_unmatched_part_of_a_sale_is_left_out_of_cash_and_counted() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=60 * TOKEN, fee_bps=0),
        fill(wallet="A", side="sell", slot=20, sol=2 * SOL, atoms=100 * TOKEN, fee_bps=0),
    ]
    (book,) = _books(fills).values()
    assert book.episodes[0].result_lamports == 2 * SOL * 60 // 100 - SOL
    assert (book.unmatched_atoms, book.sold_atoms) == (40 * TOKEN, 100 * TOKEN)


def test_hold_is_the_atom_weighted_median_so_a_quick_flip_is_not_masked() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=0, sol=SOL, atoms=100 * TOKEN, fee_bps=0),
        fill(wallet="A", side="sell", slot=1, sol=SOL, atoms=99 * TOKEN, fee_bps=0),
        fill(wallet="A", side="sell", slot=9_000, sol=SOL // 100, atoms=TOKEN, fee_bps=0),
    ]
    (book,) = _books(fills).values()
    (ep,) = book.episodes
    assert (ep.hold_slots, ep.hold_seconds) == (1, 0.0)


def test_no_valid_state_at_the_cut_values_the_bag_at_zero() -> None:
    late_only = fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=TOKEN, fee_bps=0)
    tapes = {"MINT": MintTape([])}
    books = window_books(
        [late_only],
        owner_of=lambda w: w,
        opening=(),
        tapes=tapes,
        start=T0,
        days=7,
        tx_fee_lamports=0,
    )
    assert books["A"].e_pnl_lamports == -SOL


def test_twins_merge_into_one_owner_episode() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=10 * TOKEN, fee_bps=0),
        fill(wallet="B", side="sell", slot=20, sol=2 * SOL, atoms=10 * TOKEN, fee_bps=0),
    ]
    tapes = {"MINT": MintTape(fills)}
    books = window_books(
        fills, owner_of=lambda _w: "E", opening=(), tapes=tapes, start=T0, days=7, tx_fee_lamports=0
    )
    assert books["E"].e_pnl_lamports == SOL
    assert books["E"].unmatched_atoms == 0


def test_an_opening_lot_with_unknown_cost_marks_the_episode_incomplete() -> None:
    lot = Lot("A", "MINT", 50 * TOKEN, None, -500, T0 - timedelta(hours=1))
    sale = fill(wallet="A", side="sell", slot=10, sol=SOL, atoms=50 * TOKEN, fee_bps=0)
    (book,) = _books([sale], opening=(lot,)).values()
    assert book.episodes[0].incomplete is True


def test_a_preserved_lot_without_a_valid_state_at_the_start_is_incomplete() -> None:
    """Code review: V(start) = 0 for a dead mint would score its sale as pure gain."""
    lot = Lot("A", "MINT", 50 * TOKEN, SOL, -500, T0 - timedelta(hours=1))
    sale = fill(wallet="A", side="sell", slot=10, sol=2 * SOL, atoms=50 * TOKEN, fee_bps=0)
    (book,) = _books([sale], opening=(lot,)).values()
    assert book.episodes[0].incomplete is True


def test_hold_median_is_weighted_by_atoms_not_by_pieces() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=0, sol=SOL, atoms=12 * TOKEN, fee_bps=0, t=0),
        fill(wallet="A", side="sell", slot=25, sol=SOL // 12, atoms=TOKEN, fee_bps=0, t=10),
        fill(wallet="A", side="sell", slot=50, sol=SOL // 12, atoms=TOKEN, fee_bps=0, t=20),
        fill(wallet="A", side="sell", slot=250, sol=SOL, atoms=10 * TOKEN, fee_bps=0, t=100),
    ]
    (book,) = _books(fills).values()
    assert book.episodes[0].hold_seconds == 100.0  # the simple median of pieces would be 20 s


def test_an_episode_crossing_a_gap_is_contaminated() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=TOKEN, fee_bps=0),
        fill(wallet="A", side="sell", slot=200, sol=SOL, atoms=TOKEN, fee_bps=0),
        fill(wallet="A", side="buy", slot=1_000, sol=SOL, atoms=TOKEN, fee_bps=0),
    ]
    tapes = {"MINT": MintTape(fills)}

    def run(gaps: tuple[Gap, ...]) -> list[bool]:
        books = window_books(
            fills, owner_of=lambda w: w, opening=(), tapes=tapes, start=T0, days=7,
            tx_fee_lamports=0, gaps=gaps,
        )  # fmt: skip
        return [e.contaminated for e in books["A"].episodes]

    assert run((Gap(100, 150),)) == [True, False]
    assert run((Gap(5_000, 5_100),)) == [False, True]  # the open one runs to the cut
    assert run(()) == [False, False]
