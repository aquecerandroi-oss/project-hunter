"""T4.29b — the price-impact ceiling of a bonding-curve buy, proved against ``quote.py``.

The study ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2.md`` answers
"what does US$ 1 000 per operation buy on pump.fun under our own caps?" with one closed
form, and this file is that form's receipt:

    impact = average fill price / marginal price before the trade − 1
           = a / (vtok − a) = sol_amount / virtual_sol

so the ``impact`` cap of ``hunter_risk_meme.sizing`` admits a **total** spend of
``max_price_impact_pct × virtual_sol × (1 + fee)`` and nothing more. Because a standard
curve's virtual SOL runs from 30 SOL at launch to 115,005359057 SOL at graduation, the
0,5 % cap never admits a 1 SOL buy — on any curve, at any progress. That is a property
of the curve, not an opinion, and the tests below fail the day it stops being true.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from hunter_exchanges.pumpfun.quote import (
    BONDING_CURVE_FEE_TIER_2026_05_20 as FEE,
)
from hunter_exchanges.pumpfun.quote import (
    CurveReserves,
    GlobalParams,
    buy_cost,
    curve_fill_threshold_lamports,
    quote_buy,
    quote_buy_for_budget,
)

LAMPORTS = 1_000_000_000

STANDARD = GlobalParams(
    slot=354_155_511,
    signature="global-params of 2025-07-18, docs/PUMPFUN-ONCHAIN.md §1.2",
    initial_virtual_token_reserves=1_073_000_000_000_000,
    initial_virtual_sol_reserves=30_000_000_000,
    initial_real_token_reserves=793_100_000_000_000,
    token_total_supply=1_000_000_000_000_000,
    fee_basis_points=95,
    timestamp=1_752_856_476_446,
)
"""The record the plantão measured and ``docs/PUMPFUN.md`` §4.2 quotes."""


def curve_at(progress: Decimal) -> CurveReserves:
    """The standard curve after ``progress`` of its real token reserve was bought.

    Uses the constant product the program's own formula preserves (``vsol × vtok`` is
    invariant under ``buy_cost`` up to its "+1 lamport"), so no fill history is replayed.
    """
    sold = int(STANDARD.initial_real_token_reserves * progress)
    vtok = STANDARD.initial_virtual_token_reserves - sold
    vsol = (STANDARD.initial_virtual_sol_reserves * STANDARD.initial_virtual_token_reserves) // vtok
    return CurveReserves(
        virtual_sol=vsol,
        virtual_token=vtok,
        real_sol=vsol - STANDARD.initial_virtual_sol_reserves,
        real_token=STANDARD.initial_real_token_reserves - sold,
    )


def impact_ceiling_sol(reserves: CurveReserves, cap_pct: Decimal) -> Decimal:
    """``cap × virtual_sol × (1 + fee)`` — the ``impact`` cap of ``hunter_risk_meme.sizing``."""
    vsol = Decimal(reserves.virtual_sol) / LAMPORTS
    return cap_pct * vsol * (1 + Decimal(FEE.total) / 10_000)


def test_a_buy_preserves_the_constant_product() -> None:
    """``vsol × vtok`` is invariant — the premise of :func:`curve_at`."""
    reserves = curve_at(Decimal("0.2"))
    before = reserves.virtual_sol * reserves.virtual_token
    quote = quote_buy(reserves, 10_000_000_000_000, FEE, max_slippage_bps=100)
    after = quote.reserves_after.virtual_sol * quote.reserves_after.virtual_token
    # The program's "+1 lamport" makes the product grow by at most one token reserve.
    assert 0 <= after - before <= quote.reserves_after.virtual_token


@pytest.mark.parametrize("progress", ["0", "0.05", "0.25", "0.5", "0.9", "0.95"])
@pytest.mark.parametrize("total_sol", ["0.05", "0.5", "1", "9.8"])
def test_impact_is_the_spend_over_the_virtual_sol_reserve(progress: str, total_sol: str) -> None:
    """``price_impact_bps`` of the quote equals ``sol_amount / virtual_sol``."""
    reserves = curve_at(Decimal(progress))
    budget = int(Decimal(total_sol) * LAMPORTS)
    quote = quote_buy_for_budget(reserves, budget, FEE, max_slippage_bps=100)
    closed_form_bps = quote.sol_amount * 10_000 // reserves.virtual_sol
    assert abs(quote.price_impact_bps - closed_form_bps) <= 1


def test_the_standard_curve_tops_out_at_115_sol_of_virtual_reserve() -> None:
    """The deepest a standard curve ever gets: 115,005359057 SOL of virtual reserve."""
    assert curve_fill_threshold_lamports(STANDARD) == 85_005_359_057
    graduated = curve_at(Decimal(1))
    # The constant product loses the program's "+1 lamport" per fill; one lamport.
    assert abs(graduated.virtual_sol - 115_005_359_057) <= 1
    assert graduated.real_token == 0  # and a graduated curve has nothing left to sell


@pytest.mark.parametrize(
    ("cap_pct", "max_total_sol_at_graduation"),
    [("0.005", "0.582215"), ("0.01", "1.164429"), ("0.05", "5.822146")],
)
def test_the_impact_ceiling_at_graduation(cap_pct: str, max_total_sol_at_graduation: str) -> None:
    ceiling = impact_ceiling_sol(curve_at(Decimal(1)), Decimal(cap_pct))
    assert round(ceiling, 6) == Decimal(max_total_sol_at_graduation)


@pytest.mark.parametrize("progress", ["0", "0.05", "0.5"])
def test_the_impact_ceiling_inside_the_desk_window(progress: str) -> None:
    """Progress 5–50 % (the desk's window after 16/09): the 0,5 % cap never reaches 0,25 SOL."""
    ceiling = impact_ceiling_sol(curve_at(Decimal(progress)), Decimal("0.005"))
    assert ceiling < Decimal("0.25")


@pytest.mark.parametrize("progress", ["0", "0.1", "0.25", "0.5", "0.75", "0.9", "0.99"])
def test_no_curve_state_admits_one_sol_under_a_half_percent_impact(progress: str) -> None:
    """The headline of T4.29b: 1 SOL — let alone 9,8 — never fits the 0,5 % cap."""
    reserves = curve_at(Decimal(progress))
    quote = quote_buy_for_budget(reserves, LAMPORTS, FEE, max_slippage_bps=100)
    assert quote.price_impact_bps > 50  # 50 bps = 0,5 %
    # The floor over every curve state is graduation itself: 0,9877 / 115,0054 = 85,9 bps.
    assert quote.price_impact_bps >= 85


def test_a_curve_at_the_edge_of_graduation_cannot_even_deliver_one_sol() -> None:
    """Past ~99,9 % the reserve, not the cap, is what binds: the tokens run out first."""
    reserves = curve_at(Decimal("0.999"))
    quote = quote_buy_for_budget(reserves, LAMPORTS, FEE, max_slippage_bps=100)
    assert quote.token_amount == reserves.real_token  # the whole remaining reserve
    assert quote.total_cost < LAMPORTS // 3  # and it still does not spend a third of 1 SOL


def test_nine_point_eight_sol_is_eight_percent_at_the_deepest_buyable_state() -> None:
    """US$ 1 000 where the curve is deepest and still buyable: ~800 bps, 16× our cap."""
    quote = quote_buy_for_budget(
        curve_at(Decimal("0.95")), int(Decimal("9.8") * LAMPORTS), FEE, max_slippage_bps=100
    )
    assert 900 <= quote.price_impact_bps <= 1_000
    # And the analytic value at graduation (unbuyable, but the lower bound of the impact):
    vsol = Decimal(curve_at(Decimal(1)).virtual_sol) / LAMPORTS
    analytic = Decimal("9.8") / (1 + Decimal(FEE.total) / 10_000) / vsol
    assert round(analytic * 100, 2) == Decimal("8.42")


def test_buy_cost_is_the_formula_the_study_quotes() -> None:
    reserves = curve_at(Decimal("0.3"))
    tokens = 1_000_000_000_000
    expected = tokens * reserves.virtual_sol // (reserves.virtual_token - tokens) + 1
    assert buy_cost(reserves, tokens) == expected
