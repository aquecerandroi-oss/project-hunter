"""T4.81 — Address Lookup Tables (ALT): reading them and building the account
key list a v0 message's instruction indexes are resolved against.

Why this module exists: Jupiter reaches the route's accounts — and, since the
desk's first real signal (ZECUSDT, 23/09/2026 11:45 BRT), the **mint and the
ATA** of a ``Create ATA (idempotent)`` — through lookup tables.
``spot_verify`` used to refuse anything it could not see (``ata_account_via_
lookup_table``), which is fail-closed but leaves the desk unable to ever buy.
Here the tables are read and the addresses are checked for real.

The split is deliberate: **resolution is IO (here), verification is pure**
(``spot_verify``). The caller reads the tables once and hands the resolved key
list to the verifier, so the verifier stays testable without a network.

The order is the whole safety of this module — every index in every
instruction is an offset into the list built below, so getting it wrong means
checking a different account than the runtime will execute:

    static_account_keys
    + for each lookup, in message order: table[i] for i in writable_indexes
    + for each lookup, in message order: table[i] for i in readonly_indexes

i.e. **all** the writable addresses of **all** the tables come before the first
readonly one. That is ``AccountKeys::new(static, LoadedAddresses)`` in agave
(``LoadedAddresses::from_iter`` concatenates the two categories separately) and
``MessageAccountKeys([static, loaded.writable, loaded.readonly])`` in
solana-web3.js. ``test_spot_alt.py`` pins it with two tables, and
``test_spot_verify_alt.py`` pins it against the real recorded Jupiter
transaction (its ATA mint is index 18 = the first readonly address).

Account layout of an ALT (``address-lookup-table-interface``): a **fixed**
56-byte header — ``u32`` discriminant (1 = LookupTable), ``u64``
``deactivation_slot``, ``u64`` ``last_extended_slot``, ``u8``
``last_extended_slot_start_index``, ``Option<Pubkey>`` authority, padding —
then the addresses, 32 bytes each. The addresses always start at 56 even when
the table is frozen (``authority = None``, whose serialized meta is only 24
bytes): the offset is a constant of the program, never the deserializer's
cursor.

Fail-closed decisions, all refused **by name**, never skipped:

- the tables are read at ``finalized`` (Astra, T4.81): ``confirmed`` fixes no
  fork, and an extension that only exists on an abandoned fork could put a
  different address at the index we verified (Anza documents this as the ALT
  front-running attack). A table (or an extension) too fresh to be finalized
  is refused as missing / out of range — a missed trade, never a wrong one.
- any ``deactivation_slot != u64::MAX`` is refused, without reading the
  current slot: stricter than the runtime, which still accepts a deactivating
  table during its cooldown.
- one snapshot per table address, read **once** before verification; every
  occurrence of a lookup is expanded against that same snapshot, in the
  message's own order — positions are never deduplicated, sorted or omitted.
  A table cannot be rewritten inside one chain history (the program only
  appends, and the address is a PDA of ``[authority, recent_slot]`` that
  cannot be re-derived after the close cooldown), so an index resolved here
  resolves to the same address at execution.
- caps on tables, loaded positions and total keys, so a hostile message cannot
  turn one verification into hundreds of megabytes of reads.

Not refused, on purpose: the same table address appearing twice in one message
(both occurrences resolve against the same snapshot — no ambiguity), and
duplicate addresses in the final list (the runtime rejects that message
itself; refusing it here would only risk re-blocking the desk with no
wrong-account scenario to point at).
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from hunter_core.logging import get_logger
from hunter_exchanges.jupiter.versioned_tx import VersionedCompiledInstruction, VersionedMessage
from hunter_exchanges.pumpfun.solana_codec import b58encode
from hunter_meme_executor.treasury_rules import TreasurySwapRefused

__all__ = [
    "ALT_PROGRAM_ID",
    "LOOKUP_TABLE_META_SIZE",
    "MAX_ACCOUNT_KEYS",
    "MAX_LOADED_ADDRESSES",
    "MAX_LOOKUP_TABLES",
    "READ_COMMITMENT",
    "LookupTable",
    "LookupTableRpc",
    "account_at",
    "account_keys_for",
    "decode_lookup_table",
    "fetch_lookup_tables",
    "lookup_table_addresses",
    "resolved_account_keys",
    "validated_account_keys",
]

logger = get_logger(__name__)

ALT_PROGRAM_ID = "AddressLookupTab1e1111111111111111111111111"
LOOKUP_TABLE_META_SIZE = 56
"""The addresses start here whatever the authority is (a frozen table's
serialized meta is 24 bytes, but the reserved header stays 56)."""
ACTIVE_DEACTIVATION_SLOT = 2**64 - 1
LOOKUP_TABLE_DISCRIMINANT = 1
MAX_TABLE_ADDRESSES = 256
"""The program's own ceiling; an index is a ``u8``, so 255 is the last one."""
MAX_LOOKUP_TABLES = 8
MAX_LOADED_ADDRESSES = 128
MAX_ACCOUNT_KEYS = 256
READ_COMMITMENT = "finalized"


