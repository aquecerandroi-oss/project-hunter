"""``decode_sell_event`` on a synthetic ``SellEvent`` body built field-by-field
from the on-chain IDL's declared order (T4.29a). **Not checked against a real
fill** — no wallet exists in this task to produce one
(``.claude/state/notes-T4.29a.md`` "not proven"); this only proves the codec
round-trips the layout the IDL declares, refuses truncation/trailing bytes
and a wrong discriminator, same discipline as
``test_pumpfun_trade_event.py``.
"""

from __future__ import annotations

import struct
from typing import Any

import pytest

from hunter_exchanges.pumpfun.solana_codec import b58decode
from hunter_exchanges.pumpfun.trade_event import EVENT_CPI_TAG
from hunter_exchanges.pumpswap.sell_event import (
    SELL_EVENT_DISCRIMINATOR,
    decode_sell_event,
    sell_events_from_transaction,
)

_PLACEHOLDER_PUBKEY = "11111111111111111111111111111111"


def _synthetic_body(*, trailing: bytes = b"") -> bytes:
    body = bytearray(SELL_EVENT_DISCRIMINATOR)
    body += struct.pack("<q", 1_789_000_000)
    for value in (1_000_000_000, 18_000, 5, 6, 7, 8, 19_012, 20, 39, 5, 10, 18_973, 18_953):
        body += struct.pack("<Q", value)
    for _ in range(7):
        body += b58decode(_PLACEHOLDER_PUBKEY)
    for value in (5, 10, 0, 0, 0, 0):
        body += struct.pack("<Q", value)
    return bytes(body) + trailing


def test_decodes_all_26_fields() -> None:
    event = decode_sell_event(_synthetic_body())
    assert event.base_amount_in == 1_000_000_000
    assert event.quote_amount_out == 19_012
    assert event.lp_fee == 39
    assert event.protocol_fee == 10
    assert event.coin_creator_fee == 10
    assert event.user_quote_amount_out == 18_953
    assert event.net_proceeds == 18_953


def test_accepts_event_cpi_tag_prefix() -> None:
    tagged = EVENT_CPI_TAG + _synthetic_body()
    assert decode_sell_event(tagged) == decode_sell_event(_synthetic_body())


def test_wrong_discriminator_rejected() -> None:
    body = bytearray(_synthetic_body())
    body[0] ^= 0xFF
    with pytest.raises(ValueError, match="discriminator"):
        decode_sell_event(bytes(body))


def test_truncated_body_rejected() -> None:
    with pytest.raises(ValueError, match="truncated"):
        decode_sell_event(_synthetic_body()[:100])


def test_trailing_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="trailing"):
        decode_sell_event(_synthetic_body(trailing=b"\x00"))


def test_sell_events_from_transaction_empty_on_failed_tx() -> None:
    tx: dict[str, Any] = {
        "meta": {"err": {"InstructionError": [0, "Custom"]}},
        "transaction": {"message": {}},
    }
    assert sell_events_from_transaction(tx) == ()


def test_sell_events_from_transaction_empty_without_inner_instructions() -> None:
    tx: dict[str, Any] = {"meta": {"err": None}, "transaction": {"message": {"accountKeys": []}}}
    assert sell_events_from_transaction(tx) == ()
