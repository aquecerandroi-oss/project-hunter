"""``spot_verify.verify_spot_swap_tx`` (T4.73) — the generic-mint verifier,
against synthetic Jupiter-shaped messages built the same way
``test_treasury_verify.py``'s ``shared_accounts_route`` case is (no network,
no real capture needed: the wire shape is documented and struct-packed by
hand). Pure: no signer, no RPC, no database.
"""

from __future__ import annotations

import struct
from dataclasses import replace

import pytest

from hunter_exchanges.jupiter.versioned_tx import VersionedCompiledInstruction, VersionedMessage
from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
)
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID, USDC_MINT, TreasurySwapRefused
from hunter_meme_executor.treasury_verify import ROUTE_DISCRIMINATOR

pytestmark = pytest.mark.unit

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
WSOL = "So11111111111111111111111111111111111111112"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
_TAIL = struct.Struct("<QQHB")  # in_amount, quoted_out, slippage_bps, platform_fee_bps


def _route_data(*, in_amount: int, out: int, slippage: int, fee: int = 0) -> bytes:
    step = bytes((0, 100, 0, 1))  # one Swap step: variant, percent, input idx, output idx
    return (
        ROUTE_DISCRIMINATOR
        + struct.pack("<I", 1)
        + step
        + _TAIL.pack(in_amount, out, slippage, fee)
    )


def _route_ix(
    program_index: int, *, authority: int, source: int, dest: int, sentinel: int, data: bytes
) -> VersionedCompiledInstruction:
    # positions: 0 unused, 1 authority, 2 source, 3 destination, 4 third-party (sentinel), 5 unused, 6 fee (sentinel)
    return VersionedCompiledInstruction(
        program_index, (0, authority, source, dest, sentinel, 0, sentinel), data
    )


def _wrap_message(
    *,
    in_amount: int = 20_000_000,
    out_amount: int = 10_402_273,
    route_in_amount: int | None = None,
) -> VersionedMessage:
    """input=WSOL, output=WIF: ComputeBudget x2, ATA create (own WSOL ATA),
    System.Transfer (wrap), SyncNative, route. Mirrors the real shape Jupiter
    emits when SOL is the input (``docs/RISK_ENGINE_MEME.md`` §16.x)."""
    wsol_ata = associated_token_address(WALLET, WSOL, token_program=TOKEN_PROGRAM_ID)
    wif_ata = associated_token_address(WALLET, WIF, token_program=TOKEN_PROGRAM_ID)
    keys = (
        WALLET,  # 0
        JUP_PROGRAM_ID,  # 1
        TOKEN_PROGRAM_ID,  # 2
        wsol_ata,  # 3
        wif_ata,  # 4
        ASSOCIATED_TOKEN_PROGRAM_ID,  # 5
        SYSTEM_PROGRAM_ID,  # 6
        COMPUTE_BUDGET_PROGRAM_ID,  # 7
        WSOL,  # 8
        WIF,  # 9
    )
    instructions = (
        VersionedCompiledInstruction(7, (), bytes([2]) + struct.pack("<I", 100_000)),
        VersionedCompiledInstruction(7, (), bytes([3]) + struct.pack("<Q", 1)),
        VersionedCompiledInstruction(5, (0, 3, 0, 8, 6, 2), b"\x01"),  # create own WSOL ATA
        VersionedCompiledInstruction(
            6, (0, 3), struct.pack("<I", 2) + struct.pack("<Q", in_amount)
        ),
        VersionedCompiledInstruction(2, (3,), bytes([17])),  # SyncNative
        _route_ix(
            1,
            authority=0,
            source=3,
            dest=4,
            sentinel=1,
            data=_route_data(
                in_amount=route_in_amount if route_in_amount is not None else in_amount,
                out=out_amount,
                slippage=50,
            ),
        ),
    )
    return VersionedMessage(
        version=0,
        num_required_signatures=1,
        num_readonly_signed=0,
        num_readonly_unsigned=6,
        static_account_keys=keys,
        recent_blockhash="5" * 32,
        instructions=instructions,
        address_table_lookups=(),
    )


def _token_to_token_message(
    *, in_amount: int = 1_000_000, out_amount: int = 900_000
) -> VersionedMessage:
    """input=USDC, output=WIF, no SOL on either leg: both ATAs created, no wrap/unwrap."""
    usdc_ata = associated_token_address(WALLET, USDC_MINT, token_program=TOKEN_PROGRAM_ID)
    wif_ata = associated_token_address(WALLET, WIF, token_program=TOKEN_PROGRAM_ID)
    keys = (
        WALLET,  # 0
        JUP_PROGRAM_ID,  # 1
        TOKEN_PROGRAM_ID,  # 2
        usdc_ata,  # 3
        wif_ata,  # 4
        ASSOCIATED_TOKEN_PROGRAM_ID,  # 5
        SYSTEM_PROGRAM_ID,  # 6
        USDC_MINT,  # 7
        WIF,  # 8
    )
    instructions = (
        VersionedCompiledInstruction(5, (0, 3, 0, 7, 6, 2), b"\x01"),  # create USDC ATA
        VersionedCompiledInstruction(5, (0, 4, 0, 8, 6, 2), b"\x01"),  # create WIF ATA
        _route_ix(
            1,
            authority=0,
            source=3,
            dest=4,
            sentinel=1,
            data=_route_data(in_amount=in_amount, out=out_amount, slippage=50),
        ),
    )
    return VersionedMessage(
        version=0,
        num_required_signatures=1,
        num_readonly_signed=0,
        num_readonly_unsigned=5,
        static_account_keys=keys,
        recent_blockhash="5" * 32,
        instructions=instructions,
        address_table_lookups=(),
    )


