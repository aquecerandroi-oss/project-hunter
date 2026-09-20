"""T4.74-4 — a Jupiter-shaped v0 transaction encoded by hand (no network, no
capture needed: the wire shape is documented and struct-packed), so the
**real** ``decode_versioned_transaction`` and ``verify_spot_swap_tx`` run in
the money-path tests; plus the shared constants and the quote builder."""

from __future__ import annotations

import base64
import struct
from decimal import Decimal

from hunter_exchanges.jupiter import JupiterQuote, JupiterSwapTransaction
from hunter_exchanges.jupiter.versioned_tx import VersionedCompiledInstruction, VersionedMessage
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
    out += _compact(0)
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
