"""T4.8g — the events after the 2026-10-08 redeploy (pump slot 454596459, PumpSwap 454596406):
**no byte layout moved**. ``TradeEvent`` (pump), ``CompleteEvent`` (pump) and PumpSwap's
``SellEvent``/``BuyEvent`` decode with the T4.8e/T4.8f decoders unchanged.

Fixtures ``t48g_rpc_{tx,amm_tx}_*_raw.json``: real ``getTransaction`` results of 2026-10-08, read-only
(provenance in ``t48g_provenance.json`` of each fixture dir).

What is NEW and only noted, never decoded as money: instruction names (``buy_exact_sol_in``,
``multi_hop_swap``, PumpSwap ``buy_exact_quote_in_v2``) — ``ix_name`` is a free string in the event,
so the layout rule (a tail validated after the variable fields) already carries them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.curve_completion import (
    COMPLETE_EVENT_DISCRIMINATOR,
    decode_complete_event,
)
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event import (
    LAYOUT_TRAILING_U64,
    scan_trade_event_logs,
    trade_events_from_logs,
    trade_events_from_transaction,
)
from hunter_exchanges.pumpfun.tx import bonding_curve_address
from hunter_exchanges.pumpswap.buy_event import (
    LAYOUT_TRAILING_U64 as BUY_LAYOUT,
)
from hunter_exchanges.pumpswap.buy_event import (
    buy_events_from_transaction,
)
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import (
    LAYOUT_TRAILING_U64 as SELL_LAYOUT,
)
from hunter_exchanges.pumpswap.sell_event import (
    sell_events_from_transaction,
)

PUMPFUN = Path(__file__).parents[1] / "fixtures/pumpfun"
PUMPSWAP = Path(__file__).parents[1] / "fixtures/pumpswap"
NATIVE_SOL = "11111111111111111111111111111111"
PUMP_DEPLOY, SWAP_DEPLOY = 454_596_459, 454_596_406


def _tx(directory: Path, name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((directory / name).read_text()))


# ``(fixture, ix_name, is_buy, sol_amount, trailing_u64, holder_rewards)`` — read off the chain.
_PUMP = [
    ("t48g_rpc_tx_buy_3p8KxySa18L6_raw.json", "buy", True, 189_868_706, 4_943_423, 0),
    ("t48g_rpc_tx_buy_4yATaRdQNe2N_raw.json", "buy", True, 26_740_586, 115_019, 0),
    ("t48g_rpc_tx_buy_Kz7Nk1YiVWWj_raw.json", "buy", True, 9_876_542, 3_936_534, 29_630),
    ("t48g_rpc_tx_buy_iJjSTjH8AoKT_raw.json", "buy", True, 790_123_455, 0, 0),
    ("t48g_rpc_tx_sell_2zmu5NQsqrJ3_raw.json", "sell", False, 1_213_606_443, 112_704_770, 0),
    ("t48g_rpc_tx_sell_3SefGhSLx9f9_raw.json", "sell", False, 631_984_680, 192_318_435, 1_895_955),
    ("t48g_rpc_tx_sell_49Lfa4aoEdTw_raw.json", "sell", False, 2_943_209_875, 89_475_789, 8_829_630),
    (
        "t48g_rpc_tx_sell_4Cuu6mMnzpvB_raw.json",
        "sell",
        False,
        3_466_061_896,
        72_962_964,
        10_398_186,
    ),
    (
        "t48g_rpc_tx_event_buy_exact_quote_in_2Sh2zTmnse3s_raw.json",
        "buy_exact_quote_in",
        True,
        987_654_320,
        72_962_964,
        2_962_963,
    ),
    (
        "t48g_rpc_tx_event_buy_exact_sol_in_2Hno2LqYACfE_raw.json",
        "buy_exact_sol_in",
        True,
        118_222_502,
        17_919_815,
        354_668,
    ),
]


@pytest.mark.parametrize(("name", "ix_name", "is_buy", "sol", "tail", "hr"), _PUMP)
def test_real_post_redeploy_trade_events_decode_with_the_unchanged_layout(
    name: str, ix_name: str, is_buy: bool, sol: int, tail: int, hr: int
) -> None:
    tx = _tx(PUMPFUN, name)
    assert tx["slot"] > PUMP_DEPLOY
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.layout == LAYOUT_TRAILING_U64  # the T4.8e layout, not a new one
    assert (event.ix_name, event.is_buy, event.sol_amount) == (ix_name, is_buy, sol)
    assert (event.trailing_u64, event.holder_rewards) == (tail, hr)
    assert event.quote_mint == NATIVE_SOL and event.quote_amount == event.sol_amount
    assert event.timestamp == tx["blockTime"]
    logs = tx["meta"]["logMessages"]
    scan = scan_trade_event_logs(logs)
    assert scan.events == (event,) and scan.undecodable == () and not scan.lost
    assert trade_events_from_logs(logs) == (event,)


def test_a_multi_hop_swap_event_has_another_pump_token_as_quote_and_no_sol() -> None:
    """Not a SOL-quoted curve trade: ``sol_amount`` is 0 and the quote is a pump token. It
    decodes (the layout is the same) and is NOT ours — the desk trades SOL-quoted curves only."""
    tx = _tx(PUMPFUN, "t48g_rpc_tx_event_multi_hop_swap_rRUVF4GSZNRA_raw.json")
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.ix_name == "multi_hop_swap" and event.layout == LAYOUT_TRAILING_U64
    assert event.sol_amount == 0 and event.quote_mint != NATIVE_SOL


def test_the_curve_completing_buy_is_followed_by_the_programs_complete_event() -> None:
    tx = _tx(PUMPFUN, "t48g_rpc_tx_complete_3qDvAqx3Ssut_raw.json")
    assert tx["slot"] > PUMP_DEPLOY
    (trade,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    keys: list[str] = list(tx["transaction"]["message"]["accountKeys"])
    loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
    keys += loaded.get("writable", []) + loaded.get("readonly", [])
    payloads = [
        b58decode(ix["data"])[8:]
        for group in tx["meta"]["innerInstructions"]
        for ix in group["instructions"]
        if keys[ix["programIdIndex"]] == PUMP_PROGRAM_ID
        and b58decode(ix["data"])[:8] == bytes.fromhex("e445a52e51cb9a1d")
    ]
    kinds = [p[:8] for p in payloads]
    assert kinds.count(COMPLETE_EVENT_DISCRIMINATOR) == 1
    done = decode_complete_event(next(p for p in payloads if p[:8] == COMPLETE_EVENT_DISCRIMINATOR))
    assert len(next(p for p in payloads if p[:8] == COMPLETE_EVENT_DISCRIMINATOR)) == 144
    assert done.mint == trade.mint and done.user == trade.user and done.quote_mint == NATIVE_SOL
    assert done.bonding_curve == bonding_curve_address(trade.mint)
    assert done.timestamp == trade.timestamp
    assert trade.is_buy and trade.real_token_reserves == 0  # the draining buy


# -- PumpSwap ---------------------------------------------------------------------------------

_SELLS = [
    ("t48g_rpc_amm_tx_sell_2C8QHNSJtxoh_raw.json", 43_495_595_942, 1_714_354, True, 0, 0),
    (
        "t48g_rpc_amm_tx_sell_5cWuAY9xJtrp_raw.json",
        443_891_453_692,
        45_091_700,
        True,
        136_988,
        963_766_469,
    ),
    (
        "t48g_rpc_amm_tx_sell_AXNiK4CmYw5m_raw.json",
        821_116_701_363,
        79_884_782,
        True,
        242_688,
        3_615_760_875,
    ),
    (
        "t48g_rpc_amm_tx_sell_YdnQWgW72poy_raw.json",
        185_302_193_907,
        80_207_980,
        True,
        771_231,
        1_978_527_830,
    ),
    (
        "t48g_rpc_amm_tx_sell_5b3eUPbMhPAH_raw.json",
        38_420_712_906,
        115_897_234,
        True,
        996_084,
        12_669_242_816,
    ),
]


@pytest.mark.parametrize(("name", "base_in", "user_out", "boost", "hr", "tail"), _SELLS)
def test_real_post_redeploy_sell_events_decode_with_the_unchanged_layout(
    name: str, base_in: int, user_out: int, boost: bool, hr: int, tail: int
) -> None:
    tx = _tx(PUMPSWAP, name)
    assert tx["slot"] > SWAP_DEPLOY
    (event,) = sell_events_from_transaction(tx)
    assert event.layout == SELL_LAYOUT
    assert (event.base_amount_in, event.user_quote_amount_out) == (base_in, user_out)
    assert (event.can_boost, event.holder_rewards, event.trailing_u64) == (boost, hr, tail)


_BUYS = [
    (
        "t48g_rpc_amm_tx_buy_29Ew15xD3NfJ_raw.json",
        "buy_exact_quote_in",
        104_502_240_959,
        7_017_954,
        1_791,
    ),
    ("t48g_rpc_amm_tx_buy_3ocZBFd1F6hf_raw.json", "buy", 8_445_761_198, 61_662_323_654_167, 0),
    (
        "t48g_rpc_amm_tx_buy_2TtLDZYrHaXf_raw.json",
        "buy_exact_quote_in_v2",
        260_658_732_315,
        990_000_000,
        12_443_936_816,
    ),
]


@pytest.mark.parametrize(("name", "ix_name", "base_out", "total_paid", "tail"), _BUYS)
def test_real_post_redeploy_buy_events_decode_and_conserve_money(
    name: str, ix_name: str, base_out: int, total_paid: int, tail: int
) -> None:
    tx = _tx(PUMPSWAP, name)
    assert tx["slot"] > SWAP_DEPLOY
    (event,) = buy_events_from_transaction(tx)
    assert event.layout == BUY_LAYOUT
    assert (event.ix_name, event.base_amount_out) == (ix_name, base_out)
    assert event.total_quote_paid == total_paid and event.money_conserves
    assert event.trailing_u64 == tail


def test_a_transaction_with_a_buy_and_a_sell_event_yields_both() -> None:
    """3ocZ: an arbitrage-shaped transaction (a buy and a sell on PumpSwap) — each decoder reads
    only its own event and neither swallows the other."""
    tx = _tx(PUMPSWAP, "t48g_rpc_amm_tx_buy_3ocZBFd1F6hf_raw.json")
    assert len(sell_events_from_transaction(tx)) == len(buy_events_from_transaction(tx)) == 1


def test_every_swap_fixture_has_its_event_under_the_pumpswap_program() -> None:
    for path in sorted(PUMPSWAP.glob("t48g_rpc_amm_tx_*_raw.json")):
        tx = cast(dict[str, Any], json.loads(path.read_text()))
        keys: list[str] = list(tx["transaction"]["message"]["accountKeys"])
        loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
        keys += loaded.get("writable", []) + loaded.get("readonly", [])
        owners: set[str] = {
            keys[ix["programIdIndex"]]
            for group in tx["meta"]["innerInstructions"]
            for ix in group["instructions"]
            if b58decode(ix["data"])[:8] == bytes.fromhex("e445a52e51cb9a1d")
        }
        assert PUMPSWAP_PROGRAM_ID in owners, path.name
