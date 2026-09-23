"""T4.54b fix A — the instruction-by-instruction verifier against the REAL
unsigned transaction Jupiter built for this wallet's public key (18/09/2026,
``fixtures/jupiter_swap_usdc_to_sol_real.json``; nothing was signed or sent)
and against hostile variants of it, each refused by name.

Pure: no network, no database, no signer. The capture reaches its
``CreateIdempotent`` mint through an address lookup table (account index 18),
so since T4.83 every call hands the verifier the **resolved** key list the
caller would have read from the chain (``_keys``); the table's own contents
were never captured, so the snapshot is synthetic with WSOL at slot 11 —
``test_treasury_verify_alt.py`` is where the resolution itself is pinned."""

from __future__ import annotations

import base64
import json
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from hunter_exchanges.jupiter import decode_versioned_transaction
from hunter_exchanges.jupiter.versioned_tx import (
    VersionedCompiledInstruction,
    VersionedMessage,
)
from hunter_exchanges.pumpfun.solana_codec import (
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
    u64_le,
)
from hunter_meme_executor.spot_alt import LookupTable, resolved_account_keys
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID, USDC_MINT, TreasurySwapRefused
from hunter_meme_executor.treasury_verify import (
    MAX_PRIORITY_FEE_LAMPORTS,
    ROUTE_DISCRIMINATOR,
    SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR,
    SwapIntent,
    verify_swap_transaction,
)

from .spot_tx_fixtures import filler, table_addresses

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
WSOL = "So11111111111111111111111111111111111111112"
USDC_ATA = associated_token_address(WALLET, USDC_MINT, token_program=TOKEN_PROGRAM_ID)
WSOL_ATA = associated_token_address(WALLET, WSOL, token_program=TOKEN_PROGRAM_ID)
INTENT = SwapIntent(
    wallet=WALLET, usdc_atoms=1_000_000, min_quoted_out_lamports=9_487_602, max_slippage_bps=50
)
ROUTE_IX = 3  # position of the JUP6 instruction in the real capture
MINT_SLOT = 11  # the table slot the ``CreateIdempotent`` mint (index 18) resolves to
_TAIL = struct.Struct("<QQHB")


def _real_message() -> VersionedMessage:
    payload = json.loads((FIXTURES / "jupiter_swap_usdc_to_sol_real.json").read_text("utf-8"))
    return decode_versioned_transaction(base64.b64decode(payload["swapTransaction"])).message


def _keys(message: VersionedMessage) -> tuple[str, ...]:
    """The resolved account keys of ``message`` — what ``treasury_send`` reads
    from the chain before verifying (T4.83)."""
    if not message.address_table_lookups:
        return message.static_account_keys
    address = message.address_table_lookups[0].account_key
    table = LookupTable(address, table_addresses(256, {MINT_SLOT: WSOL}))
    return resolved_account_keys(message, {address: table})


def _with(message: VersionedMessage, index: int, **fields: object) -> VersionedMessage:
    ixs = list(message.instructions)
    ixs[index] = replace(ixs[index], **fields)  # type: ignore[arg-type]
    return replace(message, instructions=tuple(ixs))


def _plus(message: VersionedMessage, ix: VersionedCompiledInstruction) -> VersionedMessage:
    return replace(message, instructions=(*message.instructions, ix))


def _retail(data: bytes, *, in_amount: int, out: int, slippage: int, fee: int = 0) -> bytes:
    return data[: -_TAIL.size] + _TAIL.pack(in_amount, out, slippage, fee)


def _refused(message: VersionedMessage, intent: SwapIntent = INTENT) -> str:
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_swap_transaction(message, intent=intent, account_keys=_keys(message))
    return excinfo.value.reason


# -------------------------------------------------------------- the real one
def test_the_real_jupiter_transaction_verifies_and_is_decoded_by_name() -> None:
    message = _real_message()
    keys = message.static_account_keys
    assert keys[0] == WALLET and keys[1] == WSOL_ATA and keys[3] == USDC_ATA
    verified = verify_swap_transaction(message, intent=INTENT, account_keys=_keys(message))
    assert verified.route_kind == "route"
    assert verified.in_amount == 1_000_000
    assert verified.quoted_out_amount == 9_487_602
    assert verified.slippage_bps == 50
    assert verified.compute_unit_limit == 122_885
    assert verified.compute_unit_price_micro_lamports == 813_768
    assert verified.priority_fee_lamports == 100_000  # == prioritizationFeeLamports 99999 + 1
    assert verified.ata_creates == 1
    assert verified.closes_wsol_ata is True