def _intent(
    message: VersionedMessage, *, input_mint: str, output_mint: str, in_amount: int, min_out: int
) -> SpotSwapIntent:
    return SpotSwapIntent(
        wallet=WALLET,
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount=in_amount,
        min_quoted_out=min_out,
        max_slippage_bps=50,
    )


def test_a_sol_wrap_is_accepted() -> None:
    message = _wrap_message()
    intent = _intent(
        message, input_mint=WSOL, output_mint=WIF, in_amount=20_000_000, min_out=10_000_000
    )
    verified = verify_spot_swap_tx(message, intent=intent)
    assert verified.wraps_sol is True
    assert verified.unwraps_sol is False
    assert verified.in_amount == 20_000_000
    assert verified.quoted_out_amount == 10_402_273


def test_a_token_to_token_swap_with_both_atas_created_is_accepted() -> None:
    message = _token_to_token_message()
    intent = _intent(
        message, input_mint=USDC_MINT, output_mint=WIF, in_amount=1_000_000, min_out=800_000
    )
    verified = verify_spot_swap_tx(message, intent=intent)
    assert verified.ata_creates == 2
    assert verified.wraps_sol is False and verified.unwraps_sol is False


def test_a_foreign_destination_token_transfer_is_refused() -> None:
    message = _token_to_token_message()
    # destination = JUP6 (index 1), an account that is not one of our own ATAs
    transfer = VersionedCompiledInstruction(2, (3, 1, 0), b"\x03" + struct.pack("<Q", 1_000_000))
    hostile = replace(message, instructions=(*message.instructions, transfer))
    intent = _intent(
        hostile, input_mint=USDC_MINT, output_mint=WIF, in_amount=1_000_000, min_out=800_000
    )
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(hostile, intent=intent)
    assert excinfo.value.reason == "token_instruction_not_allowed:3"


def test_a_route_in_amount_mismatch_is_refused() -> None:
    """The System.Transfer wraps the amount actually requested, but the JUP6
    route instruction's own tail names a different ``in_amount`` — the route
    is what the chain executes, so it is refused even though the wrap matches."""
    message = _wrap_message(in_amount=20_000_000, route_in_amount=999)
    intent = _intent(message, input_mint=WSOL, output_mint=WIF, in_amount=20_000_000, min_out=1)
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(message, intent=intent)
    assert excinfo.value.reason.startswith("route_in_amount_mismatch:")


def test_a_system_transfer_when_input_is_not_wsol_is_refused() -> None:
    message = _token_to_token_message()
    drain = VersionedCompiledInstruction(6, (0, 3), struct.pack("<I", 2) + struct.pack("<Q", 1))
    hostile = replace(message, instructions=(*message.instructions, drain))
    intent = _intent(
        hostile, input_mint=USDC_MINT, output_mint=WIF, in_amount=1_000_000, min_out=800_000
    )
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(hostile, intent=intent)
    assert excinfo.value.reason == "system_program_not_allowed"


def test_a_message_with_lookup_tables_is_refused_when_the_caller_resolved_nothing() -> None:
    """T4.81: the verifier is pure, so a message whose accounts live in a lookup
    table can only be verified against the caller's resolved key list. Without
    one it is refused by name — never verified against the static keys alone
    (T4.73b finding 6, where the mint at position 3 escaped the derivation).
    ``test_spot_verify_alt.py`` covers the resolved case, pass and fail."""
    from hunter_exchanges.jupiter.versioned_tx import AddressTableLookup

    message = _wrap_message()
    n_static = len(message.static_account_keys)
    hidden_mint_create = VersionedCompiledInstruction(5, (0, 3, 0, n_static, 6, 2), b"\x01")
    instructions = list(message.instructions)
    instructions[2] = hidden_mint_create
    hostile = replace(
        message,
        instructions=tuple(instructions),
        address_table_lookups=(AddressTableLookup("A" * 32, (), (0,)),),
    )
    intent = _intent(hostile, input_mint=WSOL, output_mint=WIF, in_amount=20_000_000, min_out=1)
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(hostile, intent=intent)
    assert excinfo.value.reason == "lookup_tables_unresolved"


def test_an_account_index_past_the_resolved_keys_is_refused_by_name() -> None:
    """A message with no lookup table whose instruction still points past the
    keys: unresolvable, refused before any check can read the wrong account."""
    message = _wrap_message()
    n_static = len(message.static_account_keys)
    hidden_ata_create = VersionedCompiledInstruction(5, (0, n_static, 0, 8, 6, 2), b"\x01")
    instructions = list(message.instructions)
    instructions[2] = hidden_ata_create
    hostile = replace(message, instructions=tuple(instructions))
    intent = _intent(hostile, input_mint=WSOL, output_mint=WIF, in_amount=20_000_000, min_out=1)
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(hostile, intent=intent)
    assert excinfo.value.reason == f"account_index_out_of_range:{n_static}"
