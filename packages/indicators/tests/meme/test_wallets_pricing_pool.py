"""§3.1 pool pricing (fix of the wave-1c bug "cota a pool sem a reserva virtual e desfaz o
trade sem a taxa LP", 05/10): a PumpSwap pool is quoted on ``real quote + virtual quote``
(signed), and the state before a trade is rebuilt from the exact vault flow — the LP fee
stays in the pool. Synthetic round numbers (labelled fixtures, not data) so every expected
value is checkable by hand; the real-chain proof is ``test_wallets_chain.py``.
"""

from __future__ import annotations

import pytest

from hunter_indicators.meme.wallets.follow import pair_controls, pre_trade_real_sol
from hunter_indicators.meme.wallets.pricing import (
    CENSORED,
    MintTape,
    buy_atoms,
    pre_trade_state,
    sell_lamports,
)
from hunter_indicators.meme.wallets.tape import Fill, Reserves
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, curve, fill, pool

pytestmark = pytest.mark.unit

LP = 2_500_000  # synthetic LP fee, lamports


@pytest.mark.parametrize(
    ("virtual", "expected"),
    [
        (100 * SOL, 1_980_198_019),  # 200 × 10 / 1010 SOL, floored
        (0, 990_099_009),  # 100 × 10 / 1010 SOL
        (-50 * SOL, 495_049_504),  # 50 × 10 / 1010 SOL
    ],
)
def test_a_pool_sale_is_quoted_on_real_plus_virtual_quote(virtual: int, expected: int) -> None:
    state = pool(100 * SOL, 1_000 * TOKEN, virtual=virtual)
    assert sell_lamports(state, 10 * TOKEN, fee_bps=0) == expected


def test_the_fee_of_a_boosted_pool_sale_is_ceiled_on_the_gross() -> None:
    state = pool(100 * SOL, 1_000 * TOKEN, virtual=100 * SOL)
    # gross 1 980 198 019; fee ceil(1 980 198 019 × 125 / 10 000) = 24 752 476
    assert sell_lamports(state, 10 * TOKEN, fee_bps=125) == 1_955_445_543


def test_a_pool_buy_is_quoted_on_real_plus_virtual_quote() -> None:
    state = pool(100 * SOL, 1_000 * TOKEN, virtual=100 * SOL)
    # 1.0125 SOL at 1.25 %: 1 SOL reaches the pool; 1000 × 1 / (200 + 1) tokens, floored
    assert buy_atoms(state, 1_012_500_000, fee_bps=125) == 4_975_124


def test_a_sale_never_takes_more_than_the_real_quote_in_the_vault() -> None:
    # 101 × 1000 / 2000 = 50.5 SOL by the constant product, but the vault holds 1 SOL
    state = pool(1 * SOL, 1_000 * TOKEN, virtual=100 * SOL)
    assert sell_lamports(state, 1_000 * TOKEN, fee_bps=0) == 1 * SOL
    # the fee is taken AFTER the cap: 1 SOL − ceil(1 SOL × 1.25 %), not min(net, 1 SOL)
    assert sell_lamports(state, 1_000 * TOKEN, fee_bps=125) == 987_500_000


@pytest.mark.parametrize("virtual", [-50 * SOL, -51 * SOL])
def test_a_pool_whose_effective_quote_is_not_positive_is_not_a_state(virtual: int) -> None:
    with pytest.raises(ValueError, match="effective quote"):
        pool(50 * SOL, 1_000 * TOKEN, virtual=virtual)


def test_a_curve_state_has_no_separate_virtual_quote() -> None:
    with pytest.raises(ValueError, match="virtual quote"):
        Reserves("curve", 40 * SOL, 250 * TOKEN, 10 * SOL, virtual_quote_lamports=1)


