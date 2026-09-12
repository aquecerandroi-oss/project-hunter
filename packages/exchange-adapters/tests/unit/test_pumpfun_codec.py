"""Pure Solana primitives: base58, PDAs (with the ed25519 check), ATAs, legacy messages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from hypothesis import given
from hypothesis import strategies as st

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.global_state import GLOBAL_ACCOUNT_ADDRESS, decode_global_account
from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_2022_PROGRAM_ID,
    AccountMeta,
    Instruction,
    _is_on_curve,  # pyright: ignore[reportPrivateUsage]
    associated_token_address,
    b58decode,
    b58encode,
    compile_message,
    decompile_message,
    deserialize_message,
    find_program_address,
    pubkey_bytes,
    serialize_message,
    serialize_transaction,
    set_compute_unit_limit,
    set_compute_unit_price,
)
from hunter_exchanges.pumpfun.tx import (
    PUMP_FEE_PROGRAM_ID,
    bonding_curve_address,
    creator_vault_address,
    pump_pdas,
    user_volume_accumulator_address,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"


@given(st.binary(min_size=0, max_size=80))
def test_base58_roundtrip(raw: bytes) -> None:
    assert b58decode(b58encode(raw)) == raw


def test_base58_rejects_invalid_characters() -> None:
    with pytest.raises(ValueError):
        b58decode("0OIl")


def test_keypair_pubkeys_are_on_curve_and_pdas_are_not() -> None:
    for _ in range(20):
        pub = (
            Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        )
        assert _is_on_curve(pub)
    assert _is_on_curve(pubkey_bytes("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"))  # a signer
    assert not _is_on_curve(pubkey_bytes(GLOBAL_ACCOUNT_ADDRESS))


def test_known_pdas_match_the_chain() -> None:
    """Every address here was read from a confirmed mainnet transaction (T4.8 fixtures)."""
    pdas = pump_pdas()
    assert pdas.global_account == GLOBAL_ACCOUNT_ADDRESS
    assert pdas.event_authority == "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1"
    assert pdas.fee_config == "8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt"
    assert pdas.global_volume_accumulator == "Hq2wp8uJ9jCPsYgNHex8RtqdvMPfVGoYwjvF1ATiwn2Y"
    assert bonding_curve_address(MINT) == "ChDRd2ZZ1NTFZ2sx6PAWH9iaL7wv3jSdnCFMzSBxNCaS"
    curve = bonding_curve_address(MINT)
    assert (
        associated_token_address(curve, MINT, token_program=TOKEN_2022_PROGRAM_ID)
        == "FkqtrypdaSbVttRMBhSQMKENNPSEpQzcFoFE6Mg1WpCm"
    )
    assert (
        associated_token_address(
            "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", MINT, token_program=TOKEN_2022_PROGRAM_ID
        )
        == "FrNRJjMoV2QKy7JZmFppVkYb2kYoxQJD5U43sJPjxo3k"
    )
    assert (
        creator_vault_address("B4tp4tfJU9kWBdYdMmW6yAxgHfYNPjfchaT4abCpkyJZ")
        == "EbEQsXX4jzggNbYWva4zxX2MWHxiavtTm5NqjLGcUpWu"
    )
    assert (
        user_volume_accumulator_address("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d")
        == "BYeCRHRKthghbs7DGwjBGgZcfz1GfbvCx5QnMBrkQM9D"
    )
    # the fee-config PDA lives under the *fee* program, seeded with the pump program id
    assert (
        find_program_address([b"fee_config", pubkey_bytes(PUMP_PROGRAM_ID)], PUMP_FEE_PROGRAM_ID)[0]
        == pdas.fee_config
    )


def test_global_account_decodes_and_matches_documented_lists() -> None:
    raw: dict[str, Any] = json.loads((FIXTURES / "rpc_global_account_raw.json").read_text())
    value = raw["result"]["value"]
    g = decode_global_account(value["data"][0], owner=value["owner"])
    assert g.fee_recipient == "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV"
    assert len(g.normal_fee_recipients) == 8 and len(g.mayhem_fee_recipients) == 8
    assert len(g.buyback_fee_recipients) == 8
    assert g.reserved_fee_recipient == "GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS"
    assert g.whitelist_pda == "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"  # the Mayhem agent
    assert g.initial_virtual_sol_reserves == 30_000_000_000
    assert g.fee_basis_points == 95 and g.creator_fee_basis_points == 5
    assert "EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL" in g.buyback_fee_recipients
    with pytest.raises(MalformedMessage):
        decode_global_account(value["data"][0], owner="11111111111111111111111111111111")
    with pytest.raises(MalformedMessage):
        decode_global_account(value["data"][0][:40], owner=value["owner"])


def _sample_instructions() -> list[Instruction]:
    return [
        set_compute_unit_limit(400_000),
        set_compute_unit_price(10_000),
        Instruction(
            PUMP_PROGRAM_ID,
            (
                AccountMeta(GLOBAL_ACCOUNT_ADDRESS, False, False),
                AccountMeta("62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV", False, True),
                AccountMeta("sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d", True, True),
                AccountMeta(GLOBAL_ACCOUNT_ADDRESS, False, False),  # repeated key, deduped
            ),
            b"\x66\x06\x3d\x12\x01\xda\xeb\xea" + b"\x01" * 16,
        ),
    ]


def test_message_compile_serialize_deserialize_roundtrip() -> None:
    payer = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"
    message = compile_message(
        payer, _sample_instructions(), "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ"
    )
    assert message.account_keys[0] == payer and message.num_required_signatures == 1
    raw = serialize_message(message)
    assert deserialize_message(raw) == message
    decompiled = decompile_message(message)
    assert [ix.data for ix in decompiled] == [ix.data for ix in _sample_instructions()]
    assert decompiled[2].accounts[2].is_signer and decompiled[2].accounts[1].is_writable
    assert not decompiled[2].accounts[0].is_writable
    tx = serialize_transaction([b"\0" * 64], raw)
    assert tx[0] == 1 and tx[65:] == raw


def test_versioned_message_is_refused() -> None:
    site_tx: dict[str, Any] = json.loads((FIXTURES / "swap_build_probe4_raw.txt").read_text())
    raw = b58decode(site_tx["transaction"])
    message = raw[1 + 64 :]
    assert message[0] & 0x80, "the site's transaction is v0 (address lookup table)"
    with pytest.raises(ValueError, match="versioned"):
        deserialize_message(message)


def test_truncated_or_dangling_messages_are_refused() -> None:
    message = compile_message(
        "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d",
        _sample_instructions(),
        "BQ8v5pyUzayNkgPghSBd36pVgG14SGLExT5kwWkmYZWJ",
    )
    raw = serialize_message(message)
    with pytest.raises((ValueError, IndexError)):
        deserialize_message(raw[:-5])
    with pytest.raises(ValueError, match="trailing"):
        deserialize_message(raw + b"\x00")
    with pytest.raises(ValueError):
        deserialize_message(b"")


def test_compute_budget_bounds() -> None:
    with pytest.raises(ValueError):
        set_compute_unit_limit(0)
    with pytest.raises(ValueError):
        set_compute_unit_limit(1_400_001)
    with pytest.raises(ValueError):
        set_compute_unit_price(-1)
    assert set_compute_unit_limit(400_000).data == bytes.fromhex("02801a0600")
    assert set_compute_unit_price(10_000).data == bytes.fromhex("031027000000000000")
