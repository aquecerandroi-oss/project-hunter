"""Solana wire primitives in pure Python — no ``solders``, no network, no key.

Base58, PDAs (with the real ed25519 off-curve check ``docs/PUMPFUN-ONCHAIN.md``
§1.4b said was missing), ATAs, Borsh scalars, ComputeBudget instructions and the
**legacy** ``Message`` layout (compile / serialize / deserialize / decompile).
Versioned (v0) messages are refused on purpose: our transactions never use a
lookup table, and a verifier that accepted one would compare accounts it cannot
see (``docs/RISK_ENGINE_MEME.md`` §9.1). :func:`compile_message` orders keys as
``solana-sdk``'s ``legacy::Message::new_with_blockhash`` does (programs first,
then instruction accounts, stable-sorted by signer then writable, payer at 0).
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = [
    "ASSOCIATED_TOKEN_PROGRAM_ID",
    "COMPUTE_BUDGET_PROGRAM_ID",
    "SYSTEM_PROGRAM_ID",
    "TOKEN_2022_PROGRAM_ID",
    "TOKEN_PROGRAM_ID",
    "AccountMeta",
    "CompiledInstruction",
    "Instruction",
    "Message",
    "associated_token_address",
    "b58decode",
    "b58encode",
    "compile_message",
    "decompile_message",
    "deserialize_message",
    "find_program_address",
    "pubkey_bytes",
    "serialize_message",
    "serialize_transaction",
    "set_compute_unit_limit",
    "set_compute_unit_price",
    "u64_le",
]

SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"
TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"  # noqa: S105 - program id
TOKEN_2022_PROGRAM_ID = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"  # noqa: S105 - program id
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"  # noqa: S105 - program id
COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"

_B58 = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58)}
_PDA_MARKER = b"ProgramDerivedAddress"
_MAX_SEEDS = 16
_MAX_SEED_LEN = 32

# ed25519 field constants for the off-curve check (curve25519-dalek decompress).
_P = 2**255 - 19
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_B58[rem])
    out.reverse()
    pad = len(raw) - len(raw.lstrip(b"\0"))
    return (_B58[0:1] * pad + out).decode("ascii")


def b58decode(text: str) -> bytes:
    n = 0
    for ch in text.encode("ascii"):
        if ch not in _B58_INDEX:
            raise ValueError("invalid base58 character")
        n = n * 58 + _B58_INDEX[ch]
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    pad = len(text) - len(text.lstrip("1"))
    return b"\0" * pad + raw


def pubkey_bytes(pubkey: str) -> bytes:
    raw = b58decode(pubkey)
    if len(raw) != 32:
        raise ValueError(f"pubkey {pubkey!r} is {len(raw)} bytes, need 32")
    return raw


def _is_on_curve(point: bytes) -> bool:
    """``CompressedEdwardsY::decompress().is_some()`` — a PDA must be *off* the curve."""
    y = int.from_bytes(point, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        return False
    y2 = y * y % _P
    u = (y2 - 1) % _P
    v = (_D * y2 + 1) % _P
    x = u * pow(v, 3, _P) * pow(u * pow(v, 7, _P) % _P, (_P - 5) // 8, _P) % _P
    vx2 = v * x * x % _P
    if vx2 == u:
        pass
    elif vx2 == (-u) % _P:
        x = x * _SQRT_M1 % _P
    else:
        return False
    return not (x == 0 and sign == 1)


def _create_program_address(seeds: Sequence[bytes], program_id: bytes) -> bytes:
    if len(seeds) > _MAX_SEEDS or any(len(seed) > _MAX_SEED_LEN for seed in seeds):
        raise ValueError("PDA seeds: at most 16 seeds of at most 32 bytes")
    digest = hashlib.sha256(b"".join(seeds) + program_id + _PDA_MARKER).digest()
    if _is_on_curve(digest):
        raise ValueError("candidate address is on the ed25519 curve")
    return digest


def find_program_address(seeds: Sequence[bytes], program_id: str) -> tuple[str, int]:
    """Canonical bump search (255 down to 0), exactly as ``Pubkey::find_program_address``."""
    program = pubkey_bytes(program_id)
    for bump in range(255, -1, -1):
        try:
            return b58encode(_create_program_address([*seeds, bytes([bump])], program)), bump
        except ValueError:
            continue
    raise ValueError("no viable program address bump")  # pragma: no cover - probability 2^-256


def associated_token_address(owner: str, mint: str, *, token_program: str) -> str:
    """The ATA is a PDA of the associated-token program over (owner, token program, mint)
    — the token program is part of the seed, so a Token-2022 mint has a different ATA."""
    return find_program_address(
        [pubkey_bytes(owner), pubkey_bytes(token_program), pubkey_bytes(mint)],
        ASSOCIATED_TOKEN_PROGRAM_ID,
    )[0]


def u64_le(value: int) -> bytes:
    if not 0 <= value < 2**64:
        raise ValueError(f"u64 out of range: {value}")
    return struct.pack("<Q", value)


@dataclass(frozen=True, slots=True)
class AccountMeta:
    pubkey: str
    is_signer: bool
    is_writable: bool


@dataclass(frozen=True, slots=True)
class Instruction:
    program_id: str
    accounts: tuple[AccountMeta, ...]
    data: bytes


@dataclass(frozen=True, slots=True)
class CompiledInstruction:
    program_id_index: int
    account_indexes: tuple[int, ...]
    data: bytes


@dataclass(frozen=True, slots=True)
class Message:
    """A legacy Solana message: header, keys, blockhash, compiled instructions."""

    num_required_signatures: int
    num_readonly_signed: int
    num_readonly_unsigned: int
    account_keys: tuple[str, ...]
    recent_blockhash: str
    instructions: tuple[CompiledInstruction, ...]

    def is_signer(self, index: int) -> bool:
        return index < self.num_required_signatures

    def is_writable(self, index: int) -> bool:
        n_keys = len(self.account_keys)
        n_signed = self.num_required_signatures
        if index < n_signed:
            return index < n_signed - self.num_readonly_signed
        return index < n_keys - self.num_readonly_unsigned


def set_compute_unit_limit(units: int) -> Instruction:
    """ComputeBudget ``SetComputeUnitLimit`` (enum index 2, u32)."""
    if not 0 < units <= 1_400_000:
        raise ValueError("compute unit limit must be in 1..1_400_000")
    return Instruction(COMPUTE_BUDGET_PROGRAM_ID, (), b"\x02" + struct.pack("<I", units))


def set_compute_unit_price(micro_lamports: int) -> Instruction:
    """ComputeBudget ``SetComputeUnitPrice`` (enum index 3, u64 micro-lamports per CU)."""
    if micro_lamports < 0:
        raise ValueError("compute unit price must be >= 0")
    return Instruction(COMPUTE_BUDGET_PROGRAM_ID, (), b"\x03" + u64_le(micro_lamports))


def compile_message(
    payer: str, instructions: Sequence[Instruction], recent_blockhash: str
) -> Message:
    metas: list[AccountMeta] = [
        AccountMeta(pid, False, False) for pid in _unique(ix.program_id for ix in instructions)
    ]
    for ix in instructions:
        metas.extend(ix.accounts)
    metas.sort(key=lambda m: (not m.is_signer, not m.is_writable))
    metas.insert(0, AccountMeta(payer, True, True))
    unique: list[AccountMeta] = []
    for meta in metas:
        for i, seen in enumerate(unique):
            if seen.pubkey == meta.pubkey:
                unique[i] = AccountMeta(
                    seen.pubkey,
                    seen.is_signer or meta.is_signer,
                    seen.is_writable or meta.is_writable,
                )
                break
        else:
            unique.append(meta)
    signed = [m for m in unique if m.is_signer]
    unsigned = [m for m in unique if not m.is_signer]
    keys = tuple(m.pubkey for m in signed + unsigned)
    index = {key: i for i, key in enumerate(keys)}
    compiled = tuple(
        CompiledInstruction(
            index[ix.program_id], tuple(index[a.pubkey] for a in ix.accounts), ix.data
        )
        for ix in instructions
    )
    return Message(
        num_required_signatures=len(signed),
        num_readonly_signed=sum(1 for m in signed if not m.is_writable),
        num_readonly_unsigned=sum(1 for m in unsigned if not m.is_writable),
        account_keys=keys,
        recent_blockhash=recent_blockhash,
        instructions=compiled,
    )


def _unique(items: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _compact_u16(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value == 0:
            out.append(byte)
            return bytes(out)
        out.append(byte | 0x80)


def _read_compact_u16(raw: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in (0, 7, 14):
        byte = raw[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, offset
    raise ValueError("compact-u16 longer than 3 bytes")


def serialize_message(message: Message) -> bytes:
    out = bytearray(
        (
            message.num_required_signatures,
            message.num_readonly_signed,
            message.num_readonly_unsigned,
        )
    )
    out += _compact_u16(len(message.account_keys))
    for key in message.account_keys:
        out += pubkey_bytes(key)
    out += pubkey_bytes(message.recent_blockhash)
    out += _compact_u16(len(message.instructions))
    for ix in message.instructions:
        out.append(ix.program_id_index)
        out += _compact_u16(len(ix.account_indexes)) + bytes(ix.account_indexes)
        out += _compact_u16(len(ix.data)) + ix.data
    return bytes(out)


def deserialize_message(raw: bytes) -> Message:
    """Legacy only. A version prefix (high bit of the first byte) is refused, not parsed."""
    if not raw:
        raise ValueError("empty message")
    if raw[0] & 0x80:
        raise ValueError("versioned (v0) message refused: address lookup tables hide accounts")
    num_sigs, ro_signed, ro_unsigned = raw[0], raw[1], raw[2]
    n_keys, off = _read_compact_u16(raw, 3)
    keys: list[str] = []
    for _ in range(n_keys):
        keys.append(b58encode(raw[off : off + 32]))
        off += 32
    blockhash = b58encode(raw[off : off + 32])
    off += 32
    n_ix, off = _read_compact_u16(raw, off)
    instructions: list[CompiledInstruction] = []
    for _ in range(n_ix):
        program_index = raw[off]
        off += 1
        n_acc, off = _read_compact_u16(raw, off)
        indexes = tuple(raw[off : off + n_acc])
        off += n_acc
        n_data, off = _read_compact_u16(raw, off)
        data = raw[off : off + n_data]
        off += n_data
        if program_index >= n_keys or any(i >= n_keys for i in indexes) or len(data) != n_data:
            raise ValueError("message references an account index it does not carry")
        instructions.append(CompiledInstruction(program_index, indexes, bytes(data)))
    if off != len(raw):
        raise ValueError("trailing bytes after the message")
    return Message(num_sigs, ro_signed, ro_unsigned, tuple(keys), blockhash, tuple(instructions))


def decompile_message(message: Message) -> tuple[Instruction, ...]:
    """Recover full ``Instruction``s (with signer/writable flags) from a compiled message."""
    return tuple(
        Instruction(
            message.account_keys[ix.program_id_index],
            tuple(
                AccountMeta(message.account_keys[i], message.is_signer(i), message.is_writable(i))
                for i in ix.account_indexes
            ),
            ix.data,
        )
        for ix in message.instructions
    )


def serialize_transaction(signatures: Sequence[bytes], message_bytes: bytes) -> bytes:
    """``compact-u16(n) || signatures || message`` — the wire form ``sendTransaction`` takes."""
    if any(len(sig) != 64 for sig in signatures):
        raise ValueError("every signature is 64 bytes")
    return _compact_u16(len(signatures)) + b"".join(signatures) + message_bytes
