"""T4.8e: the fill decoders against the programs redeployed on 2026-10-02.

Real ``getTransaction`` results of 2026-10-05 (third parties' trades, read-only capture):
before T4.8e ``decode_fills`` raised ``TradeEvent has 24 trailing bytes`` on every one and
``decode_pumpswap_fills`` raised ``SellEvent has 49 trailing bytes`` before its documented
payer-delta fallback could run — a real buy or sell would have ended ``fill_decode_failed``.
"""

from __future__ import annotations

import base64
import copy
import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode
from hunter_exchanges.pumpfun.trade_event import LAYOUT_TRAILING_U64
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import LAYOUT_TRAILING_U64 as SELL_LAYOUT_TRAILING_U64
from hunter_exchanges.pumpswap.sell_event import SELL_EVENT_DISCRIMINATOR
from hunter_meme_executor.build import decode_fills
from hunter_meme_executor.pumpswap_build import decode_pumpswap_fills

pytestmark = pytest.mark.unit

ADAPTERS = Path(__file__).resolve().parents[3] / "packages/exchange-adapters/tests/fixtures"


def _tx(folder: str, name: str) -> dict[str, Any]:
    return json.loads((ADAPTERS / folder / name).read_text(encoding="utf-8"))


# -- the curve ---------------------------------------------------------------------------


def test_decode_fills_reads_a_real_post_upgrade_buy_and_reports_the_tail() -> None:
    (fill,) = decode_fills(_tx("pumpfun", "t48e_rpc_tx_buy_3JLToMLjc2mt_raw.json"))
    assert fill.event.is_buy and fill.event.layout == LAYOUT_TRAILING_U64
    assert fill.payer_delta_lamports is not None
    payload = fill.as_json()
    assert payload["event_layout"] == LAYOUT_TRAILING_U64
    assert payload["event_trailing_u64"] == 89_139  # reported, never part of any total
    assert (
        payload["event_buy_total_lamports"] == fill.event.buy_total_cost + fill.network_fee_lamports
    )


def test_decode_fills_reads_a_real_post_upgrade_sell() -> None:
    (fill,) = decode_fills(_tx("pumpfun", "t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json"))
    assert not fill.event.is_buy and fill.event.sol_amount == 263_233_315
    assert fill.as_json()["event_trailing_u64"] == 618_215
    assert fill.event_sell_net_lamports == fill.event.sell_net_proceeds - fill.network_fee_lamports


def test_the_pre_upgrade_fill_json_reports_no_tail() -> None:
    raw = json.loads((ADAPTERS / "pumpfun/t48d_rpc_tx_sell_nonmayhem_raw.json").read_text())
    (fill,) = decode_fills(raw["result"])
    assert fill.as_json()["event_trailing_u64"] is None


def test_an_unknown_trade_event_layout_still_raises_on_the_curve() -> None:
    """No payer-delta fallback on the curve (the FillRecord *is* the event): an unknown
    layout stays loud, so the submitter marks ``fill_decode_failed`` instead of booking."""
    tx = copy.deepcopy(_tx("pumpfun", "t48e_rpc_tx_sell_61x6SRWNuLhg_raw.json"))
    _append_to_event_cpi(tx, b"\x00" * 7, program=None)
    with pytest.raises(ValueError, match="31 trailing bytes"):  # 24 real + 7 unknown
        decode_fills(tx)


# -- PumpSwap ----------------------------------------------------------------------------


def _append_to_event_cpi(tx: dict[str, Any], extra: bytes, *, program: str | None) -> None:
    """Corrupt the event the way a future layout would: bytes after its last field, in the
    inner instruction *and* the log line (the two places the codecs read)."""
    loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
    keys = [
        *cast(list[str], tx["transaction"]["message"]["accountKeys"]),
        *loaded.get("writable", []),
        *loaded.get("readonly", []),
    ]
    for group in tx["meta"]["innerInstructions"]:
        for ix in group["instructions"]:
            data = b58decode(ix["data"])
            if data[:8] == bytes.fromhex("e445a52e51cb9a1d") and (
                program is None or keys[ix["programIdIndex"]] == program
            ):
                ix["data"] = b58encode(data + extra)
    for i, line in enumerate(tx["meta"]["logMessages"]):
        if line.startswith("Program data: "):
            raw = base64.b64decode(line[len("Program data: ") :])
            if raw[:8] in (bytes.fromhex("bddb7fd34ee661ee"), bytes(SELL_EVENT_DISCRIMINATOR)):
                tx["meta"]["logMessages"][i] = (
                    "Program data: " + base64.b64encode(raw + extra).decode()
                )


def test_decode_pumpswap_fills_reads_a_real_post_upgrade_sell() -> None:
    tx = _tx("pumpswap", "t48e_rpc_amm_tx_5mrYZLam93Kd_raw.json")
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.event is not None and fill.event.layout == SELL_LAYOUT_TRAILING_U64
    assert fill.event_error is None
    assert fill.event.user_quote_amount_out == 11_768_877
    payload = fill.as_json()
    assert payload["user_quote_amount_out"] == 11_768_877
    assert payload["event_layout"] == SELL_LAYOUT_TRAILING_U64
    assert payload["event_trailing_u64"] == 9_915_553
    assert payload["event_error"] is None
    # the ledger's truth stays the payer's real delta, whatever the event says
    assert fill.payer_delta_lamports is not None
    assert fill.sell_net_lamports == fill.payer_delta_lamports


def test_an_undecodable_pumpswap_event_falls_back_to_the_payer_delta_as_documented() -> None:
    """The docstring promised it and the code raised first: a landed sell whose event cannot
    be read still yields one record keyed on the payer's real SOL delta, and says why."""
    tx = copy.deepcopy(_tx("pumpswap", "t48e_rpc_amm_tx_5mrYZLam93Kd_raw.json"))
    _append_to_event_cpi(tx, b"\x00" * 3, program=PUMPSWAP_PROGRAM_ID)
    (fill,) = decode_pumpswap_fills(tx)
    assert fill.event is None
    # 49 real + 3 unknown
    assert fill.event_error is not None and "52 trailing bytes" in fill.event_error
    assert fill.payer_delta_lamports is not None
    assert fill.sell_net_lamports == fill.payer_delta_lamports
    payload = fill.as_json()
    assert payload["event_error"] == fill.event_error
    assert payload["user_quote_amount_out"] is None  # never invented from a broken event
    assert payload["sell_net_lamports"] == fill.payer_delta_lamports


def test_an_undecodable_pumpswap_event_without_balances_yields_no_fill() -> None:
    """No event and no delta: nothing to price — never a zero booked as a sale."""
    tx = copy.deepcopy(_tx("pumpswap", "t48e_rpc_amm_tx_5mrYZLam93Kd_raw.json"))
    _append_to_event_cpi(tx, b"\x00" * 3, program=PUMPSWAP_PROGRAM_ID)
    tx["meta"]["preBalances"] = []
    tx["meta"]["postBalances"] = []
    assert decode_pumpswap_fills(tx) == []