def test_the_anchor_discriminators_match_the_bytes_jupiter_emitted() -> None:
    assert ROUTE_DISCRIMINATOR == bytes.fromhex("e517cb977ae3ad2a")
    assert SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR == bytes.fromhex("c1209b3341d69c81")
    assert _real_message().instructions[ROUTE_IX].data[:8] == ROUTE_DISCRIMINATOR


def test_the_real_transaction_has_no_system_instruction() -> None:
    message = _real_message()
    programs = [message.program_id(ix.program_id_index) for ix in message.instructions]
    assert SYSTEM_PROGRAM_ID not in programs


# ------------------------------------------------------------- adversarial
def test_a_system_transfer_to_a_foreign_key_is_refused() -> None:
    message = _real_message()
    system = message.static_account_keys.index(SYSTEM_PROGRAM_ID)
    drain = VersionedCompiledInstruction(system, (0, 9), b"\x02\x00\x00\x00" + u64_le(680_000_000))
    assert _refused(_plus(message, drain)) == "system_program_not_allowed"


def test_a_token_transfer_out_of_the_usdc_ata_is_refused() -> None:
    message = _real_message()
    token = message.static_account_keys.index(TOKEN_PROGRAM_ID)
    transfer = VersionedCompiledInstruction(token, (3, 9, 0), b"\x03" + u64_le(21_330_000))
    assert _refused(_plus(message, transfer)) == "token_instruction_not_allowed:3"


def test_a_route_for_the_whole_balance_is_refused() -> None:
    message = _real_message()
    data = _retail(
        message.instructions[ROUTE_IX].data, in_amount=21_330_000, out=9_487_602, slippage=50
    )
    assert _refused(_with(message, ROUTE_IX, data=data)) == (
        "route_in_amount_mismatch:21330000!=1000000"
    )


def test_a_route_with_ten_thousand_bps_of_slippage_is_refused() -> None:
    message = _real_message()
    data = _retail(
        message.instructions[ROUTE_IX].data, in_amount=1_000_000, out=9_487_602, slippage=10_000
    )
    assert _refused(_with(message, ROUTE_IX, data=data)) == "route_slippage_above_cap:10000"


def test_a_route_promising_less_than_the_quote_is_refused() -> None:
    message = _real_message()
    data = _retail(message.instructions[ROUTE_IX].data, in_amount=1_000_000, out=1, slippage=50)
    assert _refused(_with(message, ROUTE_IX, data=data)) == "route_quoted_out_below_quote"


def test_a_route_with_a_platform_fee_is_refused() -> None:
    message = _real_message()
    data = _retail(
        message.instructions[ROUTE_IX].data, in_amount=1_000_000, out=9_487_602, slippage=50, fee=1
    )
    assert _refused(_with(message, ROUTE_IX, data=data)) == "route_platform_fee_present"


def test_a_route_whose_destination_is_not_our_wsol_ata_is_refused() -> None:
    message = _real_message()
    accounts = list(message.instructions[ROUTE_IX].account_indexes)
    accounts[3] = 9  # some other static account
    reason = _refused(_with(message, ROUTE_IX, account_indexes=tuple(accounts)))
    assert reason == "route_destination_not_wsol_ata"


def test_a_route_with_a_third_party_destination_is_refused() -> None:
    message = _real_message()
    accounts = list(message.instructions[ROUTE_IX].account_indexes)
    accounts[4] = 9  # destination_token_account set instead of None (= the program id)
    reason = _refused(_with(message, ROUTE_IX, account_indexes=tuple(accounts)))
    assert reason == "route_third_party_destination"


def test_a_route_whose_authority_is_not_the_wallet_is_refused() -> None:
    message = _real_message()
    accounts = list(message.instructions[ROUTE_IX].account_indexes)
    accounts[1] = 9
    reason = _refused(_with(message, ROUTE_IX, account_indexes=tuple(accounts)))
    assert reason == "route_authority_not_wallet"


def test_an_unknown_route_discriminator_is_refused() -> None:
    message = _real_message()
    data = message.instructions[ROUTE_IX].data
    exact_out = bytes.fromhex("d033ef977b2bed5c") + data[8:]
    assert _refused(_with(message, ROUTE_IX, data=exact_out)).startswith(
        "route_instruction_unknown:"
    )


def test_a_close_account_paying_someone_else_is_refused() -> None:
    message = _real_message()
    close_ix = len(message.instructions) - 1
    reason = _refused(_with(message, close_ix, account_indexes=(1, 9, 0)))
    assert reason == "close_account_destination_not_wallet"


