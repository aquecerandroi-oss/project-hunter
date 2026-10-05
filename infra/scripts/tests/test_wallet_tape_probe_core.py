"""Unit tests for ``infra/scripts/wallet_tape_probe_core.py`` (wave 0 of the "follow wallets" project).

Offline: real ``getTransaction`` fixtures of ``hunter_exchanges`` (their ``meta.logMessages`` are the same
lines a ``logsSubscribe`` notification carries) plus small synthetic logs for the attribution rules.

Run:
    uv run --no-sync pytest infra/scripts/tests/test_wallet_tape_probe_core.py -q
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from wallet_tape_probe_core import (  # noqa: E402  (path surgery must come first)
    AMM,
    PUMP,
    decode_event,
    event_name,
    find_known_pubkeys,
    parse_logs,
)

FIX = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures"


def _logs(path: str) -> list[str]:
    raw: Any = json.loads((FIX / path).read_text())
    result = raw.get("result", raw)
    return list(result["meta"]["logMessages"])


def _data(disc: bytes, body: bytes = b"") -> str:
    return "Program data: " + base64.b64encode(disc + body).decode()


def test_amm_router_tx_yields_sell_and_buy_events_from_the_amm_only() -> None:
    facts = parse_logs(_logs("pumpswap/t48e_rpc_amm_tx_5A1byFyLnuFA_raw.json"))
    names = [event_name(e.program, e.disc) for e in facts.events if e.program == AMM]
    assert names.count("SellEvent") == 1
    assert names.count("BuyEvent") == 1
    assert AMM in facts.invoked
    # the aggregator's own data lines are not pump events
    assert all(e.program in (AMM, PUMP) for e in facts.events)
    assert ordinals_are_per_program(facts.events)


def ordinals_are_per_program(events: Any) -> bool:
    seen: dict[str, list[int]] = {}
    for e in events:
        seen.setdefault(e.program, []).append(e.ordinal)
    return all(v == list(range(len(v))) for v in seen.values())


def test_sell_event_decodes_with_the_committed_decoder() -> None:
    facts = parse_logs(_logs("pumpswap/t48e_rpc_amm_tx_5mrYZLam93Kd_raw.json"))
    sells = [e for e in facts.events if event_name(e.program, e.disc) == "SellEvent"]
    assert len(sells) == 1
    got = decode_event(sells[0])
    assert got.ok and got.side == "sell" and got.kind == "swap"
    assert got.wallet and got.key  # user and pool
    assert got.sol_lamports and got.sol_lamports > 0


def test_buy_event_is_counted_raw_and_never_claims_a_committed_decode() -> None:
    facts = parse_logs(_logs("pumpswap/t48f_rpc_amm_tx_nocreator_4mvEcZZp8mj5_raw.json"))
    buys = [e for e in facts.events if event_name(e.program, e.disc) == "BuyEvent"]
    assert len(buys) == 1
    got = decode_event(buys[0])
    assert got.ok is None and got.reason == "no_decoder_raw_count_only"
    assert got.side == "buy" and got.kind == "swap"
    # the offset-inferred wallet is exposed under its own, labelled field
    assert got.wallet is None
    assert got.inferred_wallet is not None and len(got.inferred_wallet) >= 32


def test_pump_trade_event_decodes_both_layouts() -> None:
    old = parse_logs(_logs("pumpfun/rpc_tx_r43_real_buy_json_raw.json"))
    new = parse_logs(_logs("pumpfun/t48e_rpc_tx_buy_2qnMHiEaNfxX_raw.json"))
    for facts in (old, new):
        trades = [e for e in facts.events if event_name(e.program, e.disc) == "TradeEvent"]
        assert len(trades) == 1
        got = decode_event(trades[0])
        assert got.ok and got.side in ("buy", "sell") and got.kind == "swap"
        assert got.wallet and got.key and got.event_ts and got.event_ts > 1_700_000_000


def test_data_line_of_a_foreign_program_is_not_attributed_to_the_pump_program() -> None:
    other = "FeesProgram1111111111111111111111111111111111"
    logs = [
        f"Program {other} invoke [1]",
        _data(bytes.fromhex("bddb7fd34ee661ee"), b"\x00" * 5),
        f"Program {other} success",
    ]
    facts = parse_logs(logs)
    assert facts.events == ()
    assert facts.foreign_data == {other: 1}


def test_truncated_marker_and_bad_base64_are_reported() -> None:
    logs = [
        f"Program {PUMP} invoke [1]",
        "Program data: !!!not-base64!!!",
        "Log truncated",
    ]
    facts = parse_logs(logs)
    assert facts.truncated is True
    assert facts.bad_b64 == 1
    assert facts.events == ()


def test_undecodable_trade_event_keeps_its_reason() -> None:
    logs = [
        f"Program {PUMP} invoke [1]",
        _data(bytes.fromhex("bddb7fd34ee661ee"), b"\x01" * 10),  # truncated body
        f"Program {PUMP} success",
    ]
    (event,) = parse_logs(logs).events
    got = decode_event(event)
    assert got.ok is False and got.reason and "truncated" in got.reason.lower()


def test_instruction_names_are_attributed_to_the_program_on_top_of_the_stack() -> None:
    facts = parse_logs(_logs("pumpswap/t48f_rpc_amm_tx_nocreator_2bYPbC8hziYA_raw.json"))
    amm_ix = [name for prog, name in facts.instructions if prog == AMM]
    assert "Buy" in amm_ix and "Sell" in amm_ix
    # the token program's TransferChecked is not an AMM instruction
    assert "TransferChecked" not in amm_ix


def test_find_known_pubkeys_scans_every_offset() -> None:
    from hunter_exchanges.pumpfun.solana_codec import b58encode

    pool = bytes(range(1, 33))
    payload = b"\xaa" * 13 + pool + b"\xbb" * 9
    assert find_known_pubkeys(payload, {b58encode(pool)}) == {b58encode(pool)}
    assert find_known_pubkeys(payload, {b58encode(bytes(32))}) == set()


def test_event_name_of_an_unknown_discriminator_is_its_hex() -> None:
    assert event_name(AMM, bytes.fromhex("0102030405060708")) == "unknown:0102030405060708"


@pytest.mark.parametrize(
    "path",
    [
        "pumpswap/t48e_rpc_amm_tx_5A1byFyLnuFA_raw.json",
        "pumpswap/t48f_rpc_amm_tx_nocreator_2bYPbC8hziYA_raw.json",
        "pumpfun/t48e_rpc_tx_buy_2qnMHiEaNfxX_raw.json",
        "pumpfun/t48e_rpc_tx_sell_2DSRRspQNw13_raw.json",
    ],
)
def test_events_read_from_logs_equal_events_read_from_inner_instructions(path: str) -> None:
    """The check the probe's getTransaction sampler runs live: the logs hold every event the
    program emitted as a self-CPI (so ``logsSubscribe`` loses nothing unless the log is truncated)."""
    from wallet_tape_probe_core import inner_event_counts, log_event_counts

    raw: Any = json.loads((FIX / path).read_text())
    tx = raw.get("result", raw)
    from_logs = log_event_counts(parse_logs(tx["meta"]["logMessages"]))
    assert from_logs and from_logs == inner_event_counts(tx)


def test_buy_event_pool_and_user_equal_the_accounts_of_the_amm_buy_instruction() -> None:
    """Astra (wallet-tape-probe, must-fix 6): the inferred offsets are checked against the
    instruction's own accounts (pool = account 0, user = account 1 of the AMM ``buy``), not only
    against the fee payer — on direct and routed real buys."""
    from hunter_exchanges.pumpfun.solana_codec import b58encode

    checked = 0
    for name in (
        "t48e_rpc_amm_tx_5A1byFyLnuFA_raw.json",  # routed (BuyExactQuoteIn inside a router)
        "t48f_rpc_amm_tx_nocreator_2bYPbC8hziYA_raw.json",
        "t48f_rpc_amm_tx_nocreator_4mvEcZZp8mj5_raw.json",
    ):
        raw: Any = json.loads((FIX / "pumpswap" / name).read_text())
        tx = raw.get("result", raw)
        keys = list(tx["transaction"]["message"]["accountKeys"])
        meta = tx["meta"]
        keys += list(meta.get("loadedAddresses", {}).get("writable", []))
        keys += list(meta.get("loadedAddresses", {}).get("readonly", []))
        instrs = list(tx["transaction"]["message"]["instructions"])
        for inner in meta["innerInstructions"]:
            instrs += inner["instructions"]
        amm_accounts = [
            [keys[i] for i in ix["accounts"][:2]]
            for ix in instrs
            if keys[ix["programIdIndex"]] == AMM and len(ix["accounts"]) >= 2
        ]
        for event in parse_logs(meta["logMessages"]).events:
            if event_name(event.program, event.disc) != "BuyEvent":
                continue
            got = decode_event(event)
            assert got.inferred_pool and got.inferred_wallet
            assert [got.inferred_pool, got.inferred_wallet] in amm_accounts, name
            assert b58encode(event.payload[120:152]) == got.inferred_pool
            checked += 1
    assert checked == 3


def test_audit_block_counts_what_mentions_a_program_and_was_not_received() -> None:
    from wallet_tape_probe_core import audit_block

    def tx(sig: str, keys: list[str], err: Any = None, loaded: list[str] | None = None) -> Any:
        return {
            "transaction": {"signatures": [sig], "message": {"accountKeys": keys}},
            "meta": {"err": err, "loadedAddresses": {"writable": loaded or [], "readonly": []}},
        }

    block: Any = {
        "transactions": [
            tx("S1", ["w", PUMP]),  # received
            tx("S2", ["w", AMM]),  # missed
            tx("S3", ["w", PUMP], err={"InstructionError": [0, "x"]}),  # missed and failed
            tx("S4", ["w"], loaded=[AMM]),  # mention through an address lookup table
            tx("S5", ["w", "z"]),  # not ours
        ]
    }
    out = audit_block(block, {PUMP: {"S1"}, AMM: {"S4"}})
    assert out[PUMP] == {
        "txs": 2,
        "received": 1,
        "missed": 1,
        "missed_failed": 1,
        "missed_sigs": ["S3"],
        "success_txs": 1,
        "events": {},
    }
    assert out[AMM] == {
        "txs": 2,
        "received": 1,
        "missed": 1,
        "missed_failed": 0,
        "missed_sigs": ["S2"],
        "success_txs": 2,
        "events": {},
    }


def test_audit_block_counts_the_events_of_successful_mentions_from_their_own_logs() -> None:
    """The block is the websocket-independent truth: how many swap events the chain really emitted
    (the storage sizing needs this, not what a lagging public socket happened to deliver)."""
    from wallet_tape_probe_core import audit_block

    raw: Any = json.loads(
        (FIX / "pumpswap/t48f_rpc_amm_tx_nocreator_2bYPbC8hziYA_raw.json").read_text()
    )
    real = raw.get("result", raw)  # one Sell + one Buy on the AMM
    failed = json.loads(json.dumps(real))
    failed["meta"]["err"] = {"InstructionError": [0, "x"]}
    failed["transaction"]["signatures"] = ["FAILED"]
    block: Any = {"transactions": [real, failed]}
    sig = real["transaction"]["signatures"][0]
    out = audit_block(block, {PUMP: set(), AMM: {sig}})
    assert out[AMM]["txs"] == 2 and out[AMM]["success_txs"] == 1
    assert out[AMM]["events"] == {"SellEvent": 1, "BuyEvent": 1}
    assert out[PUMP]["events"] == {}


def test_late_delivery_is_not_a_loss_coverage_is_evaluated_against_a_later_received_set() -> None:
    """Astra's must-fix 1, second half: a lagging socket delivers a slot 28 s late. Auditing a block
    24 s after its slot called that 'missed'. The block's mentions are kept and judged again later."""
    from wallet_tape_probe_core import block_mentions, coverage

    def tx(sig: str, program: str, err: Any = None) -> Any:
        return {
            "transaction": {"signatures": [sig], "message": {"accountKeys": ["w", program]}},
            "meta": {"err": err, "loadedAddresses": {"writable": [], "readonly": []}},
        }

    mentions = block_mentions(
        {"transactions": [tx("A", PUMP), tx("B", PUMP), tx("C", AMM, err={"x": 1})]}
    )
    assert mentions == {PUMP: [("A", True), ("B", True)], AMM: [("C", False)]}
    early = coverage(mentions, {PUMP: {"A"}, AMM: set()})
    late = coverage(mentions, {PUMP: {"A", "B"}, AMM: {"C"}})
    assert early[PUMP]["missed"] == 1 and early[AMM]["missed_failed"] == 1
    assert late[PUMP]["missed"] == 0 and late[AMM]["missed"] == 0