class LookupTableRpc(Protocol):
    """The read-only door of ``SolanaTxRpcClient`` (``sendTransaction`` is
    refused there by construction)."""

    def call(self, method: str, params: list[Any]) -> Any: ...


@dataclass(frozen=True, slots=True)
class LookupTable:
    """One snapshot of one table — the only thing indexes are resolved against."""

    address: str
    addresses: tuple[str, ...]


def decode_lookup_table(address: str, *, owner: str, data_base64: str) -> LookupTable:
    if owner != ALT_PROGRAM_ID:
        raise TreasurySwapRefused(f"lookup_table_bad_owner:{address}")
    try:
        data = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TreasurySwapRefused(f"lookup_table_malformed:{address}") from exc
    body = len(data) - LOOKUP_TABLE_META_SIZE
    if body < 0 or body % 32 != 0 or body // 32 > MAX_TABLE_ADDRESSES:
        raise TreasurySwapRefused(f"lookup_table_malformed:{address}")
    if data[21] not in (0, 1):  # the authority's Option tag
        raise TreasurySwapRefused(f"lookup_table_malformed:{address}")
    if int.from_bytes(data[0:4], "little") != LOOKUP_TABLE_DISCRIMINANT:
        raise TreasurySwapRefused(f"lookup_table_uninitialized:{address}")
    if int.from_bytes(data[4:12], "little") != ACTIVE_DEACTIVATION_SLOT:
        raise TreasurySwapRefused(f"lookup_table_deactivated:{address}")
    addresses = tuple(
        b58encode(data[offset : offset + 32])
        for offset in range(LOOKUP_TABLE_META_SIZE, len(data), 32)
    )
    return LookupTable(address, addresses)


def lookup_table_addresses(message: VersionedMessage) -> tuple[str, ...]:
    """Every table the message names, once, in first-appearance order."""
    lookups = message.address_table_lookups
    if len(lookups) > MAX_LOOKUP_TABLES:
        raise TreasurySwapRefused(f"too_many_lookup_tables:{len(lookups)}")
    seen: dict[str, None] = {}
    for lookup in lookups:
        if not lookup.writable_indexes and not lookup.readonly_indexes:
            # The runtime's own ``sanitize`` rejects it; accepting it could
            # never be what unblocks a real route.
            raise TreasurySwapRefused(f"lookup_table_empty:{lookup.account_key}")
        seen[lookup.account_key] = None
    return tuple(seen)


def resolved_account_keys(
    message: VersionedMessage, tables: dict[str, LookupTable]
) -> tuple[str, ...]:
    """The full account key list, in the runtime's order (module docstring).
    Pure: ``tables`` is the snapshot the caller already read."""
    lookups = message.address_table_lookups
    if not lookups:
        return message.static_account_keys
    lookup_table_addresses(message)
    loaded = sum(len(x.writable_indexes) + len(x.readonly_indexes) for x in lookups)
    if loaded > MAX_LOADED_ADDRESSES:
        raise TreasurySwapRefused(f"too_many_loaded_addresses:{loaded}")
    writable: list[str] = []
    readonly: list[str] = []
    for lookup in lookups:
        table = tables.get(lookup.account_key)
        if table is None:
            raise TreasurySwapRefused(f"lookup_table_missing:{lookup.account_key}")
        for bucket, indexes in (
            (writable, lookup.writable_indexes),
            (readonly, lookup.readonly_indexes),
        ):
            for index in indexes:
                if index >= len(table.addresses):
                    raise TreasurySwapRefused(
                        f"lookup_table_index_out_of_range:{table.address}#{index}"
                    )
                bucket.append(table.addresses[index])
    keys = (*message.static_account_keys, *writable, *readonly)
    if len(keys) > MAX_ACCOUNT_KEYS:
        raise TreasurySwapRefused(f"too_many_account_keys:{len(keys)}")
    return keys