def test_a_pool_buy_is_undone_with_the_lp_fee_and_the_virtual_quote_is_kept() -> None:
    # the vault received net + LP; the trade took 10 tokens
    post = pool(100 * SOL + SOL + LP, 990 * TOKEN, virtual=100 * SOL)
    buy = fill(
        wallet="X", side="buy", slot=7, sol=SOL, atoms=10 * TOKEN, fee=LP, lp_fee=LP, reserves=post
    )
    assert pre_trade_state(buy) == pool(100 * SOL, 1_000 * TOKEN, virtual=100 * SOL)


def test_a_pool_sale_is_undone_with_the_lp_fee_left_in_the_pool() -> None:
    # the vault paid gross − LP; the trade brought 10 tokens
    post = pool(100 * SOL - (SOL - LP), 1_010 * TOKEN, virtual=-20 * SOL)
    sale = fill(
        wallet="X", side="sell", slot=7, sol=SOL, atoms=10 * TOKEN, fee=LP, lp_fee=LP, reserves=post
    )
    assert pre_trade_state(sale) == pool(100 * SOL, 1_000 * TOKEN, virtual=-20 * SOL)


def test_a_curve_trade_is_undone_as_before() -> None:
    post = curve(41 * SOL, 240 * TOKEN, real_sol=11 * SOL)
    buy = fill(wallet="X", side="buy", slot=7, sol=SOL, atoms=10 * TOKEN, reserves=post)
    assert pre_trade_state(buy) == curve(40 * SOL, 250 * TOKEN, real_sol=10 * SOL)


def test_a_pre_state_whose_effective_quote_is_not_positive_is_impossible() -> None:
    # post: real 1.5 SOL, virtual −1 SOL (effective 0.5); undoing a 1 SOL buy leaves −0.5
    post = pool(1_500_000_000, 990 * TOKEN, virtual=-SOL)
    buy = fill(wallet="X", side="buy", slot=7, sol=SOL, atoms=10 * TOKEN, reserves=post)
    assert pre_trade_state(buy) is None


def test_a_landing_slot_with_an_impossible_pre_state_is_censored_not_priced() -> None:
    # review round 2 (Astra HIGH): dropping the impossible pre-state priced the slot on its
    # post-state alone (5 000 000 lamports for 10 tokens) — the worst state is unknowable
    post = pool(1_500_000_000, 990 * TOKEN, virtual=-SOL)
    buy = fill(wallet="X", side="buy", slot=7, sol=SOL, atoms=10 * TOKEN, reserves=post)
    tape = MintTape([buy])
    assert tape.landing_sell(7, 10 * TOKEN) is CENSORED
    assert tape.landing_buy(7, SOL) is CENSORED
    # a later slot without trades meets the event's post-state, as the contract says
    assert tape.landing_sell(8, 10 * TOKEN) == sell_lamports(post, 10 * TOKEN, fee_bps=125)


def test_the_landing_slot_meets_the_exact_pre_trade_pool_state() -> None:
    post = pool(100 * SOL + SOL + LP, 990 * TOKEN, virtual=100 * SOL)
    buy = fill(
        wallet="X",
        side="buy",
        slot=7,
        sol=SOL,
        atoms=10 * TOKEN,
        fee=LP,
        lp_fee=LP,
        fee_bps=0,
        reserves=post,
    )
    # before the buy: 200 SOL effective, 1000 tokens → 1 980 198 019 for 10 tokens (worse than after)
    assert MintTape([buy]).landing_sell(7, 10 * TOKEN) == 1_980_198_019


def test_the_lp_fee_is_part_of_the_declared_fees_and_absent_on_the_curve() -> None:
    with pytest.raises(ValueError, match="lp fee"):
        fill(
            wallet="X",
            side="buy",
            slot=1,
            sol=SOL,
            atoms=TOKEN,
            fee=10,
            lp_fee=11,
            reserves=pool(SOL, TOKEN),
        )
    with pytest.raises(ValueError, match="lp fee"):
        fill(wallet="X", side="buy", slot=1, sol=SOL, atoms=TOKEN, fee=10, lp_fee=5)


