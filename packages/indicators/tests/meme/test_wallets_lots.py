"""FIFO lots, realized PnL net of fees, event identity and the causal view.

Expected values are written by hand from the synthetic fills (no measurement).
"""

from __future__ import annotations

import pytest

from hunter_indicators.meme.wallets.lots import Lot, fifo
from hunter_indicators.meme.wallets.tape import causal_view, dedupe
from packages.indicators.tests.meme.test_wallets_builders import SOL, T0, TOKEN, at, fill

pytestmark = pytest.mark.unit

TX = 5_000


def test_fifo_matches_oldest_lot_first_and_charges_fees_and_one_tx_fee_per_signature() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=10, sol=1 * SOL, atoms=100 * TOKEN, fee=12_500_000),
        fill(wallet="A", side="buy", slot=20, sol=2 * SOL, atoms=100 * TOKEN, fee=25_000_000),
        fill(wallet="A", side="sell", slot=30, sol=3 * SOL, atoms=150 * TOKEN, fee=37_500_000),
    ]
    result = fifo(fills, owner_of=lambda w: w)
    # lot 1 cost = 1 SOL + 0.0125 fee + 5 000; lot 2 = 2 SOL + 0.025 + 5 000
    # sell net = 3 SOL − 0.0375 − 5 000, split 100/150 and 50/150 (remainder to the last piece)
    first, second = result.matches
    assert (first.atoms, first.cost_lamports) == (100 * TOKEN, 1_012_505_000)
    assert first.proceeds_lamports == (2_962_495_000 * 100) // 150
    assert second.atoms == 50 * TOKEN
    assert second.cost_lamports == 2_025_005_000 // 2
    assert first.proceeds_lamports + second.proceeds_lamports == 2_962_495_000
    assert result.open_lots[0].atoms == 50 * TOKEN
    assert result.open_lots[0].cost_lamports == 2_025_005_000 - 2_025_005_000 // 2
    assert result.realized_lamports == 2_962_495_000 - 1_012_505_000 - 2_025_005_000 // 2
    assert result.unmatched == ()


def test_sell_beyond_inventory_is_unmatched_not_a_free_lot() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=1, sol=1 * SOL, atoms=60 * TOKEN),
        fill(wallet="A", side="sell", slot=2, sol=2 * SOL, atoms=100 * TOKEN),
    ]
    result = fifo(fills, owner_of=lambda w: w, tx_fee_lamports=0)
    assert result.matches[0].atoms == 60 * TOKEN
    assert result.matches[0].proceeds_lamports == 2 * SOL * 60 // 100
    (orphan,) = result.unmatched
    assert orphan.atoms == 40 * TOKEN
    assert orphan.proceeds_lamports == 2 * SOL - 2 * SOL * 60 // 100
    assert result.unmatched_atoms == 40 * TOKEN
    assert result.sold_atoms == 100 * TOKEN


def test_preserved_opening_lot_with_unknown_cost_makes_the_match_incomplete() -> None:
    opening = [
        Lot(
            owner="A",
            mint="MINT",
            atoms=10 * TOKEN,
            cost_lamports=None,
            opened_slot=0,
            opened_at=T0,
        )
    ]
    fills = [fill(wallet="A", side="sell", slot=5, sol=SOL, atoms=10 * TOKEN)]
    result = fifo(fills, owner_of=lambda w: w, opening=opening, tx_fee_lamports=0)
    assert result.matches[0].cost_lamports is None
    assert result.realized_lamports == 0
    assert result.incomplete_matches == 1


def test_twin_wallets_match_inside_the_entity() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=1, sol=SOL, atoms=10 * TOKEN),
        fill(wallet="B", side="sell", slot=2, sol=2 * SOL, atoms=10 * TOKEN),
    ]
    by_wallet = fifo(fills, owner_of=lambda w: w, tx_fee_lamports=0)
    by_entity = fifo(fills, owner_of=lambda _w: "E", tx_fee_lamports=0)
    assert by_wallet.unmatched_atoms == 10 * TOKEN
    assert by_entity.realized_lamports == SOL


def test_two_events_of_one_signature_pay_one_tx_fee() -> None:
    fills = [
        fill(wallet="A", side="buy", slot=1, sol=SOL, atoms=10 * TOKEN, signature="s", ordinal=0),
        fill(wallet="A", side="buy", slot=1, sol=SOL, atoms=10 * TOKEN, signature="s", ordinal=1),
    ]
    result = fifo(fills, owner_of=lambda w: w)
    assert sum(lot.cost_lamports or 0 for lot in result.open_lots) == 2 * SOL + TX


def test_dedupe_keeps_one_event_per_identity_the_earliest_received() -> None:
    early = fill(
        wallet="A", side="buy", slot=1, sol=SOL, atoms=TOKEN, signature="s", received_delay=0.3
    )
    late = fill(
        wallet="A", side="buy", slot=1, sol=SOL, atoms=TOKEN, signature="s", received_delay=0.9
    )
    other = fill(wallet="A", side="buy", slot=1, sol=SOL, atoms=TOKEN, signature="s", ordinal=1)
    assert dedupe([late, early, other]) == (early, other)


def test_causal_view_drops_anything_mined_or_received_at_or_after_the_cut() -> None:
    cut = at(100)
    ok = fill(wallet="A", side="buy", slot=10, sol=SOL, atoms=TOKEN, t=50)
    mined_late = fill(wallet="A", side="buy", slot=300, sol=SOL, atoms=TOKEN, t=100)
    received_late = fill(
        wallet="A", side="buy", slot=200, sol=SOL, atoms=TOKEN, t=99, received_delay=1.0
    )
    assert causal_view([mined_late, received_late, ok], cut) == (ok,)


def test_causal_view_checks_the_mining_time_even_when_received_earlier() -> None:
    cut = at(100)
    odd = fill(wallet="A", side="buy", slot=250, sol=SOL, atoms=TOKEN, t=100, received_delay=-1.0)
    assert odd.received_at < cut <= odd.block_time
    assert causal_view([odd], cut) == ()
