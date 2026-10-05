"""§3.1 price contract: last state ≤ slot (never the next trade), worst of the
landing slot, real-SOL ceiling always on, migration without a readable pool is
censored. Small curves are used so every expected value is checkable by hand.
"""

from __future__ import annotations

import pytest

from hunter_indicators.meme.wallets.pricing import (
    CENSORED,
    MintTape,
    buy_atoms,
    liquidation_lamports,
    sell_lamports,
)
from packages.indicators.tests.meme.test_wallets_builders import SOL, TOKEN, at, curve, fill, pool

pytestmark = pytest.mark.unit

SMALL = curve(45 * SOL, 200 * TOKEN, real_sol=15 * SOL)


def test_curve_sell_quote_is_the_constant_product_minus_fee() -> None:
    # 45 × 100 / (200 + 100) = 15 SOL gross; 1 % fee → 14.85 SOL
    assert sell_lamports(SMALL, 100 * TOKEN, fee_bps=0) == 15 * SOL
    assert sell_lamports(SMALL, 100 * TOKEN, fee_bps=100) == 14_850_000_000


def test_curve_sale_never_takes_more_than_the_real_sol_in_the_vault() -> None:
    thin = curve(45 * SOL, 200 * TOKEN, real_sol=10 * SOL)
    assert sell_lamports(thin, 100 * TOKEN, fee_bps=0) == 10 * SOL


def test_curve_buy_quote_puts_the_fee_on_top_and_floors_the_atoms() -> None:
    # 1.01 SOL at 1 %: 1 SOL reaches the curve; 200 × 1 / (45 + 1) tokens
    atoms = buy_atoms(SMALL, 1_010_000_000, fee_bps=100)
    assert atoms == 200 * TOKEN * 1 // 46


def test_pool_quotes_have_their_own_constant_product() -> None:
    state = pool(100 * SOL, 1_000 * TOKEN)
    # sell 10 tokens: 100 × 10 / 1010 SOL gross, minus 1.25 %
    # gross floored to 990 099 009 lamports, fee ceiled to 12 376 238 (Astra must-fix 4)
    assert sell_lamports(state, 10 * TOKEN, fee_bps=125) == 977_722_771
    # buy with 1.0125 SOL at 1.25 %: 1 SOL in; 1000 × 1 / 101 tokens
    assert buy_atoms(state, 1_012_500_000, fee_bps=125) == 1_000 * TOKEN // 101


def test_a_completed_curve_is_not_executable() -> None:
    done = curve(115 * SOL, 280 * TOKEN, real_sol=85 * SOL, complete=True)
    assert sell_lamports(done, TOKEN, fee_bps=0) is None
    assert buy_atoms(done, SOL, fee_bps=0) is None


def _tape() -> MintTape:
    return MintTape(
        [
            fill(
                wallet="X",
                side="buy",
                slot=10,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(40 * SOL, 250 * TOKEN),
            ),
            fill(
                wallet="Y",
                side="buy",
                slot=20,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(60 * SOL, 150 * TOKEN),
            ),
        ]
    )


def test_slot_without_trades_uses_the_last_state_never_the_next_trade() -> None:
    tape = _tape()
    q = tape.landing_sell(15, 10 * TOKEN)
    assert q == sell_lamports(curve(40 * SOL, 250 * TOKEN), 10 * TOKEN, fee_bps=125)
    moved = MintTape(
        [
            *tape.fills[:1],
            fill(
                wallet="Y",
                side="buy",
                slot=20,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(90 * SOL, 100 * TOKEN),
            ),
        ]
    )
    assert moved.landing_sell(15, 10 * TOKEN) == q


def test_landing_slot_with_trades_takes_the_worst_of_before_and_every_state_in_the_slot() -> None:
    tape = MintTape(
        [
            fill(
                wallet="X",
                side="buy",
                slot=10,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(40 * SOL, 250 * TOKEN),
            ),
            fill(
                wallet="Y",
                side="buy",
                slot=15,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(50 * SOL, 200 * TOKEN),
                ordinal=0,
            ),
            fill(
                wallet="Z",
                side="sell",
                slot=15,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(35 * SOL, 280 * TOKEN),
                ordinal=1,
            ),
        ]
    )
    worst_sell = min(
        sell_lamports(curve(s * SOL, t * TOKEN), 10 * TOKEN, fee_bps=125) or 0
        for s, t in [(40, 250), (50, 200), (35, 280)]
    )
    assert tape.landing_sell(15, 10 * TOKEN) == worst_sell
    worst_buy = min(
        buy_atoms(curve(s * SOL, t * TOKEN), SOL, fee_bps=125) or 0
        for s, t in [(40, 250), (50, 200), (35, 280)]
    )
    assert tape.landing_buy(15, SOL) == worst_buy


def test_migration_without_a_decodable_pool_event_is_censored() -> None:
    tape = MintTape(
        [
            fill(
                wallet="X",
                side="buy",
                slot=10,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(40 * SOL, 250 * TOKEN),
            ),
            fill(
                wallet="Y",
                side="buy",
                slot=12,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(115 * SOL, 280 * TOKEN, real_sol=85 * SOL, complete=True),
            ),
        ]
    )
    assert tape.landing_sell(20, TOKEN) is CENSORED


def test_after_migration_the_position_is_priced_in_the_decoded_pool() -> None:
    p = pool(80 * SOL, 200 * TOKEN)
    tape = MintTape(
        [
            fill(
                wallet="Y",
                side="buy",
                slot=12,
                sol=SOL,
                atoms=TOKEN,
                reserves=curve(115 * SOL, 280 * TOKEN, real_sol=85 * SOL, complete=True),
            ),
            fill(wallet="Z", side="buy", slot=18, sol=SOL, atoms=TOKEN, reserves=p, fee_bps=120),
        ]
    )
    # in the pool's own trade slot, the state before that buy (79 SOL, 201 tokens) is worse
    before_buy = sell_lamports(pool(79 * SOL, 201 * TOKEN), TOKEN, fee_bps=120)
    assert before_buy is not None
    assert tape.landing_sell(18, TOKEN) == before_buy < (sell_lamports(p, TOKEN, fee_bps=120) or 0)
    assert tape.landing_sell(25, TOKEN) == sell_lamports(p, TOKEN, fee_bps=120)


def test_liquidation_at_a_boundary_uses_only_events_before_it_and_zero_without_state() -> None:
    tape = _tape()
    assert liquidation_lamports(tape, at(1), 10 * TOKEN) == 0  # nothing before slot 10 (t=4 s)
    v = liquidation_lamports(tape, at(5), 10 * TOKEN)
    assert v == sell_lamports(curve(40 * SOL, 250 * TOKEN), 10 * TOKEN, fee_bps=125)
    assert liquidation_lamports(tape, at(5), 0) == 0


def test_the_state_before_the_first_trade_of_the_landing_slot_is_a_candidate() -> None:
    # Astra must-fix 3: the only event moves (100 SOL, 1000 tokens) to (200, 500); selling 10
    # tokens before it yields 100 × 10 / 1010 SOL, far below the post-trade quote
    only = fill(
        wallet="X",
        side="buy",
        slot=50,
        sol=100 * SOL,
        atoms=500 * TOKEN,
        fee_bps=0,
        reserves=curve(200 * SOL, 500 * TOKEN, real_sol=170 * SOL),
    )
    assert MintTape([only]).landing_sell(50, 10 * TOKEN) == 990_099_009
