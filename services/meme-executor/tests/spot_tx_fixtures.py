"""T4.74-4 — a Jupiter-shaped v0 transaction encoded by hand (no network, no
capture needed: the wire shape is documented and struct-packed), so the
**real** ``decode_versioned_transaction`` and ``verify_spot_swap_tx`` run in
the money-path tests; plus the shared constants and the quote builder."""

from __future__ import annotations

import base64
import struct
from decimal import Decimal

from hunter_exchanges.jupiter import JupiterQuote, JupiterSwapTransaction
from hunter_exchanges.jupiter.versioned_tx import (
    AddressTableLookup,
    VersionedCompiledInstruction,
    VersionedMessage,
)
from hunter_exchanges.pumpfun.solana_codec import (
    ASSOCIATED_TOKEN_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58encode,
    pubkey_bytes,
)
from hunter_meme_executor.treasury_rules import JUP_PROGRAM_ID
from hunter_meme_executor.treasury_verify import ROUTE_DISCRIMINATOR

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"
WSOL = "So11111111111111111111111111111111111111112"
WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
WSOL_ATA = associated_token_address(WALLET, WSOL, token_program=TOKEN_PROGRAM_ID)
WIF_ATA = associated_token_address(WALLET, WIF, token_program=TOKEN_PROGRAM_ID)
ORDER = "01996e2a-0000-7000-8000-00000000000f"
TICKET = 50_000_000
OUT = 26_005_682
THRESHOLD = OUT * 9950 // 10_000
SIG_BYTES = bytes([7]) * 64
SIGNATURE = b58encode(SIG_BYTES)
ATA_RENT = 2_039_280
_TAIL = struct.Struct("<QQHB")


