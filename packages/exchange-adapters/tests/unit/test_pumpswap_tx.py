"""``build_pumpswap_sell_instruction``/``build_sell_message`` — accounts (IDL
order, 21), discriminator (golden bytes from the on-chain IDL) and args, plus
the WSOL unwrap pair and the verifier's round trip and refusals (T4.29a).

The pool fixture is the real, live-read ``F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ``
(mint ``5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump``); PDAs
(``event_authority``, ``fee_config``, ``coin_creator_vault_*``) were all
confirmed against real accounts in ``pdas.py``'s module docstring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    AccountMeta,
    Instruction,
    Message,
    compile_message,
    deserialize_message,
    serialize_message,
    set_compute_unit_limit,
    set_compute_unit_price,
)
from hunter_exchanges.pumpswap.decode import decode_pool_account
from hunter_exchanges.pumpswap.pdas import fee_config_address
from hunter_exchanges.pumpswap.tx import (
    SELL_ACCOUNT_NAMES,
    SELL_DISCRIMINATOR,
    PumpSwapSellIntent,
    build_close_wsol_instruction,
    build_create_wsol_ata_instruction,
    build_pumpswap_sell_instruction,
    build_sell_message,
)
from hunter_exchanges.pumpswap.verify import UnverifiedTransaction, verify_pumpswap_sell_message

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpswap"
POOL_ADDRESS = "F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ"
USER = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
PROTOCOL_FEE_RECIPIENT = "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV"
BLOCKHASH = "7Pptc9XnPvGCz2SExsdbLzYAWCXbGmYyewGefDCVU4A6"


def _pool():
    raw = json.loads((FIXTURES / "t429a_rpc_pools_raw.json").read_text(encoding="utf-8"))
    value = raw["result"]["value"][2]
    return decode_pool_account(value["data"][0], owner=value["owner"])


def _intent() -> PumpSwapSellIntent:
    return PumpSwapSellIntent(
        pool_address=POOL_ADDRESS,
        pool=_pool(),
        user=USER,
        base_token_program=TOKEN_PROGRAM_ID,
        base_amount_in=1_000_000_000,
        min_quote_amount_out=18_000,
        protocol_fee_recipient=PROTOCOL_FEE_RECIPIENT,
    )


def test_sell_instruction_discriminator_matches_onchain_idl() -> None:
    assert SELL_DISCRIMINATOR == bytes([51, 230, 133, 164, 1, 127, 131, 173])
    assert SELL_DISCRIMINATOR.hex() == "33e685a4017f83ad"


def test_sell_instruction_has_21_accounts_in_idl_order() -> None:
    ix = build_pumpswap_sell_instruction(_intent())
    assert len(ix.accounts) == 21 == len(SELL_ACCOUNT_NAMES)
    assert ix.accounts[0].pubkey == POOL_ADDRESS
    assert ix.accounts[0].is_writable is True and ix.accounts[0].is_signer is False
    assert ix.accounts[1].pubkey == USER
    assert ix.accounts[1].is_signer is True and ix.accounts[1].is_writable is True
    assert ix.accounts[SELL_ACCOUNT_NAMES.index("fee_config")].pubkey == fee_config_address()
    assert ix.accounts[SELL_ACCOUNT_NAMES.index("fee_program")].pubkey == (
        "pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
    )


def test_sell_instruction_args_encode_amounts() -> None:
    ix = build_pumpswap_sell_instruction(_intent())
    assert ix.data[:8] == SELL_DISCRIMINATOR
    assert len(ix.data) == 24
    base_amount = int.from_bytes(ix.data[8:16], "little")
    min_out = int.from_bytes(ix.data[16:24], "little")
    assert base_amount == 1_000_000_000
    assert min_out == 18_000


def test_sell_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError, match="base_amount_in"):
        PumpSwapSellIntent(
            pool_address=POOL_ADDRESS,
            pool=_pool(),
            user=USER,
            base_token_program=TOKEN_PROGRAM_ID,
            base_amount_in=0,
            min_quote_amount_out=1,
            protocol_fee_recipient=PROTOCOL_FEE_RECIPIENT,
        )


def test_create_and_close_wsol_instructions_target_the_same_ata() -> None:
    create_ix = build_create_wsol_ata_instruction(payer=USER, owner=USER)
    close_ix = build_close_wsol_instruction(owner=USER)
    wsol_ata_from_create = create_ix.accounts[1].pubkey
    wsol_ata_from_close = close_ix.accounts[0].pubkey
    assert wsol_ata_from_create == wsol_ata_from_close
    assert close_ix.data == b"\x09"
    assert close_ix.accounts[1].pubkey == USER  # destination of reclaimed lamports
    assert close_ix.accounts[2].is_signer is True


def test_build_sell_message_round_trips_through_verifier() -> None:
    intent = _intent()
    message = build_sell_message(
        intent,
        payer=USER,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=120_000,
        compute_unit_price_micro_lamports=5_000,
        create_wsol_ata=True,
    )
    raw = serialize_message(message)
    verified = verify_pumpswap_sell_message(
        raw,
        intent,
        compute_unit_limit_cap=200_000,
        compute_unit_price_cap_micro_lamports=10_000,
        expected_blockhash=BLOCKHASH,
    )
    assert verified.compute_unit_limit == 120_000
    assert verified.creates_wsol_ata is True
    assert deserialize_message(raw) == message


def test_verifier_refuses_tampered_amount() -> None:
    intent = _intent()
    message = build_sell_message(
        intent,
        payer=USER,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=120_000,
        compute_unit_price_micro_lamports=5_000,
        create_wsol_ata=True,
    )
    raw = bytearray(serialize_message(message))
    # Flip a byte inside the sell instruction's data (min_quote_amount_out).
    needle = SELL_DISCRIMINATOR
    idx = bytes(raw).index(needle)
    raw[idx + 8] ^= 0xFF
    with pytest.raises(UnverifiedTransaction, match="message_bytes_differ"):
        verify_pumpswap_sell_message(
            bytes(raw),
            intent,
            compute_unit_limit_cap=200_000,
            compute_unit_price_cap_micro_lamports=10_000,
            expected_blockhash=BLOCKHASH,
        )


def test_verifier_refuses_wrong_signer() -> None:
    intent = _intent()
    message = build_sell_message(
        intent,
        payer=USER,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=120_000,
        compute_unit_price_micro_lamports=5_000,
        create_wsol_ata=True,
    )
    raw = serialize_message(message)
    other_intent = PumpSwapSellIntent(
        pool_address=POOL_ADDRESS,
        pool=_pool(),
        user="11111111111111111111111111111112",
        base_token_program=TOKEN_PROGRAM_ID,
        base_amount_in=1_000_000_000,
        min_quote_amount_out=18_000,
        protocol_fee_recipient=PROTOCOL_FEE_RECIPIENT,
    )
    with pytest.raises(UnverifiedTransaction, match="signer_is_not_our_wallet"):
        verify_pumpswap_sell_message(
            raw,
            other_intent,
            compute_unit_limit_cap=200_000,
            compute_unit_price_cap_micro_lamports=10_000,
        )


def test_verifier_refuses_foreign_program() -> None:
    intent = _intent()
    foreign = Instruction(
        "6Vo3245eszAb5wuqEMw8mGdbfRUdKbHhDHP5LcaGuTAB",
        (AccountMeta(intent.user, True, True),),
        b"\x01",
    )
    message = compile_message(
        USER,
        [
            set_compute_unit_limit(120_000),
            set_compute_unit_price(5_000),
            build_pumpswap_sell_instruction(intent),
            build_close_wsol_instruction(owner=USER),
            foreign,
        ],
        BLOCKHASH,
    )
    with pytest.raises(UnverifiedTransaction, match="program_not_allowed"):
        verify_pumpswap_sell_message(
            serialize_message(message),
            intent,
            compute_unit_limit_cap=200_000,
            compute_unit_price_cap_micro_lamports=10_000,
        )


def test_verifier_refuses_missing_close_instruction() -> None:
    intent = _intent()
    message = build_sell_message(
        intent,
        payer=USER,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=120_000,
        compute_unit_price_micro_lamports=5_000,
        create_wsol_ata=False,
    )
    decoded = deserialize_message(serialize_message(message))
    broken = Message(
        decoded.num_required_signatures,
        decoded.num_readonly_signed,
        decoded.num_readonly_unsigned,
        decoded.account_keys,
        decoded.recent_blockhash,
        decoded.instructions[:-1],
    )
    with pytest.raises(UnverifiedTransaction, match="message_bytes_differ"):
        verify_pumpswap_sell_message(
            serialize_message(broken),
            intent,
            compute_unit_limit_cap=200_000,
            compute_unit_price_cap_micro_lamports=10_000,
        )
