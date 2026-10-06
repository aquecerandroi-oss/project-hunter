"""Real chain → ``SwapRecord`` → ``Fill`` → pre-trade state / quote (H-030, fix of wave 1c).

Against the REAL wave-1a fixtures (``t1a_tape.py``): the engine rebuilds the pool exactly as
the event reported it before the trade (virtual quote kept, LP fee left in the pool), prices
the 38 387 041-lamport buy right (the real quote alone gave 32 468 689, −15 %), reproduces the
sells' gross to the lamport, chains the pinned consecutive pairs and refuses by name the pools
whose quote is not WSOL.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from hunter_exchanges.pumpfun.swap_record import SwapRecord
from hunter_indicators.meme.wallets.bridge import (
    WSOL_MINT,
    BridgeRefusal,
    PoolMints,
    fill_from_swap,
)
from hunter_indicators.meme.wallets.pricing import buy_atoms, pre_trade_state, sell_lamports
from hunter_indicators.meme.wallets.tape import Fill, Reserves
from packages.indicators.tests.meme.t1a_tape import (
    AMM_BUY,
    AMM_BUY_NEXT,
    AMM_SELL_CASHBACK_X2,
    SOL_IS_BASE,
    V1_AMM_SELL,
    V1_PUMP_BUY,
    WSOL_QUOTED,
    chain_pool_mints,
    pool_events,
    records,
    tx,
)

pytestmark = pytest.mark.unit


def _fill(record: SwapRecord, mints: PoolMints) -> Fill:
    fill = fill_from_swap(record, pool=mints)
    assert isinstance(fill, Fill), fill
    return fill


def _fills(name: str) -> list[Fill]:
    t = tx(name)
    return [_fill(r, chain_pool_mints(t, r.pool or "")) for r in records(t)]


def _pre(fill: Fill) -> Reserves:
    state = pre_trade_state(fill)
    assert state is not None
    return state


def _cost_exact_out(state: Reserves, atoms: int) -> int:
    """The program's net quote for ``atoms`` out (ceil), KB-0184 item 3."""
    q = state.effective_quote_lamports
    return -(-(q * atoms) // (state.token_atoms - atoms))


@pytest.mark.parametrize("name", WSOL_QUOTED)
def test_the_pre_trade_pool_is_exactly_what_the_event_reported(name: str) -> None:
    t = tx(name)
    events = pool_events(t)
    fills = [_fill(r, chain_pool_mints(t, r.pool or "")) for r in records(t)]
    assert len(fills) == len(events) >= 1
    for fill, event in zip(fills, events, strict=True):
        assert fill.mint == chain_pool_mints(t, event.pool).base_mint != WSOL_MINT
        assert event.virtual_quote_reserves is not None  # every post-redeploy event carries it
        assert _pre(fill) == Reserves(
            "pool",
            event.pool_quote_token_reserves,
            event.pool_base_token_reserves,
            None,
            virtual_quote_lamports=event.virtual_quote_reserves,
        )


def test_the_38_387_041_lamport_buy_is_priced_on_real_plus_virtual_quote() -> None:
    (fill,) = _fills(AMM_BUY)
    pre = _pre(fill)
    assert (fill.sol_lamports, fill.token_atoms) == (38_387_041, 52_542_044_672)
    assert pre.virtual_quote_lamports == 25_730_818_627
    assert _cost_exact_out(pre, fill.token_atoms) == 38_387_041
    real_only = replace(pre, virtual_quote_lamports=0)
    # the bug: −15 % (KB-0184 cites 32 468 689, the floored figure; the ceil is one more)
    assert _cost_exact_out(real_only, fill.token_atoms) == 32_468_690
    # our copy spending what the leader paid in total gets the leader's atoms, give or take
    # the rounding of one ceiled fee rate against three ceiled fees (≤ 2 lamports of quote)
    atoms = buy_atoms(pre, fill.sol_lamports + fill.fee_lamports, fee_bps=fill.fee_bps)
    assert atoms is not None and atoms >= fill.token_atoms
    assert _cost_exact_out(pre, atoms) - fill.sol_lamports <= 2
    stale = buy_atoms(real_only, fill.sol_lamports + fill.fee_lamports, fee_bps=fill.fee_bps)
    assert stale is not None and 100 * stale > 115 * fill.token_atoms


@pytest.mark.parametrize("name", [AMM_SELL_CASHBACK_X2, V1_AMM_SELL])
def test_a_real_sale_is_reproduced_to_the_lamport_from_the_pre_trade_pool(name: str) -> None:
    for fill in _fills(name):
        assert fill.side == "sell"
        pre = _pre(fill)
        assert sell_lamports(pre, fill.token_atoms, fee_bps=0) == fill.sol_lamports
        net = sell_lamports(pre, fill.token_atoms, fee_bps=fill.fee_bps)
        chain_net = fill.sol_lamports - fill.fee_lamports
        # one ceiled total rate vs four ceiled fees (LP, protocol, creator, cashback): ≤ 3 lamports
        assert net is not None and 0 <= net - chain_net <= 3


@pytest.mark.parametrize(
    ("first", "following"),
    [((AMM_BUY, 0), (AMM_BUY_NEXT, 0)), ((AMM_SELL_CASHBACK_X2, 0), (AMM_SELL_CASHBACK_X2, 1))],
)
def test_the_pinned_consecutive_pairs_chain_through_the_engine(
    first: tuple[str, int], following: tuple[str, int]
) -> None:
    """Independent witness: the NEXT trade's own pre-trade report, rebuilt by the engine."""
    a = _fills(first[0])[first[1]]
    b = _fills(following[0])[following[1]]
    assert a.mint == b.mint and a.slot == b.slot
    assert a.reserves == _pre(b)


@pytest.mark.parametrize("name", SOL_IS_BASE)
def test_a_pool_whose_quote_is_not_wsol_never_enters_as_lamports(name: str) -> None:
    t = tx(name)
    (record,) = records(t)
    assert record.quote_is_sol is None
    unresolved = fill_from_swap(record)
    assert isinstance(unresolved, BridgeRefusal) and unresolved.reason == "pool_quote_unresolved"
    mints = chain_pool_mints(t, record.pool or "")
    assert mints.base_mint == WSOL_MINT != mints.quote_mint
    refused = fill_from_swap(record, pool=mints)
    assert isinstance(refused, BridgeRefusal) and refused.reason == "sol_is_base"
    assert refused.identity == record.identity and refused.slot == record.slot


def test_a_real_curve_record_bridges_with_the_completion_flag_the_caller_gives() -> None:
    (record,) = records(tx(V1_PUMP_BUY, "pumpfun"))
    missing = fill_from_swap(record)
    assert isinstance(missing, BridgeRefusal) and missing.reason == "curve_completion_unknown"
    fill = fill_from_swap(record, curve_complete=False)
    assert isinstance(fill, Fill)
    assert fill.reserves == Reserves(
        "curve", record.sol_reserves, record.token_reserves, record.real_sol_reserves
    )
    assert (fill.mint, fill.sol_lamports, fill.lp_fee_lamports) == (
        record.mint,
        record.sol_lamports,
        0,
    )
