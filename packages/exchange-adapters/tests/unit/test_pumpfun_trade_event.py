"""``TradeEvent`` decoding from inner instructions and from ``Program data:`` logs."""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.models import NormalizedCurveTrade
from hunter_exchanges.pumpfun.trade_event import (
    EVENT_CPI_TAG,
    LAYOUT_HOLDER_REWARDS,
    LAYOUT_PRE_HOLDER_REWARDS,
    TRADE_EVENT_DISCRIMINATOR,
    decode_trade_event,
    normalized_curve_trade,
    trade_events_from_logs,
    trade_events_from_transaction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _tx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())["result"]


def _tx_no_wrapper(name: str) -> dict[str, Any]:
    """A ``getTransaction`` result recorded without the ``{"jsonrpc", "result"}``
    envelope — T4.46's R43 captures (``rpc_tx_r43_real_buy_json_raw.json``)."""
    return json.loads((FIXTURES / name).read_text())


def test_sell_event_from_inner_instruction_and_from_logs_agree() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    (from_inner,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    logs_only = {"meta": {"logMessages": tx["meta"]["logMessages"], "err": None}, "transaction": {}}
    (from_logs,) = trade_events_from_transaction(logs_only, program_id=PUMP_PROGRAM_ID)
    assert from_inner == from_logs
    assert from_inner.ix_name == "sell" and not from_inner.is_buy
    assert from_inner.mint == "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
    assert from_inner.user == "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"
    assert from_inner.fee_basis_points == 95 and from_inner.creator_fee_basis_points == 0
    assert (
        from_inner.cashback_fee_basis_points == 30 and from_inner.buyback_fee_basis_points == 5000
    )
    assert from_inner.buyback_fee == from_inner.fee * 5000 // 10000
    assert from_inner.quote_mint == "11111111111111111111111111111111"  # native SOL
    assert from_inner.quote_amount == from_inner.sol_amount
    assert from_inner.shareholders == ()
    assert from_inner.timestamp == tx["blockTime"]


def test_buy_event_through_router_with_lookup_table() -> None:
    tx = _tx("rpc_tx_buy_raw.json")
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    assert event.is_buy and event.ix_name == "buy"
    assert event.user == "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
    assert event.token_amount == 22628881309131 and event.sol_amount == 977777777


def test_failed_transaction_yields_no_fill() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    failed = {**tx, "meta": {**tx["meta"], "err": {"InstructionError": [4, {"Custom": 6002}]}}}
    assert trade_events_from_transaction(failed, program_id=PUMP_PROGRAM_ID) == ()
    assert trade_events_from_transaction({}, program_id=PUMP_PROGRAM_ID) == ()


def test_other_programs_events_are_ignored() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    assert (
        trade_events_from_transaction(tx, program_id="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
        == ()
    )


def test_truncated_or_foreign_bytes_are_refused() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    line = next(m for m in tx["meta"]["logMessages"] if m.startswith("Program data: "))
    raw = base64.b64decode(line[len("Program data: ") :])
    assert raw[:8] == TRADE_EVENT_DISCRIMINATOR
    assert decode_trade_event(EVENT_CPI_TAG + raw) == decode_trade_event(raw)
    with pytest.raises(ValueError, match="truncated"):
        decode_trade_event(raw[:-1])
    with pytest.raises(ValueError, match="trailing"):
        decode_trade_event(raw + b"\x00")
    with pytest.raises(ValueError, match="discriminator"):
        decode_trade_event(b"\x00" * 8 + raw[8:])


def test_the_2026_09_12_layout_appends_holder_rewards_and_nothing_else_is_tolerated() -> None:
    """The program deployed on 2026-09-12 appends ``holder_rewards_bps`` and
    ``holder_rewards`` (two u64) — real fields now (T4.8b). The older 359-byte layout
    decodes with both at 0 and ``layout`` naming it; any other trailing length is still
    refused (an unknown layout is not a fill)."""
    tx = _tx("rpc_tx_probe_raw.json")
    line = next(m for m in tx["meta"]["logMessages"] if m.startswith("Program data: "))
    raw = base64.b64decode(line[len("Program data: ") :])
    older = decode_trade_event(raw)
    assert older.holder_rewards_basis_points == 0 and older.holder_rewards == 0
    assert older.layout == LAYOUT_PRE_HOLDER_REWARDS
    newer = decode_trade_event(raw + (50).to_bytes(8, "little") + (1234).to_bytes(8, "little"))
    assert newer.holder_rewards_basis_points == 50 and newer.holder_rewards == 1234
    assert newer.layout == LAYOUT_HOLDER_REWARDS
    assert newer.sol_amount == older.sol_amount and newer.fee == older.fee
    assert newer.sell_net_proceeds == older.sell_net_proceeds
    with pytest.raises(ValueError, match="8 trailing bytes"):
        decode_trade_event(raw + b"\x00" * 8)
    with pytest.raises(ValueError, match="24 trailing bytes"):
        decode_trade_event(raw + b"\x00" * 24)


def test_a_real_sell_of_2026_09_12_decodes_the_holder_rewards_layout() -> None:
    """``t48b_rpc_tx_sell_raw.json``: 375 bytes consumed of 375, from the inner
    instruction and from the log alike; the pair is present and reads 0 on this fill."""
    tx = _tx("t48b_rpc_tx_sell_raw.json")
    (from_inner,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    logs_only = {"meta": {"logMessages": tx["meta"]["logMessages"], "err": None}, "transaction": {}}
    (from_logs,) = trade_events_from_transaction(logs_only, program_id=PUMP_PROGRAM_ID)
    assert from_inner == from_logs
    assert from_inner.layout == LAYOUT_HOLDER_REWARDS
    assert from_inner.holder_rewards_basis_points == 0 and from_inner.holder_rewards == 0
    assert from_inner.ix_name == "sell" and from_inner.mayhem_mode
    assert from_inner.mint == "2nG3hY94XM3zwf4rtuVkTvLGCJgBfcCggARUAkFSpump"
    assert from_inner.fee_basis_points == 95 and from_inner.creator_fee_basis_points == 30
    assert from_inner.cashback_fee_basis_points == 0 and from_inner.buyback_fee_basis_points == 0
    assert from_inner.quote_amount == from_inner.sol_amount == 1237388211
    assert from_inner.timestamp == tx["blockTime"] == 1789235562
    line = next(m for m in tx["meta"]["logMessages"] if m.startswith("Program data: "))
    raw = base64.b64decode(line[len("Program data: ") :])
    assert len(raw) == 375
    # a router buy of the same afternoon (``buy_exact_quote_in_v2``) emits the same layout
    (buy,) = trade_events_from_transaction(
        _tx("t48b_rpc_tx_buy_router_v2_raw.json"), program_id=PUMP_PROGRAM_ID
    )
    assert buy.is_buy and buy.ix_name == "buy_exact_quote_in"
    assert buy.layout == LAYOUT_HOLDER_REWARDS and buy.holder_rewards == 0


def test_trade_events_from_logs_matches_transaction_decode() -> None:
    """T4.52b-1: ``trade_events_from_logs`` (the shape a ``logsSubscribe``
    notification's ``value.logs`` carries) decodes the same event as the
    ``getTransaction`` logs-only path, with no ``program_id`` filtering."""
    tx = _tx("rpc_tx_probe_raw.json")
    (from_tx,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    (from_logs,) = trade_events_from_logs(tx["meta"]["logMessages"])
    assert from_tx == from_logs


def test_trade_events_from_logs_skips_non_trade_lines_without_raising() -> None:
    assert trade_events_from_logs(["Program 111 invoke [1]", "Program 111 success"]) == ()
    assert trade_events_from_logs([]) == ()
    assert trade_events_from_logs(["Program data: not-base64!!"]) == ()


def test_normalized_curve_trade_from_event_has_decimal_human_units_and_no_float() -> None:
    """T4.52b-1's ``NormalizedCurveTrade``: ``lamports`` raw, reserves in human
    units, everything ``Decimal`` — never a ``float`` anywhere in the model."""
    tx = _tx("rpc_tx_probe_raw.json")
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    trade = normalized_curve_trade(event, slot=tx["slot"], signature="sig-under-test")
    assert isinstance(trade, NormalizedCurveTrade)
    assert trade.mint == event.mint
    assert trade.slot == tx["slot"]
    assert trade.signature == "sig-under-test"
    assert trade.trader == event.user
    assert trade.side == "sell"  # from_tx.is_buy is False (module docstring, R43 test above)
    assert trade.creator == event.creator
    assert trade.mayhem is event.mayhem_mode
    for field_name in (
        "lamports",
        "virtual_sol_reserves",
        "virtual_token_reserves",
        "real_sol_reserves",
        "real_token_reserves",
    ):
        value = getattr(trade, field_name)
        assert isinstance(value, Decimal), field_name
    assert trade.lamports == Decimal(event.sol_amount)
    assert trade.virtual_sol_reserves == Decimal(event.virtual_sol_reserves) / Decimal(10**9)
    assert trade.block_time is not None and trade.block_time.tzinfo is not None


def test_normalized_curve_trade_block_time_none_when_event_has_no_timestamp() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    no_ts_event = replace(event, timestamp=0)
    trade = normalized_curve_trade(no_ts_event, slot=1, signature="s")
    assert trade.block_time is None


def test_r43_fixture_logs_decode_to_the_real_buy_trade_event() -> None:
    """The R43 fixture (T4.46's real mainnet buy, no RPC envelope) through the
    ``logsSubscribe`` code path: logs -> ``TradeEvent`` -> ``NormalizedCurveTrade``,
    cross-checked against the constants ``test_wallet_fills_r43.py`` established
    independently for the same transaction."""
    tx = _tx_no_wrapper("rpc_tx_r43_real_buy_json_raw.json")
    (event,) = trade_events_from_logs(tx["meta"]["logMessages"])
    assert event.is_buy
    assert event.user == "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
    assert event.mint == "7s4dKmpvQxNy5CwDpsy9SKw3JVoFGRYNd6F8mr4GAxi8"
    signature = tx["transaction"]["signatures"][0]
    assert signature == (
        "SwjKQmywDbwgXZnuhZzCiYYduVTTzdrA146vfS8uXebotkAesRDUU32i6obist86xSh5Pd926baRS8qWhcjEyK7"
    )
    trade = normalized_curve_trade(event, slot=tx["slot"], signature=signature)
    assert trade.slot == 447659328
    assert trade.side == "buy"
    assert trade.block_time is not None
    assert int(trade.block_time.timestamp()) == tx["blockTime"] == 1789605088
