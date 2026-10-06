"""Unit tests for ``infra/scripts/pumpfun_rt_probe_conv.py`` — wire message -> probe event, for the five
sources of the pump.fun realtime latency probe (2026-10-06). Offline: shapes copied from the frames the site
and the public feeds served on 06/10/2026 (shortened; no credential in any of them).

Run:
    uv run --no-sync pytest infra/scripts/tests/test_pumpfun_rt_probe_conv.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from pumpfun_rt_probe_conv import (  # noqa: E402  (path surgery must come first)
    conv_core,
    conv_pumpportal,
    conv_rpc_logs,
    conv_trenches,
    conv_unified,
    iso_to_epoch,
    parse_block_time,
)

CREATE = {
    "slot_index_id": "00045377553700023900000002",
    "tx": "SIG1",
    "mint": "MINT1pump",
    "name": "Uncle",
    "symbol": "UP",
    "created_timestamp": "2026-10-06T03:06:42+00:00",
    "program": "pump",
    "creator": "CREATOR1",
    "metadata_uri": "https://x/y",
}
TRADE = {
    "slotIndexId": "00045377570300044200000301",
    "tx": "SIG2",
    "timestamp": "2026-10-06T03:07:28+00:00",
    "program": "pump",
    "isBondingCurve": True,
    "mintAddress": "MINT1pump",
    "userAddress": "WALLET1",
    "type": "buy",
    "amountSol": "0.031726277",
}


def test_iso_to_epoch_reads_offsets_zulu_and_milliseconds() -> None:
    assert iso_to_epoch("2026-10-06T03:06:42+00:00") == 1791256002.0
    assert iso_to_epoch("2026-10-06T03:06:42Z") == 1791256002.0
    assert iso_to_epoch("2026-10-06T03:09:39.713Z") == pytest.approx(1791256179.713)
    assert iso_to_epoch(None) is None and iso_to_epoch("nope") is None


def test_unified_creation_keeps_signature_mint_slot_and_block_second() -> None:
    kind, id_, extra = conv_unified("unifiedCoinCreationEvent", CREATE) or ("", "", {})
    assert (kind, id_) == ("create", "SIG1")
    assert extra["mint"] == "MINT1pump" and extra["slot"] == 453775537
    assert extra["bt"] == 1791256002.0 and extra["program"] == "pump"


def test_unified_processed_trade_and_lite_share_the_signature_key() -> None:
    k1, id1, e1 = conv_unified("unifiedTradeEvent.processed.MINT1pump", TRADE) or ("", "", {})
    assert (k1, id1) == ("trade", "SIG2")
    assert e1["mint"] == "MINT1pump" and e1["user"] == "WALLET1" and e1["side"] == "buy"
    assert e1["slot"] == 453775703 and e1["bt"] == 1791256048.0
    lite = {"mint": "MINT1pump", "tx": "SIG2", "slotIndexId": TRADE["slotIndexId"], "type": "buy",
            "userAddress": "WALLET1", "timestamp": TRADE["timestamp"]}  # fmt: skip
    k2, id2, _ = conv_unified("unifiedTradeEvent.lite.MINT1pump", lite) or ("", "", {})
    assert (k2, id2) == ("lite", "SIG2")


def test_unified_ignores_unknown_subjects_and_payloads_without_a_signature() -> None:
    assert conv_unified("somethingElse", CREATE) is None
    assert conv_unified("unifiedCoinCreationEvent", {"mint": "x"}) is None


def test_core_balance_change_keeps_wallet_mint_slot_and_the_servers_millisecond_stamp() -> None:
    msg = {
        "walletAddress": "W", "tokenMint": "SOL", "balance": "0.4", "slot": 453776189,
        "timestamp": "2026-10-06T03:09:39.713Z", "txSignature": "SIG3", "txIndex": "441",
    }  # fmt: skip
    kind, id_, extra = conv_core("account_balance_change.W.SOL", msg) or ("", "", {})
    assert (kind, id_) == ("balance", "SIG3")
    assert extra["wallet"] == "W" and extra["mint"] == "SOL" and extra["slot"] == 453776189
    assert extra["srv_ts"] == pytest.approx(1791256179.713)


def test_pumpportal_create_and_the_non_create_and_the_ack() -> None:
    got = conv_pumpportal({"signature": "S", "mint": "M", "txType": "create", "pool": "bonk"})
    assert got == ("create", "S", {"mint": "M", "pool": "bonk"})
    mig = conv_pumpportal(
        {"signature": "S2", "mint": "M2", "txType": "migrate", "pool": "pump-amm"}
    )
    assert mig is not None and mig[0] == "migration" and mig[1] == "S2"
    assert conv_pumpportal({"message": "Successfully subscribed to token creation events."}) is None


def test_trenches_add_remove_and_kol_updates_become_events_and_plain_updates_do_not() -> None:
    delta = {
        "type": "delta", "board": "new", "baseVersion": 1, "version": 2, "serverTs": 1791256002500,
        "patches": [
            {"op": "add", "mint": "M1", "idx": 0, "fields": {"m": "M1", "pg": "pump", "kol": 0, "age": 1}},
            {"op": "update", "mint": "M2", "fields": {"mc": 5}},
            {"op": "update", "mint": "M3", "fields": {"kol": 2}},
            {"op": "remove", "mint": "M4"},
        ],
    }  # fmt: skip
    got = conv_trenches("new", delta)
    kinds = [(k, i) for k, i, _ in got]
    assert kinds == [("add", "M1"), ("kol", "M3"), ("remove", "M4")]
    assert got[0][2]["server_ts"] == 1791256002.5 and got[0][2]["entry"]["pg"] == "pump"
    assert got[1][2]["kol"] == 2


def test_trenches_snapshot_is_one_marker_event_not_one_per_entry() -> None:
    snap = {"type": "snapshot", "board": "new", "version": 9, "serverTs": 1791256002000,
            "entries": [{"m": "A"}, {"m": "B"}]}  # fmt: skip
    assert conv_trenches("new", snap) == [("snapshot", "new", {"n": 2, "server_ts": 1791256002.0})]


def test_rpc_logs_notification_becomes_a_fact_and_the_ack_does_not() -> None:
    assert conv_rpc_logs({"jsonrpc": "2.0", "result": 7, "id": 1}) is None
    note: dict[str, Any] = {
        "jsonrpc": "2.0", "method": "logsNotification",
        "params": {"result": {"context": {"slot": 99},
                              "value": {"signature": "SIG9", "err": None, "logs": []}}, "subscription": 7},
    }  # fmt: skip
    fact = conv_rpc_logs(note)
    assert (
        fact is not None and fact["id"] == "SIG9" and fact["slot"] == 99 and fact["create"] is False
    )


def test_iso_without_a_timezone_is_refused_not_read_in_the_machines_zone() -> None:
    assert iso_to_epoch("2026-10-06T03:06:42") is None


def test_block_time_answer_separates_a_value_from_a_refusal_and_from_a_missing_block() -> None:
    assert parse_block_time({"jsonrpc": "2.0", "result": 1791256002, "id": 1}) == (1791256002, None)
    value, err = parse_block_time(
        {"jsonrpc": "2.0", "error": {"code": 413, "message": "You have used your data allowance"}}
    )
    assert value is None and err is not None and "413" in err and "allowance" in err
    assert parse_block_time({"jsonrpc": "2.0", "result": None, "id": 1}) == (None, "no block time")
    assert parse_block_time("garbage") == (None, "unreadable answer")
