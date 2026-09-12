"""``TradeEvent`` decoding from inner instructions and from ``Program data:`` logs."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.trade_event import (
    EVENT_CPI_TAG,
    TRADE_EVENT_DISCRIMINATOR,
    decode_trade_event,
    trade_events_from_transaction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _tx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())["result"]


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
    """T4.14: mainnet events of 2026-09-12 carry 16 more bytes than the recorded fixtures —
    the IDL ``main`` of that day appends ``holder_rewards_bps`` and ``holder_rewards`` (two
    u64). They decode as the optional pair; the older layout reads ``None``; any other
    trailing length is still refused (an unknown layout is not a fill)."""
    tx = _tx("rpc_tx_probe_raw.json")
    line = next(m for m in tx["meta"]["logMessages"] if m.startswith("Program data: "))
    raw = base64.b64decode(line[len("Program data: ") :])
    older = decode_trade_event(raw)
    assert older.holder_rewards_basis_points is None and older.holder_rewards is None
    newer = decode_trade_event(raw + (50).to_bytes(8, "little") + (1234).to_bytes(8, "little"))
    assert newer.holder_rewards_basis_points == 50 and newer.holder_rewards == 1234
    assert newer.sol_amount == older.sol_amount and newer.fee == older.fee
    assert newer.sell_net_proceeds == older.sell_net_proceeds
    with pytest.raises(ValueError, match="8 trailing bytes"):
        decode_trade_event(raw + b"\x00" * 8)
    with pytest.raises(ValueError, match="24 trailing bytes"):
        decode_trade_event(raw + b"\x00" * 24)
