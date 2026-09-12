"""Local quotes reproduce the chain lamport for lamport, and the site's quote within 1e-5.

Sources: two real fills (``rpc_tx_probe_raw.json`` sell, ``rpc_tx_buy_raw.json`` buy),
the site's ``swap-build`` reply for a 0.01 SOL exact-in buy on the same coin
(``swap_build_probe4_raw.txt``, 2026-09-12 07:46:38 UTC; the tape shows no trade
on the coin between the sell at 07:34:28 and that call, so the post-sell reserves
are the reserves the site quoted on), and the mainnet simulation proof
(``simulation_proof_mainnet_raw.json``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.quote import (
    BONDING_CURVE_FEE_TIER_2026_05_20,
    CurveReserves,
    FeeBps,
    curve_progress_bps,
    parse_global_params,
    quote_buy,
    quote_buy_for_budget,
    quote_sell,
)
from hunter_exchanges.pumpfun.trade_event import TradeEvent, trade_events_from_transaction

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
FEES = BONDING_CURVE_FEE_TIER_2026_05_20


def _event(name: str) -> TradeEvent:
    tx: dict[str, Any] = json.loads((FIXTURES / name).read_text())["result"]
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    return event


def _pre_reserves(event: TradeEvent) -> CurveReserves:
    sign = 1 if event.is_buy else -1
    return CurveReserves(
        virtual_sol=event.virtual_sol_reserves - sign * event.sol_amount,
        virtual_token=event.virtual_token_reserves + sign * event.token_amount,
        real_sol=event.real_sol_reserves - sign * event.sol_amount,
        real_token=event.real_token_reserves + sign * event.token_amount,
    )


def test_sell_quote_reproduces_the_real_fill() -> None:
    event = _event("rpc_tx_probe_raw.json")
    fees = FeeBps(event.fee_basis_points, event.cashback_fee_basis_points)  # 95 + 30
    quote = quote_sell(_pre_reserves(event), event.token_amount, fees, max_slippage_bps=2500)
    assert quote.sol_amount == event.sol_amount == 724716993
    assert quote.protocol_fee == event.fee == 6884812
    assert quote.creator_fee == event.cashback == 2174151  # cashback takes the creator share
    assert quote.net_proceeds == event.sell_net_proceeds == 715658030
    assert quote.reserves_after.virtual_sol == event.virtual_sol_reserves
    assert quote.reserves_after.virtual_token == event.virtual_token_reserves
    assert quote.min_sol_output == 715658030 * 7500 // 10000


def test_buy_quote_reproduces_the_real_fill() -> None:
    event = _event("rpc_tx_buy_raw.json")
    fees = FeeBps(event.fee_basis_points, event.cashback_fee_basis_points)
    quote = quote_buy(_pre_reserves(event), event.token_amount, fees, max_slippage_bps=0)
    assert quote.sol_amount == event.sol_amount == 977777777
    assert quote.protocol_fee == event.fee == 9288889
    assert quote.creator_fee == event.cashback == 2933334
    assert quote.total_cost == event.buy_total_cost == 990000000
    assert quote.max_sol_cost == 990000000  # zero slippage: exactly the cost
    assert quote.reserves_after.virtual_sol == event.virtual_sol_reserves


def test_fee_tier_matches_the_program_return_data() -> None:
    """``GetFeesWithQuoteMint`` returned ``AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA`` in every
    fixture: lp 0, protocol 95, creator 30 — the documented bonding-curve tier."""
    import base64
    import struct

    lp, protocol, creator = struct.unpack(
        "<QQQ", base64.b64decode("AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA")
    )
    assert (lp, protocol, creator) == (0, FEES.protocol, FEES.creator) == (0, 95, 30)


def test_site_swap_build_quote_within_1e5() -> None:
    site: dict[str, Any] = json.loads((FIXTURES / "swap_build_probe4_raw.txt").read_text())
    assert site["venue"] == "bonding_curve" and site["slippage_bps"] == 100
    event = _event("rpc_tx_probe_raw.json")  # the last trade before the site call
    reserves = CurveReserves(
        event.virtual_sol_reserves,
        event.virtual_token_reserves,
        event.real_sol_reserves,
        event.real_token_reserves,
    )
    ours = quote_buy_for_budget(reserves, 10_000_000, FEES, max_slippage_bps=100)
    site_out = int(site["amount_out"]["atomic"])
    diff = ours.token_amount - site_out
    assert ours.total_cost <= 10_000_000
    assert abs(diff) / site_out < 1e-5, f"site {site_out} ours {ours.token_amount} diff {diff}"
    assert int(site["min_amount_out"]["atomic"]) == site_out * 9900 // 10000


def test_budget_quote_is_maximal_and_never_above_budget() -> None:
    event = _event("rpc_tx_probe_raw.json")
    reserves = _pre_reserves(event)
    for budget in (1_000, 45, 10_000_000, 1_000_000_000):
        quote = quote_buy_for_budget(reserves, budget, FEES, max_slippage_bps=100)
        assert quote.total_cost <= budget
        bigger = quote_buy(reserves, quote.token_amount + 1, FEES, max_slippage_bps=100)
        assert bigger.total_cost > budget, "one more subunit must not fit"
    with pytest.raises(ValueError, match="budget"):
        quote_buy_for_budget(reserves, 1, FEES, max_slippage_bps=100)


def test_simulation_proof_fixture_matches_quote_and_program_threshold() -> None:
    """The mainnet simulation (never sent) accepted ``max_sol_cost = total_cost``
    and refused ``total_cost - 1`` with ``TooMuchSolRequired`` (6002)."""
    proof: dict[str, Any] = json.loads((FIXTURES / "simulation_proof_mainnet_raw.json").read_text())
    assert proof["sent"] is False and proof["sig_verify"] is False
    curve = proof["curve"]
    reserves = CurveReserves(
        curve["virtual_sol"], curve["virtual_token"], curve["real_sol"], curve["real_token"]
    )
    quote = quote_buy(reserves, proof["buy_quote"]["token_amount"], FEES, max_slippage_bps=100)
    assert quote.total_cost == proof["buy_quote"]["total_cost"]
    sims = proof["simulations"]
    assert sims["buy_full"]["ok"] is True and sims["sell_full"]["ok"] is True
    assert sims["buy_max_sol_cost_one_lamport_short"]["err"] == {
        "InstructionError": [2, {"Custom": 6002}]
    }
    assert sims["buy_without_undocumented_account"]["err"] == {
        "InstructionError": [2, {"Custom": 6062}]
    }
    assert len(sims["buy_full"]["accounts"]) == 18 and len(sims["sell_full"]["accounts"]) == 17


def test_slippage_is_explicit_and_bounded() -> None:
    reserves = CurveReserves(30_000_000_000, 1_073_000_000_000_000, 0, 793_100_000_000_000)
    with pytest.raises(TypeError):
        quote_buy(reserves, 1_000_000, FEES)  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        quote_buy(reserves, 1_000_000, FEES, max_slippage_bps=5001)
    with pytest.raises(ValueError):
        quote_sell(reserves, 1_000_000, FEES, max_slippage_bps=-1)
    quote = quote_buy(reserves, 1_000_000, FEES, max_slippage_bps=100)
    assert quote.max_sol_cost == -(-quote.total_cost * 10100 // 10000)


def test_complete_curve_and_oversized_buys_are_refused() -> None:
    done = CurveReserves(30_000_000_000, 1_073_000_000_000_000, 0, 0, complete=True)
    with pytest.raises(ValueError, match="curve_complete"):
        quote_buy(done, 1, FEES, max_slippage_bps=0)
    live = CurveReserves(30_000_000_000, 1_073_000_000_000_000, 0, 10)
    with pytest.raises(ValueError, match="real token reserves"):
        quote_buy(live, 11, FEES, max_slippage_bps=0)
    with pytest.raises(ValueError):
        FeeBps(10_000, 0)


def test_global_params_and_progress() -> None:
    params = parse_global_params(
        {
            "slot": 446349159,
            "signature": "x",
            "initial_virtual_token_reserves": 1073000000000000,
            "initial_virtual_sol_reserves": 30000000000,
            "initial_real_token_reserves": 793100000000000,
            "token_total_supply": 1000000000000000,
            "fee_basis_points": 95,
            "timestamp": 1789190000,
        }
    )
    event = _event("rpc_tx_probe_raw.json")
    reserves = CurveReserves(
        event.virtual_sol_reserves,
        event.virtual_token_reserves,
        event.real_sol_reserves,
        event.real_token_reserves,
    )
    progress = curve_progress_bps(reserves, params)
    assert 0 < progress < 10_000
    assert progress == (793100000000000 - event.real_token_reserves) * 10_000 // 793100000000000
    with pytest.raises(ValueError):
        parse_global_params({"slot": 1.5})