def test_the_real_quote_before_a_pool_trade_counts_the_lp_fee() -> None:
    post = pool(50 * SOL, 900 * TOKEN)
    buy = fill(
        wallet="X", side="buy", slot=1, sol=SOL, atoms=TOKEN, fee=LP, lp_fee=LP, reserves=post
    )
    sale = fill(
        wallet="X", side="sell", slot=1, sol=SOL, atoms=TOKEN, fee=LP, lp_fee=LP, reserves=post
    )
    assert pre_trade_real_sol(buy) == 49 * SOL - LP
    assert pre_trade_real_sol(sale) == 51 * SOL - LP


def test_a_pool_landing_without_trades_never_reads_the_next_trade() -> None:
    first = pool(100 * SOL, 1_000 * TOKEN, virtual=50 * SOL)
    before = fill(wallet="X", side="buy", slot=10, sol=SOL, atoms=TOKEN, fee_bps=0, reserves=first)
    expected = sell_lamports(first, 10 * TOKEN, fee_bps=0)
    for nxt in (pool(300 * SOL, 500 * TOKEN, virtual=-50 * SOL), pool(SOL, 9_000 * TOKEN)):
        after = fill(
            wallet="Y", side="sell", slot=20, sol=SOL, atoms=TOKEN, fee_bps=0, reserves=nxt
        )
        assert MintTape([before, after]).landing_sell(15, 10 * TOKEN) == expected


def _exact_buy_cost(state: Reserves, atoms: int, fee_bps: int) -> int:
    """What the program charges for ``atoms`` out: net quote ceiled, fee ceiled on the net."""
    q = state.effective_quote_lamports
    net = -(-(q * atoms) // (state.token_atoms - atoms))
    return net + -(-net * fee_bps // 10_000)


@pytest.mark.parametrize(
    ("state", "budget"),
    [
        (pool(SOL, 1_000_000 * TOKEN), 50_000_000),  # the reviewer's case: 50 000 001 before
        (pool(100 * SOL, 1_000 * TOKEN, virtual=100 * SOL), 1_012_500_000),
        (pool(3 * SOL, 7_777 * TOKEN, virtual=-SOL), 123_456_789),
    ],
)
def test_a_pool_buy_never_costs_more_than_its_budget(state: Reserves, budget: int) -> None:
    atoms = buy_atoms(state, budget, fee_bps=125)
    assert atoms is not None and atoms > 0
    assert _exact_buy_cost(state, atoms, 125) <= budget


def test_an_unknown_pre_trade_liquidity_is_unknown_and_never_paired() -> None:
    # review round 2 (Astra HIGH): 0 put an impossible pre-state in the lowest tercile
    impossible = pool(1_500_000_000, 990 * TOKEN, virtual=-SOL)
    thin = pool(2 * SOL, 990 * TOKEN)  # 1 SOL real before the buy: a genuine lowest tercile

    def buy(wallet: str, mint: str, post: Reserves) -> Fill:
        return fill(
            wallet=wallet, side="buy", slot=50, sol=SOL, atoms=TOKEN, mint=mint, reserves=post
        )

    follow_bad, follow_ok = buy("F", "A", impossible), buy("F", "A", thin)
    control_bad, control_ok = buy("C", "B", impossible), buy("C", "B", thin)
    assert pre_trade_real_sol(follow_bad) is None
    assert pre_trade_real_sol(follow_ok) == SOL
    edges = (10 * SOL, 40 * SOL)

    def pairs(follows: list[Fill], controls: list[Fill]) -> dict[str, str | None]:
        return pair_controls(follows, controls, creates={}, tercile_edges=edges, seed=1)

    assert pairs([follow_bad], [control_ok]) == {follow_bad.signature: None}
    assert pairs([follow_bad], [control_bad]) == {follow_bad.signature: None}  # two unknowns
    assert pairs([follow_ok], [control_bad]) == {follow_ok.signature: None}
    assert pairs([follow_ok], [control_ok]) == {follow_ok.signature: control_ok.signature}
