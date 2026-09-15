"""``BondingCurve`` decoding, including the three fields past ``quote_mint``
this package never looked at before T4.8c: ``creator_fee_bps``,
``can_edit_creator_fee``, ``is_holder_reward`` — the on-chain byte behind
M-P34/KB-0096 (``docs/PUMPFUN-ONCHAIN.md`` §6d).

Both real fixtures here are 2026-09-15 reads (``.claude/state/notes-T4.8c.md``
§1): ``t48c_rpc_bonding_curve_hr_raw.json`` (mint ``7qSzmCMq…``,
``frontend-api-v3.pump.fun`` reports ``is_holder_reward: true`` for it) and
``t48c_rpc_bonding_curve_control_raw.json`` (mint ``Czv4odPi…``, same listing,
``is_holder_reward: false``, no Mayhem). Both accounts are 151 bytes — the
extended layout was **not** introduced by the 2026-09-15 (or the 2026-09-12)
deploy: ``t42f_rpc_curves_batch1_raw.json`` (captured 2026-09-12, T4.2f)
already has 45/100 accounts at 151 bytes, one with a non-zero
``creator_fee_bps``.
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import (
    LAYOUT_LEGACY,
    LAYOUT_WITH_HOLDER_REWARD,
    decode_bonding_curve_account,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _value(name: str) -> dict[str, str]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return raw["result"]["value"]


def test_legacy_124_byte_account_decodes_with_defaults() -> None:
    value = _value("rpc_get_account_info_bonding_curve_raw.json")
    assert len(base64.b64decode(value["data"][0])) == 124
    decoded = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
    assert decoded.layout == LAYOUT_LEGACY
    assert decoded.creator_fee_bps == 0
    assert decoded.can_edit_creator_fee is False
    assert decoded.is_holder_reward is False


def test_holder_reward_mint_reads_true_on_chain() -> None:
    value = _value("t48c_rpc_bonding_curve_hr_raw.json")
    raw = base64.b64decode(value["data"][0])
    assert len(raw) == 151
    decoded = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
    assert decoded.layout == LAYOUT_WITH_HOLDER_REWARD
    assert decoded.is_holder_reward is True
    assert decoded.creator_fee_bps == 0 and decoded.can_edit_creator_fee is False
    assert decoded.quote_mint == "11111111111111111111111111111111"
    # The 26 bytes past the three fields are reserved and unparsed, not asserted here.


def test_control_mint_from_the_same_listing_reads_false() -> None:
    value = _value("t48c_rpc_bonding_curve_control_raw.json")
    decoded = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
    assert decoded.layout == LAYOUT_WITH_HOLDER_REWARD
    assert decoded.is_holder_reward is False


def test_old_idle_mints_from_t48_and_t48b_are_also_151_bytes_now() -> None:
    """No migration event was established (T4.8c §concerns): coins idle since
    2026-09-12, re-read on 2026-09-15, are already at the extended layout."""
    for name in (
        "t48c_rpc_bonding_curve_t48_cashback_raw.json",
        "t48c_rpc_bonding_curve_t48b_mayhem_raw.json",
    ):
        value = _value(name)
        decoded = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
        assert decoded.layout == LAYOUT_WITH_HOLDER_REWARD
        assert decoded.is_holder_reward is False


def test_a_t42f_capture_from_2026_09_12_already_had_the_extended_layout() -> None:
    """The population sampled well before either 2026-09 deploy was already
    mixed (45/100 at 151 bytes) — this package's blindness, not new state."""
    batch = json.loads((FIXTURES / "t42f_rpc_curves_batch1_raw.json").read_text())
    values = batch["result"]["value"]
    legacy = extended = 0
    nonzero_creator_fee = 0
    for value in values:
        if value is None:
            continue
        decoded = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
        if decoded.layout == LAYOUT_WITH_HOLDER_REWARD:
            extended += 1
            if decoded.creator_fee_bps:
                nonzero_creator_fee += 1
        else:
            legacy += 1
    assert extended == 45 and nonzero_creator_fee == 1


def test_invalid_boolean_in_the_extended_fields_is_refused() -> None:
    value = _value("t48c_rpc_bonding_curve_hr_raw.json")
    raw = bytearray(base64.b64decode(value["data"][0]))
    raw[124] = 7  # is_holder_reward must be 0 or 1
    corrupted = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(MalformedMessage, match="boolean"):
        decode_bonding_curve_account(corrupted, owner=value["owner"])


def test_a_pad_of_one_to_nine_trailing_bytes_is_legacy_not_malformed() -> None:
    """Too short for the three fields (< 10 bytes) is a real, observed shape
    (T4.0's 9-byte reserved tail) — decoded as legacy, never refused."""
    value = _value("t48c_rpc_bonding_curve_control_raw.json")
    raw = base64.b64decode(value["data"][0])[:120]  # 115 + 5 trailing bytes
    truncated = base64.b64encode(raw).decode()
    decoded = decode_bonding_curve_account(truncated, owner=value["owner"])
    assert decoded.layout == LAYOUT_LEGACY
    assert decoded.is_holder_reward is False


def test_creator_fee_bps_is_read_as_u64_little_endian() -> None:
    value = _value("t48c_rpc_bonding_curve_hr_raw.json")
    raw = bytearray(base64.b64decode(value["data"][0]))
    struct.pack_into("<Q", raw, 115, 42)
    patched = base64.b64encode(bytes(raw)).decode()
    decoded = decode_bonding_curve_account(patched, owner=value["owner"])
    assert decoded.creator_fee_bps == 42