def fetch_lookup_tables(
    rpc: LookupTableRpc, addresses: tuple[str, ...], *, commitment: str = READ_COMMITMENT
) -> dict[str, LookupTable]:
    """One ``getMultipleAccounts`` for every table, at ``finalized``."""
    try:
        result = rpc.call(
            "getMultipleAccounts",
            [list(addresses), {"encoding": "base64", "commitment": commitment}],
        )
    except Exception as exc:
        raise TreasurySwapRefused(f"lookup_table_read_failed:{type(exc).__name__}") from exc
    raw = cast("dict[str, Any] | None", result if isinstance(result, dict) else None)
    value = None if raw is None else raw.get("value")
    if not isinstance(value, list) or len(cast("list[Any]", value)) != len(addresses):
        raise TreasurySwapRefused("lookup_table_read_unreadable")
    tables: dict[str, LookupTable] = {}
    for address, entry in zip(addresses, cast("list[Any]", value), strict=True):
        if entry is None:
            raise TreasurySwapRefused(f"lookup_table_missing:{address}")
        if not isinstance(entry, dict):
            raise TreasurySwapRefused(f"lookup_table_unreadable:{address}")
        account = cast("dict[str, Any]", entry)
        data = account.get("data")
        if not isinstance(data, list):
            raise TreasurySwapRefused(f"lookup_table_unreadable:{address}")
        parts = cast("list[Any]", data)
        if len(parts) != 2 or parts[1] != "base64":
            raise TreasurySwapRefused(f"lookup_table_unreadable:{address}")
        tables[address] = decode_lookup_table(
            address, owner=str(account.get("owner", "")), data_base64=str(parts[0])
        )
    return tables


def validated_account_keys(
    message: VersionedMessage, account_keys: Sequence[str] | None
) -> tuple[str, ...]:
    """The list a pure verifier resolves every account index against.

    Without a resolved list only a message with no lookup table can be checked
    (``lookup_tables_unresolved``); a list that does not start with the
    message's own static keys, or whose length is not the message's own
    (static + one entry per lookup position), is not this message's
    (``account_keys_not_the_messages_own``). Every instruction is then
    bounds-checked once, so no later check can read past the list, and a
    top-level program id must be a **static** key — the runtime's own
    ``sanitize`` requires it, so a message that says otherwise never executes.

    What this does **not** do (Astra, T4.81 diff review): authenticate the
    loaded addresses themselves. The suffix is only as trustworthy as the
    resolver that produced it — ``account_keys`` is a trusted input, and the
    only thing that should ever produce it is ``account_keys_for``.
    """
    if account_keys is None:
        if message.address_table_lookups:
            raise TreasurySwapRefused("lookup_tables_unresolved")
        keys = message.static_account_keys
    else:
        keys = tuple(account_keys)
        static = message.static_account_keys
        loaded = sum(
            len(x.writable_indexes) + len(x.readonly_indexes) for x in message.address_table_lookups
        )
        if keys[: len(static)] != static or len(keys) != len(static) + loaded:
            raise TreasurySwapRefused("account_keys_not_the_messages_own")
    for ix in message.instructions:
        if ix.program_id_index >= len(message.static_account_keys):
            raise TreasurySwapRefused("program_via_lookup_table")
        for index in ix.account_indexes:
            if index >= len(keys):
                raise TreasurySwapRefused(f"account_index_out_of_range:{index}")
    return keys


def account_at(keys: Sequence[str], ix: VersionedCompiledInstruction, position: int) -> str | None:
    """The account at ``position`` of the instruction — ``None`` only when the
    instruction has no such position. The index itself is always in range:
    ``validated_account_keys`` bounds-checked it before any check ran."""
    if position >= len(ix.account_indexes):
        return None
    return keys[ix.account_indexes[position]]


def account_keys_for(
    rpc: LookupTableRpc, message: VersionedMessage, *, commitment: str = READ_COMMITMENT
) -> tuple[str, ...]:
    """The resolved account keys of ``message`` — no RPC at all when it has no
    lookup tables. Blocking: the caller runs it off the loop."""
    addresses = lookup_table_addresses(message)
    if not addresses:
        return message.static_account_keys
    tables = fetch_lookup_tables(rpc, addresses, commitment=commitment)
    keys = resolved_account_keys(message, tables)
    logger.info(
        "meme_spot_lookup_tables_resolved",
        tables=len(addresses),
        static_keys=len(message.static_account_keys),
        resolved_keys=len(keys),
        commitment=commitment,
    )
    return keys