# ------------------------------------------------------------- a v0 transaction by hand
def _compact(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def encode_v0(message: VersionedMessage) -> bytes:
    out = bytearray([0x80 | message.version])
    out += bytes(
        (
            message.num_required_signatures,
            message.num_readonly_signed,
            message.num_readonly_unsigned,
        )
    )
    out += _compact(len(message.static_account_keys))
    for key in message.static_account_keys:
        out += pubkey_bytes(key)
    out += pubkey_bytes(message.recent_blockhash)
    out += _compact(len(message.instructions))
    for ix in message.instructions:
        out.append(ix.program_id_index)
        out += _compact(len(ix.account_indexes)) + bytes(ix.account_indexes)
        out += _compact(len(ix.data)) + ix.data
    out += _compact(len(message.address_table_lookups))
    for lookup in message.address_table_lookups:
        out += pubkey_bytes(lookup.account_key)
        out += _compact(len(lookup.writable_indexes)) + bytes(lookup.writable_indexes)
        out += _compact(len(lookup.readonly_indexes)) + bytes(lookup.readonly_indexes)
    return bytes(out)


def _route_data(*, in_amount: int, out: int, slippage: int = 50) -> bytes:
    step = bytes((0, 100, 0, 1))
    return (
        ROUTE_DISCRIMINATOR + struct.pack("<I", 1) + step + _TAIL.pack(in_amount, out, slippage, 0)
    )


def _route_ix(*, source: int, dest: int, data: bytes) -> VersionedCompiledInstruction:
    return VersionedCompiledInstruction(1, (0, 0, source, dest, 1, 0, 1), data)


KEYS = (
    WALLET,
    JUP_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    WSOL_ATA,
    WIF_ATA,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    WSOL,
    WIF,
)


def _message(instructions: tuple[VersionedCompiledInstruction, ...]) -> VersionedMessage:
    return VersionedMessage(
        version=0,
        num_required_signatures=1,
        num_readonly_signed=0,
        num_readonly_unsigned=6,
        static_account_keys=KEYS,
        recent_blockhash=b58encode(bytes([5]) * 32),
        instructions=instructions,
        address_table_lookups=(),
    )


def buy_message(
    *, in_amount: int = TICKET, out: int = OUT, cu_price: int = 500
) -> VersionedMessage:
    """SOL -> WIF: compute budget (limit 100 000 × price), own WSOL ATA, wrap, route."""
    return _message(
        (
            VersionedCompiledInstruction(7, (), bytes([2]) + struct.pack("<I", 100_000)),
            VersionedCompiledInstruction(7, (), bytes([3]) + struct.pack("<Q", cu_price)),
            VersionedCompiledInstruction(5, (0, 3, 0, 8, 6, 2), b"\x01"),
            VersionedCompiledInstruction(5, (0, 4, 0, 9, 6, 2), b"\x01"),
            VersionedCompiledInstruction(
                6, (0, 3), struct.pack("<I", 2) + struct.pack("<Q", in_amount)
            ),
            VersionedCompiledInstruction(2, (3,), bytes([17])),
            _route_ix(source=3, dest=4, data=_route_data(in_amount=in_amount, out=out)),
            VersionedCompiledInstruction(2, (3, 0, 0), bytes([9])),
        )
    )


def sell_message(*, in_amount: int, out: int) -> VersionedMessage:
    """WIF -> SOL: compute budget, own WSOL ATA, route, unwrap (CloseAccount)."""
    return _message(
        (
            VersionedCompiledInstruction(7, (), bytes([2]) + struct.pack("<I", 100_000)),
            VersionedCompiledInstruction(7, (), bytes([3]) + struct.pack("<Q", 500)),
            VersionedCompiledInstruction(5, (0, 3, 0, 8, 6, 2), b"\x01"),
            _route_ix(source=4, dest=3, data=_route_data(in_amount=in_amount, out=out)),
            VersionedCompiledInstruction(2, (3, 0, 0), bytes([9])),
        )
    )


def as_swap(message: VersionedMessage) -> JupiterSwapTransaction:
    raw = _compact(1) + bytes(64) + encode_v0(message)
    return JupiterSwapTransaction(base64.b64encode(raw).decode("ascii"), 250_000_123, 50_000)


def quote(*, input_mint: str, output_mint: str, amount: int, out: int) -> JupiterQuote:
    return JupiterQuote(
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount=Decimal(amount),
        out_amount=Decimal(out),
        other_amount_threshold=Decimal(out * 9950 // 10_000),
        price_impact_pct=Decimal("0.0006"),
        slippage_bps=50,
        route_labels=("Raydium",),
        raw={"inputMint": input_mint, "outputMint": output_mint, "inAmount": str(amount)},
    )


# ------------------------------------------------- address lookup tables (T4.81)
ALT_TABLE = b58encode(bytes([11]) * 32)
"""The lookup table ``alt_buy_message`` loads its two addresses from."""
ALT_TABLE_B = b58encode(bytes([12]) * 32)
ALT_ACTIVE_SLOT = 2**64 - 1
"""``deactivation_slot`` of a table that was never deactivated."""
ALT_META_SIZE = 56


def filler(index: int) -> str:
    """A distinct, inert address for the slots of a table nobody reads."""
    return b58encode(bytes([0xAA]) + index.to_bytes(2, "big") + bytes(29))


def table_addresses(size: int, entries: dict[int, str]) -> tuple[str, ...]:
    out = [filler(index) for index in range(size)]
    for index, address in entries.items():
        out[index] = address
    return tuple(out)


def lookup_table_data(
    addresses: tuple[str, ...],
    *,
    deactivation_slot: int = ALT_ACTIVE_SLOT,
    discriminant: int = 1,
    trailing: bytes = b"",
) -> str:
    """The base64 account data of an Address Lookup Table: a 56-byte header
    (``u32`` discriminant, ``u64`` deactivation slot, ``u64`` last extended slot,
    ``u8`` start index, ``Option<Pubkey>`` authority, ``u16`` padding) then the
    addresses."""
    meta = (
        struct.pack("<IQQB", discriminant, deactivation_slot, 0, 0)
        + b"\x01"
        + pubkey_bytes(WALLET)
        + b"\x00\x00"
    )
    assert len(meta) == ALT_META_SIZE
    body = b"".join(pubkey_bytes(address) for address in addresses)
    return base64.b64encode(meta + body + trailing).decode("ascii")


# static 0..7; loaded 8 = the WIF ATA (writable), 9 = the WIF mint (readonly)
ALT_KEYS = (
    WALLET,
    JUP_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
    WSOL_ATA,
    ASSOCIATED_TOKEN_PROGRAM_ID,
    SYSTEM_PROGRAM_ID,
    COMPUTE_BUDGET_PROGRAM_ID,
    WSOL,
)
ALT_WRITABLE = (5,)
ALT_READONLY = (7,)
ALT_TABLE_ADDRESSES = table_addresses(16, {5: WIF_ATA, 7: WIF})


def alt_lookup(
    *,
    table: str = ALT_TABLE,
    writable: tuple[int, ...] = ALT_WRITABLE,
    readonly: tuple[int, ...] = ALT_READONLY,
) -> AddressTableLookup:
    return AddressTableLookup(table, writable, readonly)


def alt_buy_message(
    *,
    in_amount: int = TICKET,
    out: int = OUT,
    lookups: tuple[AddressTableLookup, ...] | None = None,
    route_dest: int = 8,
) -> VersionedMessage:
    """``buy_message`` with the WIF ATA (index 8) and the WIF mint (index 9)
    reachable only through ``ALT_TABLE`` — the shape that refused the desk's
    first real signal on 23/09/2026."""
    return VersionedMessage(
        version=0,
        num_required_signatures=1,
        num_readonly_signed=0,
        num_readonly_unsigned=5,
        static_account_keys=ALT_KEYS,
        recent_blockhash=b58encode(bytes([5]) * 32),
        instructions=(
            VersionedCompiledInstruction(6, (), bytes([2]) + struct.pack("<I", 100_000)),
            VersionedCompiledInstruction(6, (), bytes([3]) + struct.pack("<Q", 500)),
            VersionedCompiledInstruction(4, (0, 3, 0, 7, 5, 2), b"\x01"),
            VersionedCompiledInstruction(4, (0, 8, 0, 9, 5, 2), b"\x01"),
            VersionedCompiledInstruction(
                5, (0, 3), struct.pack("<I", 2) + struct.pack("<Q", in_amount)
            ),
            VersionedCompiledInstruction(2, (3,), bytes([17])),
            VersionedCompiledInstruction(
                1, (0, 0, 3, route_dest, 1, 0, 1), _route_data(in_amount=in_amount, out=out)
            ),
            VersionedCompiledInstruction(2, (3, 0, 0), bytes([9])),
        ),
        address_table_lookups=(alt_lookup(),) if lookups is None else lookups,
    )
