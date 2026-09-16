"""``GlobalConfig``/``Pool`` decode against 3 real, live-read migrated pools
(T4.29a, ``.claude/state/notes-T4.29a.md``): mints
``9tiUg9bDHpEgE3rQU8kmdMJMvMfwM81ph6WuyTapump``,
``DHcQCSZ2U8QTjNWWwyuqfJbBTLCZyvtFkSeYhEYGpump`` (Mayhem),
``5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump`` — the last one is the same
mint ``hunter_exchanges.pumpfun`` already has a REST fixture for
(``frontend_api_v3_coin_graduated_raw.json``), so this test also cross-checks
the on-chain ``pool_address`` against the REST ``pump_swap_pool`` field.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpswap.decode import (
    LAYOUT_BASE,
    LAYOUT_WITH_VIRTUAL_QUOTE_RESERVES,
    PUMPSWAP_PROGRAM_ID,
    WSOL_MINT,
    decode_global_config,
    decode_pool_account,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpswap"
PUMPFUN_FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _pool_values() -> list[dict[str, Any]]:
    raw = json.loads((FIXTURES / "t429a_rpc_pools_raw.json").read_text(encoding="utf-8"))
    return raw["result"]["value"]


def test_three_real_pools_decode_and_round_trip_length() -> None:
    values = _pool_values()
    assert len(values) == 3
    for value in values:
        assert len(base64.b64decode(value["data"][0])) == 301
        pool = decode_pool_account(value["data"][0], owner=value["owner"])
        assert pool.layout == LAYOUT_WITH_VIRTUAL_QUOTE_RESERVES
        assert pool.quote_mint == WSOL_MINT
        assert pool.index == 0


def test_pool_mayhem_flag_matches_known_mint() -> None:
    values = _pool_values()
    mayhem_pool = decode_pool_account(values[1]["data"][0], owner=values[1]["owner"])
    non_mayhem_pool = decode_pool_account(values[0]["data"][0], owner=values[0]["owner"])
    assert mayhem_pool.is_mayhem_mode is True
    assert non_mayhem_pool.is_mayhem_mode is False


def test_virtual_quote_reserves_is_not_always_zero() -> None:
    """Corrects a stale reading in ``docs/PUMPFUN-ONCHAIN.md`` §2.2 — two of
    three pools read live in this task carry a non-zero value."""
    values = _pool_values()
    vqrs = [
        decode_pool_account(v["data"][0], owner=v["owner"]).virtual_quote_reserves for v in values
    ]
    assert vqrs == [17_584_505_289, 0, 17_584_505_291]


def test_graduated_fixture_pool_address_matches_pumpfun_rest_fixture() -> None:
    """Cross-package check: the pool this fixture decodes is the same
    ``pump_swap_pool`` the ``pumpfun`` package's REST fixture reports for the
    same mint."""
    coin = json.loads(
        (PUMPFUN_FIXTURES / "frontend_api_v3_coin_graduated_raw.json").read_text(encoding="utf-8")
    )
    values = _pool_values()
    f5mk = values[2]
    assert coin["pump_swap_pool"] == "F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ"
    pool = decode_pool_account(f5mk["data"][0], owner=f5mk["owner"])
    assert pool.base_mint == coin["mint"]


def test_wrong_owner_is_malformed() -> None:
    values = _pool_values()
    value = values[0]
    with pytest.raises(MalformedMessage, match="not the PumpSwap program"):
        decode_pool_account(value["data"][0], owner="11111111111111111111111111111111")


def test_short_account_is_malformed() -> None:
    values = _pool_values()
    value = values[0]
    truncated = base64.b64encode(base64.b64decode(value["data"][0])[:100]).decode()
    with pytest.raises(MalformedMessage, match="too short"):
        decode_pool_account(truncated, owner=value["owner"])


def test_wrong_discriminator_is_malformed() -> None:
    values = _pool_values()
    value = values[0]
    raw = bytearray(base64.b64decode(value["data"][0]))
    raw[0] ^= 0xFF
    corrupted = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(MalformedMessage, match="discriminator"):
        decode_pool_account(corrupted, owner=value["owner"])


def test_invalid_boolean_is_malformed() -> None:
    values = _pool_values()
    value = values[0]
    raw = bytearray(base64.b64decode(value["data"][0]))
    # is_mayhem_mode is byte offset 243 (8 + 1 + 2 + 32*7)
    raw[243] = 7
    corrupted = base64.b64encode(bytes(raw)).decode()
    with pytest.raises(MalformedMessage, match="boolean"):
        decode_pool_account(corrupted, owner=value["owner"])


def test_legacy_layout_without_extended_fields_defaults() -> None:
    values = _pool_values()
    value = values[0]
    raw = base64.b64decode(value["data"][0])[:245]
    truncated = base64.b64encode(raw).decode()
    pool = decode_pool_account(truncated, owner=value["owner"])
    assert pool.layout == LAYOUT_BASE
    assert pool.virtual_quote_reserves == 0
    assert pool.is_holder_reward is False


def test_global_config_decodes_live_fees_and_recipients() -> None:
    raw = json.loads(
        (FIXTURES / "t429a_rpc_globalconfig_tokens_raw.json").read_text(encoding="utf-8")
    )
    value = raw["result"]["value"][0]
    config = decode_global_config(value["data"][0], owner=value["owner"])
    assert config.lp_fee_basis_points == 20
    assert config.protocol_fee_basis_points == 5
    assert config.coin_creator_fee_basis_points == 5
    assert config.total_fee_basis_points == 30
    assert len(config.protocol_fee_recipients) == 8
    assert config.protocol_fee_recipients[0] == "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV"


def test_global_config_wrong_owner_is_malformed() -> None:
    raw = json.loads(
        (FIXTURES / "t429a_rpc_globalconfig_tokens_raw.json").read_text(encoding="utf-8")
    )
    value = raw["result"]["value"][0]
    with pytest.raises(MalformedMessage, match="not the PumpSwap program"):
        decode_global_config(value["data"][0], owner="11111111111111111111111111111111")


def test_pumpswap_program_id_matches_pool_owner() -> None:
    values = _pool_values()
    assert all(v["owner"] == PUMPSWAP_PROGRAM_ID for v in values)
