"""T4.54 — the v0 (versioned) message/transaction decoder, offline and pure.

Fixtures are built in-process (a real ``VersionedTransaction`` needs a live
RPC blockhash and a signer this sandbox has neither of — no wallet key was
used or looked for): the builder below is the wire format's own spec, not a
guess, so a round trip through it proves the decoder against a known shape.
"""

from __future__ import annotations

import pytest

from hunter_exchanges.jupiter.versioned_tx import (
    decode_versioned_message,
    decode_versioned_transaction,
)
from hunter_exchanges.pumpfun.solana_codec import b58decode

JUP_PROGRAM = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
COMPUTE_BUDGET = "ComputeBudget111111111111111111111111111111"
WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
POOL = "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
BLOCKHASH = "11111111111111111111111111111111111111111"[:32].ljust(32, "1")


def _compact_u16(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def _pubkey_bytes(text: str) -> bytes:
    raw = b58decode(text)
    assert len(raw) == 32
    return raw


def _blockhash_bytes() -> bytes:
    # Any 32 zero bytes decode to a fixed base58 string; used only as a stand-in
    # recent blockhash, never a real one.
    return bytes(32)


def build_v0_message(
    *,
    static_keys: list[str],
    num_required_signatures: int,
    instructions: list[tuple[int, list[int], bytes]],
    lookups: list[tuple[str, list[int], list[int]]] | None = None,
    num_readonly_unsigned: int = 0,
) -> bytes:
    out = bytearray([0x80])  # version prefix: v0
    out += bytes([num_required_signatures, 0, num_readonly_unsigned])
    out += _compact_u16(len(static_keys))
    for key in static_keys:
        out += _pubkey_bytes(key)
    out += _blockhash_bytes()
    out += _compact_u16(len(instructions))
    for program_index, accounts, data in instructions:
        out.append(program_index)
        out += _compact_u16(len(accounts)) + bytes(accounts)
        out += _compact_u16(len(data)) + data
    lookups = lookups or []
    out += _compact_u16(len(lookups))
    for account_key, writable, readonly in lookups:
        out += _pubkey_bytes(account_key)
        out += _compact_u16(len(writable)) + bytes(writable)
        out += _compact_u16(len(readonly)) + bytes(readonly)
    return bytes(out)


def wrap_transaction(message_bytes: bytes, *, signatures: list[bytes] | None = None) -> bytes:
    sigs = signatures or [bytes(64)]
    return _compact_u16(len(sigs)) + b"".join(sigs) + message_bytes


def test_round_trip_decodes_header_keys_and_instructions() -> None:
    message = build_v0_message(
        static_keys=[WALLET, COMPUTE_BUDGET, JUP_PROGRAM, POOL, TOKEN_PROGRAM],
        num_required_signatures=1,
        instructions=[
            (1, [], b"\x02\x40\x0d\x03\x00"),  # ComputeBudget, no accounts
            (2, [0, 3, 4], b"\x01\x02\x03"),  # Jupiter route
        ],
    )
    decoded = decode_versioned_message(message)
    assert decoded.version == 0
    assert decoded.num_required_signatures == 1
    assert decoded.static_account_keys[0] == WALLET
    assert decoded.program_id(0) == WALLET
    assert decoded.program_id(2) == JUP_PROGRAM
    assert decoded.is_signer(0) is True
    assert decoded.is_signer(1) is False
    assert len(decoded.instructions) == 2
    assert decoded.instructions[1].account_indexes == (0, 3, 4)


def test_program_id_behind_a_lookup_table_is_unresolved() -> None:
    message = build_v0_message(
        static_keys=[WALLET, JUP_PROGRAM],
        num_required_signatures=1,
        instructions=[(5, [0], b"\x00")],  # index 5 lives only in the lookup table
        lookups=[(POOL, [5], [6])],
    )
    decoded = decode_versioned_message(message)
    assert decoded.program_id(5) is None, "an account behind an ALT is never resolved here"
    assert decoded.address_table_lookups[0].account_key == POOL
    assert decoded.address_table_lookups[0].writable_indexes == (5,)


def test_a_legacy_message_is_refused() -> None:
    legacy = bytes([1, 0, 0]) + b"\x00"  # high bit of byte 0 clear
    with pytest.raises(ValueError, match="not a versioned"):
        decode_versioned_message(legacy)


def test_an_unsupported_version_is_refused() -> None:
    raw = bytearray(
        build_v0_message(static_keys=[WALLET], num_required_signatures=1, instructions=[])
    )
    raw[0] = 0x81  # version 1: does not exist yet, must not be silently accepted
    with pytest.raises(ValueError, match="unsupported message version"):
        decode_versioned_message(bytes(raw))


def test_trailing_bytes_are_refused() -> None:
    message = build_v0_message(static_keys=[WALLET], num_required_signatures=1, instructions=[])
    with pytest.raises(ValueError, match="trailing bytes"):
        decode_versioned_message(message + b"\x00")


def test_transaction_wrapper_splits_signatures_from_the_message() -> None:
    message = build_v0_message(
        static_keys=[WALLET, JUP_PROGRAM],
        num_required_signatures=1,
        instructions=[(1, [0], b"\x01")],
    )
    tx_bytes = wrap_transaction(message, signatures=[bytes(64)])
    decoded = decode_versioned_transaction(tx_bytes)
    assert decoded.signatures == (bytes(64),)
    assert decoded.message_bytes == message
    assert decoded.message.static_account_keys[0] == WALLET
