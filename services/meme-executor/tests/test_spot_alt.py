"""T4.81 — ``spot_alt``: reading the Address Lookup Tables of a Jupiter v0
transaction and building the account-key list every instruction index is
resolved against. Pure tests plus a fake RPC (no network, no key, no database).

The one rule that can silently authorise the wrong account is the **order**:
static keys, then every table's ``writable`` addresses (tables in message
order), then every table's ``readonly`` addresses.
``test_the_order_is_the_static_keys_then_writable_then_readonly`` and
``test_two_tables_put_every_writable_before_every_readonly_in_table_order``
pin it down; ``test_spot_verify_alt.py`` shows what getting it wrong buys.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

from hunter_exchanges.jupiter.versioned_tx import AddressTableLookup, VersionedMessage
from hunter_meme_executor.spot_alt import (
    ALT_PROGRAM_ID,
    MAX_ACCOUNT_KEYS,
    MAX_LOADED_ADDRESSES,
    MAX_LOOKUP_TABLES,
    LookupTable,
    account_keys_for,
    decode_lookup_table,
    lookup_table_addresses,
    resolved_account_keys,
)
from hunter_meme_executor.treasury_rules import TreasurySwapRefused

from .spot_tx_fixtures import (
    ALT_KEYS,
    ALT_TABLE,
    ALT_TABLE_ADDRESSES,
    ALT_TABLE_B,
    WIF,
    WIF_ATA,
    alt_buy_message,
    alt_lookup,
    buy_message,
    filler,
    lookup_table_data,
    table_addresses,
)

pytestmark = pytest.mark.unit


@dataclass
class FakeAltRpc:
    """``getMultipleAccounts`` over a dictionary of base64 account data."""

    accounts: dict[str, str]
    owner: str = ALT_PROGRAM_ID
    error: Exception | None = None
    calls: list[tuple[str, Any]] = field(default_factory=lambda: list[tuple[str, Any]]())

    def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        if self.error is not None:
            raise self.error
        value = [
            None
            if address not in self.accounts
            else {
                "data": [self.accounts[address], "base64"],
                "owner": self.owner,
                "lamports": 1_000_000,
                "executable": False,
            }
            for address in params[0]
        ]
        return {"context": {"slot": 7}, "value": value}


def _rpc(
    addresses: tuple[str, ...] = ALT_TABLE_ADDRESSES, *, table: str = ALT_TABLE, **kwargs: Any
) -> FakeAltRpc:
    return FakeAltRpc({table: lookup_table_data(addresses, **kwargs)})


def _refused(callable_: Any, *args: Any, **kwargs: Any) -> str:
    with pytest.raises(TreasurySwapRefused) as excinfo:
        callable_(*args, **kwargs)
    return excinfo.value.reason


# ------------------------------------------------------------------ decoding
def test_a_real_shaped_table_decodes_its_addresses_after_the_56_byte_header() -> None:
    table = decode_lookup_table(
        ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=lookup_table_data(ALT_TABLE_ADDRESSES)
    )
    assert table.address == ALT_TABLE
    assert table.addresses == ALT_TABLE_ADDRESSES
    assert table.addresses[5] == WIF_ATA and table.addresses[7] == WIF


def test_a_table_owned_by_another_program_is_refused_by_name() -> None:
    reason = _refused(
        decode_lookup_table,
        ALT_TABLE,
        owner="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        data_base64=lookup_table_data(ALT_TABLE_ADDRESSES),
    )
    assert reason == f"lookup_table_bad_owner:{ALT_TABLE}"


def test_an_uninitialized_table_is_refused_by_name() -> None:
    data = lookup_table_data(ALT_TABLE_ADDRESSES, discriminant=0)
    reason = _refused(decode_lookup_table, ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=data)
    assert reason == f"lookup_table_uninitialized:{ALT_TABLE}"


@pytest.mark.parametrize("trailing", [b"\x01", b"\x00" * 31])
def test_a_table_whose_body_is_not_a_whole_number_of_addresses_is_refused(trailing: bytes) -> None:
    data = lookup_table_data(ALT_TABLE_ADDRESSES, trailing=trailing)
    reason = _refused(decode_lookup_table, ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=data)
    assert reason == f"lookup_table_malformed:{ALT_TABLE}"


def test_a_table_shorter_than_its_own_header_is_refused() -> None:
    data = base64.b64encode(bytes(40)).decode("ascii")
    reason = _refused(decode_lookup_table, ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=data)
    assert reason == f"lookup_table_malformed:{ALT_TABLE}"


def test_a_deactivated_table_is_refused_even_before_the_cooldown_ends() -> None:
    """Stricter than the runtime on purpose: a table with any deactivation slot
    at all is refused, so nothing needs to be decided against a clock."""
    data = lookup_table_data(ALT_TABLE_ADDRESSES, deactivation_slot=123_456_789)
    reason = _refused(decode_lookup_table, ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=data)
    assert reason == f"lookup_table_deactivated:{ALT_TABLE}"


# ------------------------------------------------------------------ ordering
def test_a_message_with_no_lookup_tables_resolves_to_its_own_static_keys() -> None:
    message = buy_message()
    assert resolved_account_keys(message, {}) == message.static_account_keys


def test_the_order_is_the_static_keys_then_writable_then_readonly() -> None:
    message = alt_buy_message()
    table = decode_lookup_table(
        ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=lookup_table_data(ALT_TABLE_ADDRESSES)
    )
    keys = resolved_account_keys(message, {ALT_TABLE: table})
    assert keys[: len(ALT_KEYS)] == ALT_KEYS
    assert keys[8] == WIF_ATA  # the single writable index (table slot 5)
    assert keys[9] == WIF  # the single readonly index (table slot 7)
    assert len(keys) == len(ALT_KEYS) + 2


def test_two_tables_put_every_writable_before_every_readonly_in_table_order() -> None:
    """The runtime concatenates ``[static, loaded.writable, loaded.readonly]``,
    and ``loaded`` accumulates table by table — **not** table-by-table pairs."""
    first = table_addresses(8, {1: filler(101), 2: filler(102)})
    second = table_addresses(8, {3: filler(201), 4: filler(202)})
    message = replace(
        alt_buy_message(),
        address_table_lookups=(
            AddressTableLookup(ALT_TABLE, (1,), (2,)),
            AddressTableLookup(ALT_TABLE_B, (3,), (4,)),
        ),
    )
    tables = {
        ALT_TABLE: LookupTable(ALT_TABLE, first),
        ALT_TABLE_B: LookupTable(ALT_TABLE_B, second),
    }
    keys = resolved_account_keys(message, tables)
    assert keys[len(ALT_KEYS) :] == (first[1], second[3], first[2], second[4])
    # the shape that would be wrong: W1, R1, W2, R2
    assert keys[len(ALT_KEYS) :] != (first[1], first[2], second[3], second[4])


def test_a_lookup_that_selects_nothing_is_refused_by_name() -> None:
    """Astra (T4.81): the runtime's ``sanitize`` rejects a lookup with both
    index lists empty, so accepting it can never be what unblocks a route."""
    message = replace(
        alt_buy_message(), address_table_lookups=(alt_lookup(writable=(), readonly=()),)
    )
    assert _refused(lookup_table_addresses, message) == f"lookup_table_empty:{ALT_TABLE}"
    assert _refused(resolved_account_keys, message, {}) == f"lookup_table_empty:{ALT_TABLE}"


def test_an_index_outside_the_table_is_refused_by_name() -> None:
    message = replace(
        alt_buy_message(), address_table_lookups=(alt_lookup(writable=(99,), readonly=()),)
    )
    table = LookupTable(ALT_TABLE, ALT_TABLE_ADDRESSES)
    reason = _refused(resolved_account_keys, message, {ALT_TABLE: table})
    assert reason == f"lookup_table_index_out_of_range:{ALT_TABLE}#99"


def test_a_table_the_snapshot_does_not_have_is_refused_never_skipped() -> None:
    reason = _refused(resolved_account_keys, alt_buy_message(), {})
    assert reason == f"lookup_table_missing:{ALT_TABLE}"


def test_more_tables_than_the_cap_are_refused() -> None:
    lookups = tuple(
        AddressTableLookup(filler(500 + i), (0,), ()) for i in range(MAX_LOOKUP_TABLES + 1)
    )
    message = replace(alt_buy_message(), address_table_lookups=lookups)
    assert _refused(lookup_table_addresses, message).startswith("too_many_lookup_tables:")
    assert _refused(resolved_account_keys, message, {}).startswith("too_many_lookup_tables:")


def test_more_loaded_addresses_than_the_cap_are_refused() -> None:
    writable = tuple(range(MAX_LOADED_ADDRESSES // 2 + 1))
    readonly = tuple(range(MAX_LOADED_ADDRESSES // 2 + 1))
    message = replace(
        alt_buy_message(),
        address_table_lookups=(alt_lookup(writable=writable, readonly=readonly),),
    )
    reason = _refused(resolved_account_keys, message, {ALT_TABLE: LookupTable(ALT_TABLE, ())})
    assert reason.startswith("too_many_loaded_addresses:")


# --------------------------------------------------------------------- the IO
def test_a_message_without_lookup_tables_never_touches_the_rpc() -> None:
    rpc = FakeAltRpc({})
    assert account_keys_for(rpc, buy_message()) == buy_message().static_account_keys
    assert rpc.calls == []


def test_one_getmultipleaccounts_serves_every_table_once_at_finalized() -> None:
    """Astra's must-fix: ``confirmed`` does not fix a fork, so the snapshot the
    signature is verified against is read at ``finalized``."""
    rpc = _rpc()
    message = replace(
        alt_buy_message(),
        address_table_lookups=(alt_lookup(), alt_lookup(writable=(), readonly=(7,))),
    )
    keys = account_keys_for(rpc, message)
    assert [method for method, _ in rpc.calls] == ["getMultipleAccounts"]
    assert rpc.calls[0][1][0] == [ALT_TABLE]  # asked once, not twice
    assert rpc.calls[0][1][1] == {"encoding": "base64", "commitment": "finalized"}
    assert keys[8] == WIF_ATA and keys[9] == WIF and keys[10] == WIF


def test_an_option_tag_that_is_neither_none_nor_some_is_refused() -> None:
    data = base64.b64decode(lookup_table_data(ALT_TABLE_ADDRESSES))
    broken = base64.b64encode(data[:21] + b"\x07" + data[22:]).decode("ascii")
    reason = _refused(decode_lookup_table, ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=broken)
    assert reason == f"lookup_table_malformed:{ALT_TABLE}"


def test_a_table_with_more_than_256_addresses_is_refused() -> None:
    data = lookup_table_data(table_addresses(257, {}))
    reason = _refused(decode_lookup_table, ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=data)
    assert reason == f"lookup_table_malformed:{ALT_TABLE}"


def test_a_missing_table_account_is_refused_by_name() -> None:
    reason = _refused(account_keys_for, FakeAltRpc({}), alt_buy_message())
    assert reason == f"lookup_table_missing:{ALT_TABLE}"


def test_an_rpc_that_raises_is_refused_by_name_never_resolved_blind() -> None:
    rpc = _rpc()
    rpc.error = TimeoutError("rpc down")
    reason = _refused(account_keys_for, rpc, alt_buy_message())
    assert reason == "lookup_table_read_failed:TimeoutError"


def test_a_reply_that_is_not_a_list_of_accounts_is_refused_by_name() -> None:
    class Broken(FakeAltRpc):
        def call(self, method: str, params: list[Any]) -> Any:
            return {"context": {"slot": 1}, "value": None}

    reason = _refused(account_keys_for, Broken({}), alt_buy_message())
    assert reason == "lookup_table_read_unreadable"


def test_a_table_served_with_another_owner_is_refused_through_the_rpc_path() -> None:
    rpc = _rpc()
    rpc.owner = "11111111111111111111111111111111"
    assert (
        _refused(account_keys_for, rpc, alt_buy_message()) == f"lookup_table_bad_owner:{ALT_TABLE}"
    )


def test_the_resolved_keys_of_the_desks_own_shape_are_the_ones_the_runtime_would_build() -> None:
    message: VersionedMessage = alt_buy_message()
    keys = account_keys_for(_rpc(), message)
    assert keys == (*ALT_KEYS, WIF_ATA, WIF)


# -------------------------------------------------------------- Astra's edges
def test_a_frozen_table_decodes_the_same_way() -> None:
    """``authority = None``: the serialized meta is 24 bytes, but the addresses
    still start at the constant 56 — decoding from the deserializer's cursor
    would read 32 bytes of padding as the first address."""
    data = base64.b64decode(lookup_table_data(ALT_TABLE_ADDRESSES))
    frozen = base64.b64encode(data[:21] + b"\x00" + bytes(34) + data[56:]).decode("ascii")
    table = decode_lookup_table(ALT_TABLE, owner=ALT_PROGRAM_ID, data_base64=frozen)
    assert table.addresses == ALT_TABLE_ADDRESSES


def test_a_repeated_index_inside_one_list_loads_the_address_twice() -> None:
    """The runtime keeps every position; nothing here deduplicates."""
    message = replace(
        alt_buy_message(), address_table_lookups=(alt_lookup(writable=(5, 5), readonly=(7,)),)
    )
    keys = resolved_account_keys(message, {ALT_TABLE: LookupTable(ALT_TABLE, ALT_TABLE_ADDRESSES)})
    assert keys[len(ALT_KEYS) :] == (WIF_ATA, WIF_ATA, WIF)


def test_the_same_table_twice_with_disjoint_selections_keeps_both_occurrences() -> None:
    message = replace(
        alt_buy_message(),
        address_table_lookups=(
            alt_lookup(writable=(5,), readonly=()),
            alt_lookup(writable=(), readonly=(7,)),
        ),
    )
    rpc = _rpc()
    keys = account_keys_for(rpc, message)
    assert keys[len(ALT_KEYS) :] == (WIF_ATA, WIF)
    assert rpc.calls[0][1][0] == [ALT_TABLE]


def test_an_index_exactly_at_the_end_of_the_table_is_refused() -> None:
    size = len(ALT_TABLE_ADDRESSES)
    message = replace(
        alt_buy_message(), address_table_lookups=(alt_lookup(writable=(size,), readonly=()),)
    )
    table = LookupTable(ALT_TABLE, ALT_TABLE_ADDRESSES)
    reason = _refused(resolved_account_keys, message, {ALT_TABLE: table})
    assert reason == f"lookup_table_index_out_of_range:{ALT_TABLE}#{size}"


def test_the_total_key_cap_counts_the_static_keys_too() -> None:
    """``MAX_LOADED_ADDRESSES`` bounds what the tables add; this one bounds the
    whole list, so a message with a huge static half is refused as well."""
    table = LookupTable(ALT_TABLE, table_addresses(256, {}))
    loaded = alt_lookup(writable=tuple(range(MAX_LOADED_ADDRESSES)), readonly=())

    def message_with(static_keys: int) -> VersionedMessage:
        extra = tuple(filler(1000 + i) for i in range(static_keys - len(ALT_KEYS)))
        return replace(
            alt_buy_message(),
            static_account_keys=(*ALT_KEYS, *extra),
            address_table_lookups=(loaded,),
        )

    fits = message_with(MAX_ACCOUNT_KEYS - MAX_LOADED_ADDRESSES)
    assert len(resolved_account_keys(fits, {ALT_TABLE: table})) == MAX_ACCOUNT_KEYS
    over = message_with(MAX_ACCOUNT_KEYS - MAX_LOADED_ADDRESSES + 1)
    assert _refused(resolved_account_keys, over, {ALT_TABLE: table}) == (
        f"too_many_account_keys:{MAX_ACCOUNT_KEYS + 1}"
    )
