"""T4.5 — the bonding-curve math, with the numbers written before the code.

The exact-arithmetic fixture is a deliberately tiny curve (``30 SOL`` against
``300`` tokens, ``k = 9000``) because every expected value below is then a
terminating decimal a human can check by hand:

- buying 100 tokens costs ``9000/200 - 30 = 15`` SOL and leaves ``(45, 200)``;
- selling those 100 back yields ``45 - 9000/300 = 15`` SOL — the pre-fee round
  trip is exactly zero, which is what makes "the round trip loses exactly the
  fees plus the impact" a *measurable* claim instead of a slogan.

The live constants (30 SOL / 1 073 000 000 virtual tokens) and the real capture
fixtures of T4.1 are the smoke inputs at the bottom, including a parity check
against ``hunter_exchanges.pumpfun.curve``: the adapter owns the wire format,
this package owns the trade arithmetic, and the two must agree on the functions
they share.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from hunter_indicators.meme.curve import (
    CURVE_TRADE_FEE_PCT,
    INITIAL_VIRTUAL_SOL_RESERVES,
    INITIAL_VIRTUAL_TOKEN_RESERVES,
    CurveReserves,
    buy_cost,
    constant_product,
    curve_input_from_budget,
    curve_progress_pct,
    fee_amount,
    marginal_price_sol,
    market_cap_sol,
    quote_buy,
    quote_sell,
    reserves_after_buy,
    reserves_after_sell,
    sell_proceeds,
    tokens_for_sol,
)

TINY = CurveReserves(
    virtual_sol_reserves=Decimal(30),
    virtual_token_reserves=Decimal(300),
    real_token_reserves=Decimal(200),
    initial_real_token_reserves=Decimal(240),
)
FEE = Decimal("1.25")
FIXTURES = (
    Path(__file__).resolve().parents[3] / "exchange-adapters" / "tests" / "fixtures" / "pumpfun"
)
TOTAL_SUPPLY = Decimal(1_000_000_000)
"""Tokens minted per pump.fun launch, observed live in T4.0/T4.1 (1e15 subunits,
``base_decimals = 6``). A parameter of :func:`market_cap_sol`, never a default."""


def test_constant_product_and_marginal_price_are_the_two_reserves() -> None:
    assert constant_product(TINY) == Decimal(9000)
    assert marginal_price_sol(TINY) == Decimal("0.1")
    assert market_cap_sol(TINY, Decimal(1000)) == Decimal(100)


def test_buy_cost_and_tokens_for_sol_are_inverses_on_the_hand_checked_fixture() -> None:
    assert buy_cost(TINY, Decimal(100)) == Decimal(15)
    assert tokens_for_sol(TINY, Decimal(15)) == Decimal(100)


def test_buy_cost_is_the_reviewed_formula_written_to_avoid_cancelling_digits() -> None:
    """Astra's review states the cost as ``k/(T-q) - S``; we compute ``S*q/(T-q)``.

    Algebraically identical, numerically safer (no subtraction of two nearly
    equal 28-digit numbers when the trade is small against the reserves). The
    identity is asserted, not assumed.
    """
    k = constant_product(TINY)
    reviewed_buy = k / (TINY.virtual_token_reserves - Decimal(100)) - TINY.virtual_sol_reserves
    assert buy_cost(TINY, Decimal(100)) == reviewed_buy
    reviewed_sell = TINY.virtual_sol_reserves - k / (TINY.virtual_token_reserves + Decimal(100))
    assert sell_proceeds(TINY, Decimal(100)) == reviewed_sell == Decimal("7.5")


def test_reserves_after_our_own_buy_move_the_curve_and_keep_k() -> None:
    after = reserves_after_buy(TINY, Decimal(100))
    assert after.virtual_sol_reserves == Decimal(45)
    assert after.virtual_token_reserves == Decimal(200)
    assert after.real_token_reserves == Decimal(100)
    assert constant_product(after) == Decimal(9000)
    assert marginal_price_sol(after) == Decimal("0.225")


def test_selling_back_at_the_moved_reserves_returns_the_pre_fee_cost() -> None:
    after = reserves_after_buy(TINY, Decimal(100))
    assert sell_proceeds(after, Decimal(100)) == Decimal(15)
    back = reserves_after_sell(after, Decimal(100))
    assert back.virtual_sol_reserves == TINY.virtual_sol_reserves
    assert back.virtual_token_reserves == TINY.virtual_token_reserves
    assert back.real_token_reserves == TINY.real_token_reserves


def test_curve_progress_is_the_real_token_reserve_burned_down() -> None:
    assert curve_progress_pct(TINY) == Decimal("16.66666666666666666666666667")
    at_half = CurveReserves(
        virtual_sol_reserves=Decimal(30),
        virtual_token_reserves=Decimal(300),
        real_token_reserves=Decimal(120),
        initial_real_token_reserves=Decimal(240),
    )
    assert curve_progress_pct(at_half) == Decimal(50)


def test_progress_is_none_when_the_denominator_was_never_observed() -> None:
    unknown = CurveReserves(Decimal(30), Decimal(300), real_token_reserves=Decimal(200))
    assert curve_progress_pct(unknown) is None
    assert curve_progress_pct(CurveReserves(Decimal(30), Decimal(300))) is None


@pytest.mark.parametrize(
    ("sol", "tokens", "real", "initial"),
    [
        (Decimal(0), Decimal(300), None, None),
        (Decimal(-1), Decimal(300), None, None),
        (Decimal(30), Decimal(0), None, None),
        (Decimal(30), Decimal(300), Decimal(-1), None),
        (Decimal(30), Decimal(300), Decimal(1), Decimal(0)),
    ],
)
def test_reserves_refuse_to_exist_with_impossible_numbers(
    sol: Decimal, tokens: Decimal, real: Decimal | None, initial: Decimal | None
) -> None:
    with pytest.raises(ValueError):
        CurveReserves(sol, tokens, real_token_reserves=real, initial_real_token_reserves=initial)


def test_no_trade_can_drain_the_token_side_or_the_real_reserve() -> None:
    with pytest.raises(ValueError):
        buy_cost(TINY, Decimal(300))
    with pytest.raises(ValueError):
        buy_cost(TINY, Decimal(301))
    with pytest.raises(ValueError):
        reserves_after_buy(TINY, Decimal(201))  # only 200 real tokens are for sale
    with pytest.raises(ValueError):
        buy_cost(TINY, Decimal(0))
    with pytest.raises(ValueError):
        sell_proceeds(TINY, Decimal(0))


def test_fee_is_a_parameter_and_zero_fee_is_a_free_round_trip() -> None:
    assert fee_amount(Decimal(15), FEE) == Decimal("0.1875")
    assert fee_amount(Decimal(15), Decimal(0)) == Decimal(0)
    assert curve_input_from_budget(Decimal("15.1875"), FEE) == Decimal(15)
    assert curve_input_from_budget(Decimal(15), Decimal(0)) == Decimal(15)
    free = quote_buy(TINY, Decimal(15), Decimal(0))
    assert free.tokens == Decimal(100)
    assert free.total_sol == Decimal(15)
    assert quote_sell(free.reserves_after, free.tokens, Decimal(0)).net_sol == Decimal(15)


def test_the_documented_fee_is_the_one_astra_confirmed_but_the_math_never_reads_it() -> None:
    assert CURVE_TRADE_FEE_PCT == Decimal("1.25")
    assert buy_cost(TINY, Decimal(100)) == Decimal(15)  # pre-fee by construction


def test_round_trip_with_no_other_trader_loses_exactly_the_two_fees() -> None:
    buy = quote_buy(TINY, Decimal("15.1875"), FEE)
    assert buy.curve_cost_sol == Decimal(15)
    assert buy.fee_sol == Decimal("0.1875")
    assert buy.tokens == Decimal(100)
    assert buy.average_price_sol == Decimal("0.151875")
    sell = quote_sell(buy.reserves_after, buy.tokens, FEE)
    assert sell.curve_proceeds_sol == Decimal(15)
    assert sell.fee_sol == Decimal("0.1875")
    assert sell.net_sol == Decimal("14.8125")
    assert buy.total_sol - sell.net_sol == buy.fee_sol + sell.fee_sol == Decimal("0.375")


def test_round_trip_across_a_third_party_trade_loses_the_fees_plus_the_impact() -> None:
    buy = quote_buy(TINY, Decimal("15.1875"), FEE)
    dumped_on = reserves_after_sell(buy.reserves_after, Decimal(50))  # a third party sells
    sell = quote_sell(dumped_on, buy.tokens, FEE)
    impact = buy.curve_cost_sol - sell.curve_proceeds_sol
    assert impact > 0
    # Exact to the working precision: the identity involves three divisions that
    # do not terminate, so the dust lives in the 28th digit, not in the model.
    loss = buy.total_sol - sell.net_sol
    assert abs(loss - (buy.fee_sol + sell.fee_sol + impact)) <= Decimal("1e-27")
    assert loss > buy.fee_sol + sell.fee_sol


@settings(max_examples=200, deadline=None)
@given(
    sol=st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=6),
    tokens=st.decimals(min_value=Decimal("1000"), max_value=Decimal("1e9"), places=6),
    small=st.decimals(min_value=Decimal("1"), max_value=Decimal("100"), places=6),
    extra=st.decimals(min_value=Decimal("1"), max_value=Decimal("100"), places=6),
)
def test_buy_cost_is_strictly_increasing_in_size(
    sol: Decimal, tokens: Decimal, small: Decimal, extra: Decimal
) -> None:
    reserves = CurveReserves(sol, tokens)
    assume(small + extra < tokens)
    assert buy_cost(reserves, small + extra) > buy_cost(reserves, small) > 0


@settings(max_examples=200, deadline=None)
@given(
    sol=st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=6),
    tokens=st.decimals(min_value=Decimal("1000"), max_value=Decimal("1e9"), places=6),
    spend=st.decimals(min_value=Decimal("0.001"), max_value=Decimal("100"), places=6),
)
def test_tokens_for_sol_never_empties_the_curve_and_costs_what_it_bought(
    sol: Decimal, tokens: Decimal, spend: Decimal
) -> None:
    reserves = CurveReserves(sol, tokens)
    bought = tokens_for_sol(reserves, spend)
    assert Decimal(0) < bought < tokens
    # The inverse holds to the working precision, not bit-for-bit: both sides divide.
    assert abs(buy_cost(reserves, bought) - spend) <= spend * Decimal("1e-20")


@settings(max_examples=200, deadline=None)
@given(
    sol=st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=6),
    tokens=st.decimals(min_value=Decimal("1000"), max_value=Decimal("1e9"), places=6),
    size=st.decimals(min_value=Decimal("1"), max_value=Decimal("900"), places=6),
)
def test_sell_proceeds_are_bounded_by_the_sol_side_and_reserves_stay_positive(
    sol: Decimal, tokens: Decimal, size: Decimal
) -> None:
    reserves = CurveReserves(sol, tokens)
    proceeds = sell_proceeds(reserves, size)
    assert Decimal(0) < proceeds < sol
    after = reserves_after_sell(reserves, size)
    assert after.virtual_sol_reserves > 0
    assert after.virtual_token_reserves > tokens


@settings(max_examples=200, deadline=None)
@given(
    sol=st.decimals(min_value=Decimal("1"), max_value=Decimal("500"), places=6),
    tokens=st.decimals(min_value=Decimal("100000"), max_value=Decimal("1e9"), places=6),
    budget=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("50"), places=6),
    fee=st.decimals(min_value=Decimal("0"), max_value=Decimal("5"), places=4),
)
def test_the_round_trip_loss_is_always_the_fees_plus_the_impact(
    sol: Decimal, tokens: Decimal, budget: Decimal, fee: Decimal
) -> None:
    reserves = CurveReserves(sol, tokens)
    buy = quote_buy(reserves, budget, fee)
    sell = quote_sell(buy.reserves_after, buy.tokens, fee)
    impact = buy.curve_cost_sol - sell.curve_proceeds_sol
    loss = buy.total_sol - sell.net_sol
    assert abs(loss - (buy.fee_sol + sell.fee_sol + impact)) <= budget * Decimal("1e-20")
    # With no other trader the impact reverses exactly, so the whole loss is the
    # two fees — and with fee = 0 an immediate round trip is genuinely free. That
    # is the model being honest, not a discount: every real fill pays 1,25 %.
    if fee > 0:
        assert loss >= buy.fee_sol + sell.fee_sol - budget * Decimal("1e-20")
    else:
        assert abs(loss) <= budget * Decimal("1e-20")


def test_the_initial_constants_match_the_adapter_that_decodes_the_wire() -> None:
    from hunter_exchanges.pumpfun import curve as wire

    assert INITIAL_VIRTUAL_SOL_RESERVES == wire.INITIAL_VIRTUAL_SOL_RESERVES == Decimal(30)
    assert (
        INITIAL_VIRTUAL_TOKEN_RESERVES
        == wire.INITIAL_VIRTUAL_TOKEN_RESERVES
        == Decimal(1_073_000_000)
    )
    assert CURVE_TRADE_FEE_PCT == wire.CURVE_TRADE_FEE_PCT
    fresh = CurveReserves(INITIAL_VIRTUAL_SOL_RESERVES, INITIAL_VIRTUAL_TOKEN_RESERVES)
    assert marginal_price_sol(fresh) == wire.marginal_price_sol(
        INITIAL_VIRTUAL_SOL_RESERVES, INITIAL_VIRTUAL_TOKEN_RESERVES
    )
    assert market_cap_sol(fresh, TOTAL_SUPPLY) == wire.market_cap_sol(
        INITIAL_VIRTUAL_SOL_RESERVES, INITIAL_VIRTUAL_TOKEN_RESERVES, TOTAL_SUPPLY
    )


def _live_create_events() -> list[dict[str, object]]:
    rows = json.loads((FIXTURES / "pumpportal_ws_a41_live.json").read_text(encoding="utf-8"))
    out: list[dict[str, object]] = []
    for row in rows:
        payload = json.loads(str(row["raw"]))
        if "vTokensInBondingCurve" in payload and "marketCapSol" in payload:
            out.append(payload)
    return out


def test_market_cap_reproduces_the_number_the_live_socket_reported() -> None:
    events = _live_create_events()
    assert len(events) == 7, "T4.1 capture shape changed; re-read the fixture before trusting it"
    for payload in events:
        reserves = CurveReserves(
            Decimal(str(payload["vSolInBondingCurve"])),
            Decimal(str(payload["vTokensInBondingCurve"])),
        )
        reported = Decimal(str(payload["marketCapSol"]))
        assert abs(market_cap_sol(reserves, TOTAL_SUPPLY) - reported) < Decimal("1e-12")


def test_market_cap_reproduces_the_rest_snapshot_of_a_mid_curve_token() -> None:
    coin = json.loads((FIXTURES / "coin_a41_raw.json").read_text(encoding="utf-8"))
    reserves = CurveReserves(
        Decimal(coin["virtual_sol_reserves"]) / Decimal(1_000_000_000),
        Decimal(coin["virtual_token_reserves"]) / Decimal(1_000_000),
        real_token_reserves=Decimal(coin["real_token_reserves"]) / Decimal(1_000_000),
    )
    supply = Decimal(coin["total_supply"]) / Decimal(1_000_000)
    assert abs(market_cap_sol(reserves, supply) - Decimal(str(coin["market_cap"]))) < Decimal(
        "1e-12"
    )
    assert curve_progress_pct(reserves) is None  # the launch denominator was never captured
