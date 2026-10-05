"""T4.8e: the PumpSwap program redeployed on 2026-10-02 (slot 452654882, 15:47:07Z) emits a
``SellEvent`` with 49 bytes after the 26 fields the T4.29a codec knew: 41 declared by the
GitHub IDL (``virtual_quote_reserves`` i128, ``can_boost`` bool, ``base_supply`` u64,
``holder_rewards_bps`` u64, ``holder_rewards`` u64) and 8 undocumented. 4 of 4 real events
were refused. Until T4.8e this codec had never seen a real fill (T4.29a: "not proven").

Fixtures ``t48e_rpc_amm_tx_*_raw.json``: real ``getTransaction`` results (third parties' sells)
read from the public RPC on 2026-10-05, read-only, no ``sendTransaction``.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpswap.decode import PUMPSWAP_PROGRAM_ID
from hunter_exchanges.pumpswap.sell_event import (
    LAYOUT_IDL_26,
    LAYOUT_TRAILING_U64,
    SELL_EVENT_DISCRIMINATOR,
    decode_sell_event,
    sell_events_from_transaction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpswap"
_BASE_LEN = 392  # discriminator + the 26 fields
_PLACEHOLDER_PUBKEY = "11111111111111111111111111111111"

# ``(fixture, base_amount_in, user_quote_amount_out, virtual_quote_reserves, base_supply, tail)``
_REAL = [
    ("5A1byFyLnuFA", 759_169_807_353, 56_322_412, 17_584_505_353, 714_844_978_907_621, 0),
    ("5mrYZLam93Kd", 70_234_071_736, 11_768_877, 17_556_457_099, 948_214_455_946_100, 9_915_553),
    ("V99doZZTds6x", 692_223_185_883, 205_991_614, 17_584_026_303, 969_872_039_656_625, 359_407),
    ("Yi2iyHP47jiP", 690_133_291, 7_487_012, 17_583_190_767, 972_587_795_372_407, 1_314_647),
]


def _tx(sig12: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"t48e_rpc_amm_tx_{sig12}_raw.json").read_text())


def _event_bytes(tx: dict[str, Any]) -> bytes:
    loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
    keys = [
        *cast(list[str], tx["transaction"]["message"]["accountKeys"]),
        *loaded.get("writable", []),
        *loaded.get("readonly", []),
    ]
    for group in tx["meta"]["innerInstructions"]:
        for ix in group["instructions"]:
            if keys[ix["programIdIndex"]] == PUMPSWAP_PROGRAM_ID:
                data = b58decode(ix["data"])
                if data[8:16] == SELL_EVENT_DISCRIMINATOR:
                    return data[8:]
    raise AssertionError("no SellEvent")


def _base_body() -> bytes:
    body = bytearray(SELL_EVENT_DISCRIMINATOR)
    body += struct.pack("<q", 1_789_000_000)
    for value in (1_000_000_000, 18_000, 5, 6, 7, 8, 19_012, 20, 39, 5, 10, 18_973, 18_953):
        body += struct.pack("<Q", value)
    for _ in range(7):
        body += b58decode(_PLACEHOLDER_PUBKEY)
    for value in (5, 10, 0, 0, 0, 0):
        body += struct.pack("<Q", value)
    assert len(body) == _BASE_LEN
    return bytes(body)


def _extension(*, vq: int = -3, can_boost: int = 1, tail: int = 7) -> bytes:
    return (
        vq.to_bytes(16, "little", signed=True)
        + bytes([can_boost])
        + struct.pack("<QQQ", 10**15, 25, 1234)
        + struct.pack("<Q", tail)
    )


@pytest.mark.parametrize(("sig", "base_in", "user_out", "vq", "supply", "tail"), _REAL)
def test_real_post_upgrade_sell_events_decode_with_the_declared_extension_and_the_tail(
    sig: str, base_in: int, user_out: int, vq: int, supply: int, tail: int
) -> None:
    tx = _tx(sig)
    raw = _event_bytes(tx)
    assert len(raw) == 441  # 4 of 4 real bodies: 392 + 41 declared + 8 undocumented
    (event,) = sell_events_from_transaction(tx)
    assert event.layout == LAYOUT_TRAILING_U64
    assert (event.base_amount_in, event.user_quote_amount_out) == (base_in, user_out)
    assert event.net_proceeds == user_out
    assert event.virtual_quote_reserves == vq
    assert event.can_boost is True
    assert event.base_supply == supply
    assert event.holder_rewards_basis_points == 0 and event.holder_rewards == 0
    assert event.trailing_u64 == tail  # a real ``0`` is a reading, not an absence
    assert event.timestamp == tx["blockTime"]


def test_the_tail_and_the_extension_never_move_the_money_arithmetic() -> None:
    base = _base_body()
    plain = decode_sell_event(base)
    a = decode_sell_event(base + _extension(tail=0))
    b = decode_sell_event(base + _extension(tail=39_743_440, vq=10**20))
    assert a.net_proceeds == b.net_proceeds == plain.net_proceeds == 18_953
    assert (a.lp_fee, a.protocol_fee, a.coin_creator_fee) == (
        plain.lp_fee,
        10,
        plain.coin_creator_fee,
    )
    assert b.virtual_quote_reserves == 10**20  # i128: does not fit 64 bits
    assert decode_sell_event(base + _extension(vq=-(2**100))).virtual_quote_reserves == -(2**100)


def test_the_older_26_field_layout_still_decodes_and_reports_no_extension() -> None:
    event = decode_sell_event(_base_body())
    assert event.layout == LAYOUT_IDL_26
    assert event.virtual_quote_reserves is None and event.can_boost is None
    assert event.base_supply is None and event.trailing_u64 is None
    assert event.holder_rewards is None and event.holder_rewards_basis_points is None


@pytest.mark.parametrize("extra", [1, 8, 16, 40, 41, 48, 50, 57, 64])
def test_any_other_trailing_length_is_still_refused(extra: int) -> None:
    """Only 0 (T4.29a) and 49 (41 declared + 8, seen on chain) are layouts. 41 alone — the
    IDL's extension without the unnamed tail — was never seen and stays refused: the payer-
    delta fallback of ``decode_pumpswap_fills`` carries such a fill instead."""
    with pytest.raises(ValueError, match=f"{extra} trailing bytes"):
        decode_sell_event(_base_body() + b"\x00" * extra)


def test_a_can_boost_that_is_not_a_boolean_is_refused() -> None:
    with pytest.raises(ValueError, match="boolean"):
        decode_sell_event(_base_body() + _extension(can_boost=2))
