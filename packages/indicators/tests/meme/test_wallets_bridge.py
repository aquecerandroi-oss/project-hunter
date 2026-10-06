"""The pure bridge ``SwapRecord`` → engine ``Fill`` (H-030, wave 1c fix): every refusal has a
name, a pool record never enters as lamports unless its quote mint was resolved to WSOL,
and the curve's completion flag is never guessed. The record here is a SYNTHETIC plain
struct with the ``SwapRecord`` field names (fixture, not data); the real records are in
``test_wallets_chain.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

import pytest

from hunter_indicators.meme.wallets.bridge import (
    WSOL_MINT,
    BridgeRefusal,
    PoolMints,
    fill_from_swap,
)
from hunter_indicators.meme.wallets.tape import Fill, Reserves, Side, Venue

pytestmark = pytest.mark.unit

T = datetime(2026, 10, 5, 23, 0, tzinfo=UTC)
SOL = 1_000_000_000


@dataclass(frozen=True, slots=True)
class Rec:
    signature: str = "sig"
    slot: int = 100
    program: str = "AMM"
    event_ordinal: int = 0
    block_time: datetime = T
    received_at: datetime = T
    venue: Venue = "pool"
    side: Side = "buy"
    mint: str | None = None
    pool: str | None = "POOL"
    wallet: str = "W"
    sol_lamports: int = SOL
    token_atoms: int = 10_000
    fee_lamports: int = 12_000_000
    fee_bps: int = 120
    lp_fee_lamports: int = 2_000_000
    sol_reserves: int = 101 * SOL
    token_reserves: int = 990_000
    real_sol_reserves: int | None = None
    quote_is_sol: bool | None = None
    virtual_quote_reserves: int | None = 25 * SOL


SOL_POOL = PoolMints(pool="POOL", base_mint="MINT", quote_mint=WSOL_MINT)
CURVE = Rec(
    program="PUMP",
    venue="curve",
    mint="MINT",
    pool=None,
    lp_fee_lamports=0,
    sol_reserves=40 * SOL,
    token_reserves=250_000,
    real_sol_reserves=10 * SOL,
    quote_is_sol=True,
    virtual_quote_reserves=None,
)


def _refusal(result: Fill | BridgeRefusal) -> str:
    assert isinstance(result, BridgeRefusal), result
    assert result.identity[0] == "sig" and result.slot == 100
    return result.reason


def test_a_resolved_wsol_pool_record_becomes_a_fill_with_virtual_quote_and_lp_fee() -> None:
    fill = fill_from_swap(Rec(), pool=SOL_POOL)
    assert isinstance(fill, Fill)
    assert (fill.mint, fill.venue, fill.side, fill.wallet) == ("MINT", "pool", "buy", "W")
    assert (fill.sol_lamports, fill.token_atoms, fill.fee_lamports) == (SOL, 10_000, 12_000_000)
    assert (fill.fee_bps, fill.lp_fee_lamports) == (120, 2_000_000)
    assert fill.identity == ("sig", "AMM", 0) and fill.slot == 100
    assert fill.reserves == Reserves(
        "pool", 101 * SOL, 990_000, None, virtual_quote_lamports=25 * SOL
    )
    assert (fill.block_time, fill.received_at) == (T, T)


def test_a_pool_record_without_its_quote_mint_resolved_is_refused_by_name() -> None:
    assert _refusal(fill_from_swap(Rec())) == "pool_quote_unresolved"


def test_a_pool_quoted_in_something_else_never_enters_as_lamports() -> None:
    usdc = PoolMints(pool="POOL", base_mint="MINT", quote_mint="USDC")
    assert _refusal(fill_from_swap(Rec(), pool=usdc)) == "non_sol_quote"
    flipped = PoolMints(pool="POOL", base_mint=WSOL_MINT, quote_mint="MINT")
    assert _refusal(fill_from_swap(Rec(), pool=flipped)) == "sol_is_base"
    assert _refusal(fill_from_swap(Rec(quote_is_sol=False), pool=SOL_POOL)) == "non_sol_quote"


def test_the_pool_lookup_must_be_for_the_record_pool() -> None:
    with pytest.raises(ValueError, match="pool"):
        fill_from_swap(Rec(), pool=replace(SOL_POOL, pool="OTHER"))


@pytest.mark.parametrize("virtual", [-101 * SOL, -102 * SOL])
def test_a_pool_whose_effective_quote_is_not_positive_is_refused_by_name(virtual: int) -> None:
    rec = Rec(virtual_quote_reserves=virtual)
    assert _refusal(fill_from_swap(rec, pool=SOL_POOL)) == "non_positive_effective_quote"


def test_a_negative_virtual_quote_that_leaves_a_positive_effective_quote_is_kept() -> None:
    # post: 101 − 90 = 11 SOL effective; before the buy: 99.998 − 90 = 9.998 SOL, still positive
    fill = fill_from_swap(Rec(virtual_quote_reserves=-90 * SOL), pool=SOL_POOL)
    assert isinstance(fill, Fill) and fill.reserves.effective_quote_lamports == 11 * SOL


def test_a_pool_record_without_its_virtual_quote_is_refused_not_read_as_zero() -> None:
    rec = Rec(virtual_quote_reserves=None)
    assert _refusal(fill_from_swap(rec, pool=SOL_POOL)) == "virtual_quote_missing"


def test_an_emptied_pool_is_refused_by_name() -> None:
    rec = Rec(side="sell", sol_reserves=0, virtual_quote_reserves=25 * SOL)
    assert _refusal(fill_from_swap(rec, pool=SOL_POOL)) == "invalid_values"


def test_a_curve_record_needs_its_completion_flag_from_the_caller() -> None:
    assert _refusal(fill_from_swap(CURVE)) == "curve_completion_unknown"
    fill = fill_from_swap(CURVE, curve_complete=True)
    assert isinstance(fill, Fill)
    assert fill.reserves == Reserves("curve", 40 * SOL, 250_000, 10 * SOL, complete=True)
    assert (fill.mint, fill.lp_fee_lamports) == ("MINT", 0)


def test_a_curve_record_quoted_in_something_else_is_refused() -> None:
    rec = replace(CURVE, quote_is_sol=None)
    assert _refusal(fill_from_swap(rec, curve_complete=False)) == "non_sol_quote"


def test_a_pool_lookup_is_meaningless_for_a_curve_record() -> None:
    with pytest.raises(ValueError, match="pool"):
        fill_from_swap(CURVE, pool=SOL_POOL, curve_complete=False)


def test_a_pool_record_whose_pre_trade_state_is_impossible_is_refused_by_name() -> None:
    # post: real 1.5 SOL, virtual −1 SOL (effective 0.5 SOL); undoing net 1 SOL + LP 0.002 SOL
    # leaves an effective quote of −0.502 SOL: the trade could not have priced on that
    rec = Rec(sol_reserves=1_500_000_000, virtual_quote_reserves=-SOL)
    assert _refusal(fill_from_swap(rec, pool=SOL_POOL)) == "pre_state_impossible"


def test_a_curve_record_without_its_mint_is_refused_by_its_own_name() -> None:
    rec = replace(CURVE, mint=None)
    assert _refusal(fill_from_swap(rec, curve_complete=False)) == "curve_mint_missing"
