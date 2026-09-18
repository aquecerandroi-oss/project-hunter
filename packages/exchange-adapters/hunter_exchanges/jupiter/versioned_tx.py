"""Solana v0 (versioned) transaction decode — read-only, no signing (T4.54).

Jupiter's ``/swap`` returns a **versioned** transaction (a route's
intermediate accounts usually live behind address lookup tables), a shape
``hunter_exchanges.pumpfun.solana_codec`` deliberately refuses to parse — our
own transactions never need one, and a verifier that trusted an account it
cannot see would be worse than none (that module's own docstring).

This module decodes just enough of the wire format for
``hunter_meme_executor.treasury`` to check a swap's shape before it is ever
signed: the signature wrapper, the header, the *static* account keys, the
compiled instructions, and the address-table-lookup accounts as opaque keys.
An account behind a lookup table is **never resolved** here (that needs a
further RPC round trip this module deliberately does not make): a
``program_id`` that lives there is reported as ``None``, and the caller must
treat that as unverifiable, not as innocent.
"""

from __future__ import annotations

from dataclasses import dataclass

from hunter_exchanges.pumpfun.solana_codec import b58encode

__all__ = [
    "AddressTableLookup",
    "VersionedCompiledInstruction",
    "VersionedMessage",
    "VersionedTransaction",
    "decode_versioned_message",
    "decode_versioned_transaction",
]


def _read_compact_u16(raw: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in (0, 7, 14):
        if offset >= len(raw):
            raise ValueError("truncated compact-u16")
        byte = raw[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return value, offset
    raise ValueError("compact-u16 longer than 3 bytes")


@dataclass(frozen=True, slots=True)
class VersionedCompiledInstruction:
    program_id_index: int
    account_indexes: tuple[int, ...]
    data: bytes


@dataclass(frozen=True, slots=True)
class AddressTableLookup:
    account_key: str
    writable_indexes: tuple[int, ...]
    readonly_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class VersionedMessage:
    version: int
    num_required_signatures: int
    num_readonly_signed: int
    num_readonly_unsigned: int
    static_account_keys: tuple[str, ...]
    recent_blockhash: str
    instructions: tuple[VersionedCompiledInstruction, ...]
    address_table_lookups: tuple[AddressTableLookup, ...]

    def program_id(self, index: int) -> str | None:
        """The program id at ``index``, or ``None`` when it is only reachable
        through a lookup table (never resolved by this module)."""
        if 0 <= index < len(self.static_account_keys):
            return self.static_account_keys[index]
        return None

    def is_signer(self, index: int) -> bool:
        return 0 <= index < self.num_required_signatures


@dataclass(frozen=True, slots=True)
class VersionedTransaction:
    signatures: tuple[bytes, ...]
    message: VersionedMessage
    message_bytes: bytes
    """The exact bytes the signatures sign over — re-serializing ``message``
    is not attempted (byte-for-byte fidelity matters more than convenience)."""


def decode_versioned_message(raw: bytes) -> VersionedMessage:
    if not raw:
        raise ValueError("empty message")
    if not raw[0] & 0x80:
        raise ValueError("not a versioned (v0) message: high bit of byte 0 is clear")
    version = raw[0] & 0x7F
    if version != 0:
        raise ValueError(f"unsupported message version {version}")
    off = 1
    if off + 3 > len(raw):
        raise ValueError("truncated message header")
    num_sigs, ro_signed, ro_unsigned = raw[off], raw[off + 1], raw[off + 2]
    off += 3
    n_keys, off = _read_compact_u16(raw, off)
    keys: list[str] = []
    for _ in range(n_keys):
        keys.append(b58encode(raw[off : off + 32]))
        off += 32
    blockhash = b58encode(raw[off : off + 32])
    off += 32
    n_ix, off = _read_compact_u16(raw, off)
    instructions: list[VersionedCompiledInstruction] = []
    for _ in range(n_ix):
        program_index = raw[off]
        off += 1
        n_acc, off = _read_compact_u16(raw, off)
        indexes = tuple(raw[off : off + n_acc])
        off += n_acc
        n_data, off = _read_compact_u16(raw, off)
        data = raw[off : off + n_data]
        off += n_data
        instructions.append(VersionedCompiledInstruction(program_index, indexes, bytes(data)))
    n_lookups, off = _read_compact_u16(raw, off)
    lookups: list[AddressTableLookup] = []
    for _ in range(n_lookups):
        account_key = b58encode(raw[off : off + 32])
        off += 32
        n_w, off = _read_compact_u16(raw, off)
        writable = tuple(raw[off : off + n_w])
        off += n_w
        n_r, off = _read_compact_u16(raw, off)
        readonly = tuple(raw[off : off + n_r])
        off += n_r
        lookups.append(AddressTableLookup(account_key, writable, readonly))
    if off != len(raw):
        raise ValueError("trailing bytes after the versioned message")
    return VersionedMessage(
        version=version,
        num_required_signatures=num_sigs,
        num_readonly_signed=ro_signed,
        num_readonly_unsigned=ro_unsigned,
        static_account_keys=tuple(keys),
        recent_blockhash=blockhash,
        instructions=tuple(instructions),
        address_table_lookups=tuple(lookups),
    )


def decode_versioned_transaction(raw: bytes) -> VersionedTransaction:
    """``compact-u16(n) || n * 64-byte signatures || versioned message``."""
    n_sigs, off = _read_compact_u16(raw, 0)
    signatures = tuple(raw[off + 64 * i : off + 64 * (i + 1)] for i in range(n_sigs))
    off += 64 * n_sigs
    message_bytes = raw[off:]
    message = decode_versioned_message(message_bytes)
    return VersionedTransaction(signatures=signatures, message=message, message_bytes=message_bytes)