def test_an_ata_created_for_someone_else_is_refused() -> None:
    message = _real_message()
    accounts = list(message.instructions[2].account_indexes)
    accounts[2] = 9  # owner
    assert _refused(_with(message, 2, account_indexes=tuple(accounts))) == "ata_owner_not_wallet"


def test_a_priority_fee_above_the_cap_is_refused() -> None:
    message = _real_message()
    price = (MAX_PRIORITY_FEE_LAMPORTS + 1) * 1_000_000 // 122_885 + 1
    data = b"\x03" + struct.pack("<Q", price)
    assert _refused(_with(message, 1, data=data)).startswith("priority_fee_above_cap:")


def test_a_second_route_instruction_is_refused() -> None:
    message = _real_message()
    assert _refused(_plus(message, message.instructions[ROUTE_IX])) == (
        "more_than_one_route_instruction"
    )


def test_a_message_without_a_route_is_refused() -> None:
    message = _real_message()
    ixs = tuple(ix for i, ix in enumerate(message.instructions) if i != ROUTE_IX)
    assert _refused(replace(message, instructions=ixs)) == "route_instruction_missing"


def test_a_foreign_program_is_refused_by_name() -> None:
    message = _real_message()
    foreign = VersionedCompiledInstruction(9, (0,), b"\x01")
    assert (
        _refused(_plus(message, foreign)) == f"program_not_allowed:{message.static_account_keys[9]}"
    )


def test_a_program_behind_a_lookup_table_is_refused_not_trusted() -> None:
    message = _real_message()
    assert _refused(_plus(message, VersionedCompiledInstruction(40, (0,), b"\x01"))) == (
        "program_via_lookup_table"
    )


def test_a_fee_payer_that_is_not_the_wallet_is_refused() -> None:
    message = _real_message()
    keys = (message.static_account_keys[9], *message.static_account_keys[1:])
    assert _refused(replace(message, static_account_keys=keys)) == "fee_payer_not_wallet"


def test_more_than_one_signer_is_refused() -> None:
    assert _refused(replace(_real_message(), num_required_signatures=2)) == "more_than_one_signer"


def test_a_zero_blockhash_is_refused() -> None:
    assert _refused(replace(_real_message(), recent_blockhash="1" * 32)) == "blockhash_missing"


def test_a_compute_budget_instruction_that_is_not_limit_or_price_is_refused() -> None:
    message = _real_message()
    assert _refused(_with(message, 0, data=b"\x01\x00\x00\x00\x00")) == (
        "compute_budget_unknown_instruction"
    )


# ------------------------------------------------- shared_accounts_route
def test_a_shared_accounts_route_is_decoded_by_its_own_layout() -> None:
    event_authority = "D8cy77BBepLMngZx6ZukaTff5hCt1HrWyKk3Hnd9oitf"
    # T4.83: every account index must resolve, so the slots the route names
    # beyond the six checked ones are real (inert) static keys, not gaps.
    keys = (
        WALLET,
        JUP_PROGRAM_ID,
        TOKEN_PROGRAM_ID,
        USDC_ATA,
        WSOL_ATA,
        event_authority,
        *(filler(index) for index in range(6, 11)),
    )
    step = bytes((0, 100, 0, 1))  # Swap variant 0, percent 100, input 0, output 1
    data = (
        SHARED_ACCOUNTS_ROUTE_DISCRIMINATOR
        + b"\x07"
        + struct.pack("<I", 1)
        + step
        + _TAIL.pack(1_000_000, 9_500_000, 50, 0)
    )
    route = VersionedCompiledInstruction(1, (2, 6, 0, 3, 7, 8, 4, 9, 10, 1, 1, 5, 1), data)
    message = VersionedMessage(
        version=0,
        num_required_signatures=1,
        num_readonly_signed=0,
        num_readonly_unsigned=4,
        static_account_keys=keys,
        recent_blockhash="5" * 32,
        instructions=(route,),
        address_table_lookups=(),
    )
    verified = verify_swap_transaction(message, intent=INTENT, account_keys=_keys(message))
    assert verified.route_kind == "shared_accounts_route"
    assert verified.quoted_out_amount == 9_500_000
    hostile = replace(route, account_indexes=(2, 6, 0, 3, 7, 8, 4, 9, 10, 5, 1, 5, 1))
    assert _refused(replace(message, instructions=(hostile,))) == (
        "route_platform_fee_account_present"
    )
