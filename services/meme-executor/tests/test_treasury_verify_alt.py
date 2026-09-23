"""T4.83 — ``verify_swap_transaction`` over accounts that only exist behind an
Address Lookup Table, the same standard the ``spot/1`` desk got in T4.81.

Two defects closed here, both found reviewing T4.81:

1. the treasury refused ``route_account_via_lookup_table`` for any route
   account it could not see as a static key — fail-closed *and* inert, since
   every Jupiter route uses tables;
2. ``_create_ata`` **skipped** the ATA derivation when the mint came from a
   table (``if mint is not None and ...``) — exactly the real capture's shape,
   whose ``CreateIdempotent`` mint is index 18. Whatever the table held there,
   the wallet signed an instruction nobody had checked: it is not a fund
   diversion (the Associated Token program derives the address on chain) but
   it is a check that could not fail.

Pure: the table is handed in as an already-read snapshot, exactly as
``treasury_send`` hands the resolved key list to the verifier. No network.

The table's own contents were never captured (the fixture's
``addressesByLookupTableAddress`` is null), so every snapshot here is
synthetic — what the ordering tests prove is the **index arithmetic** on a
real message: under the runtime's order (static + all writable + all readonly)
index 18 is the first readonly address, table slot 11.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path

import pytest

from hunter_exchanges.jupiter.versioned_tx import (
    VersionedCompiledInstruction,
    VersionedMessage,
    decode_versioned_transaction,
)
from hunter_exchanges.pumpfun.solana_codec import TOKEN_PROGRAM_ID, associated_token_address
from hunter_meme_executor.spot_alt import LookupTable, resolved_account_keys
from hunter_meme_executor.treasury_rules import USDC_MINT, TreasurySwapRefused
from hunter_meme_executor.treasury_verify import SwapIntent, verify_swap_transaction

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
ATA_IX = 2  # AssociatedToken.CreateIdempotent — its mint is account index 18
ROUTE_IX = 3
MINT_SLOT = 11
"""Table slot the real message's ``CreateIdempotent`` mint resolves to."""
LOADED_INDEX = 19
LOADED_SLOT = 139
"""Another loaded position (index 19 = the second readonly address, slot 139),
used when the ATA's own mint must stay valid so a later check can speak."""
STRANGER_ATA = filler(666)
"""Somebody else's token account — a plausible route destination."""


def _real_message() -> VersionedMessage:
    payload = json.loads((FIXTURES / "jupiter_swap_usdc_to_sol_real.json").read_text("utf-8"))
    return decode_versioned_transaction(base64.b64decode(payload["swapTransaction"])).message


def _tables(message: VersionedMessage, addresses: tuple[str, ...]) -> dict[str, LookupTable]:
    address = message.address_table_lookups[0].account_key
    return {address: LookupTable(address, addresses)}


def _keys(message: VersionedMessage, addresses: tuple[str, ...]) -> tuple[str, ...]:
    return resolved_account_keys(message, _tables(message, addresses))


def _readonly_first(message: VersionedMessage, tables: dict[str, LookupTable]) -> tuple[str, ...]:
    """The wrong order — what a verifier that read the runtime backwards would
    check. Only ever used to prove our order is not that one."""
    readonly: list[str] = []
    writable: list[str] = []
    for lookup in message.address_table_lookups:
        table = tables[lookup.account_key]
        readonly += [table.addresses[i] for i in lookup.readonly_indexes]
        writable += [table.addresses[i] for i in lookup.writable_indexes]
    return (*message.static_account_keys, *readonly, *writable)


def _with(message: VersionedMessage, index: int, **fields: object) -> VersionedMessage:
    ixs = list(message.instructions)
    ixs[index] = replace(ixs[index], **fields)  # type: ignore[arg-type]
    return replace(message, instructions=tuple(ixs))


def _refused(
    message: VersionedMessage, keys: tuple[str, ...] | None, intent: SwapIntent = INTENT
) -> str:
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_swap_transaction(message, intent=intent, account_keys=keys)
    return excinfo.value.reason


# ------------------------------------------------- (2) the check that did not check
def test_an_ata_whose_mint_comes_from_a_table_is_derived_not_skipped() -> None:
    """The regression: the real capture's ``CreateIdempotent`` mint is index 18
    (table slot 11). With WSOL there the static ATA at index 1 derives from it."""
    message = _real_message()
    keys = _keys(message, table_addresses(256, {MINT_SLOT: WSOL}))
    assert keys[18] == WSOL
    verified = verify_swap_transaction(message, intent=INTENT, account_keys=keys)
    assert verified.route_kind == "route"
    assert verified.ata_creates == 1
    assert verified.closes_wsol_ata is True


def test_an_ata_whose_mint_and_address_disagree_is_refused_not_skipped() -> None:
    """A tampered ``/swap`` names USDC as the ``CreateIdempotent`` mint while
    the ATA account stays the wallet's WSOL ATA. Before T4.83 this verified
    (the mint was behind the table, so the derivation was skipped) and the
    wallet signed an instruction nobody had checked — on chain the Associated
    Token program derives the address itself and rejects the pair, so what is
    actually lost is the transaction's fee, not the rent (Astra, T4.83: the
    original ressalva overstated this). The point stands: a check that cannot
    fail is not a check."""
    message = _real_message()
    keys = _keys(message, table_addresses(256, {MINT_SLOT: USDC_MINT}))
    assert _refused(message, keys) == "ata_address_mismatch"


def test_a_consistent_ata_of_a_third_mint_is_still_accepted_by_design() -> None:
    """The residual limit, pinned on purpose (Astra, T4.83): the check is the
    **derivation**, not an allow-list of mints. A ``/swap`` that creates the
    wallet's correctly derived ATA of some other mint — both accounts loaded
    from the table — still verifies, and the wallet pays ~0,002 SOL of rent
    for an account it owns (recoverable by closing it).

    Not closed here because restricting the mint to {USDC, WSOL} is a new
    rule, not this task's, and re-inerting the treasury is the failure T4.81
    was about. What bounds it meanwhile: ``MAX_ATA_CREATES`` (3) and the
    post-simulation SOL invariant (``check_simulated_balances``, 0,01 SOL of
    total allowance) — and the route itself still has to pay into the
    wallet's own WSOL ATA."""
    third_mint = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"  # WIF
    third_ata = associated_token_address(WALLET, third_mint, token_program=TOKEN_PROGRAM_ID)
    message = _real_message()
    hostile = _with(message, ATA_IX, account_indexes=(0, LOADED_INDEX, 0, 18, 4, 7))
    keys = _keys(hostile, table_addresses(256, {MINT_SLOT: third_mint, LOADED_SLOT: third_ata}))
    assert verify_swap_transaction(hostile, intent=INTENT, account_keys=keys).ata_creates == 1


def test_an_ata_account_that_comes_from_a_table_is_derived_too() -> None:
    """Now the mirror image: the ATA *account* behind the table, the mint
    static. Nothing is trusted because it was loaded."""
    message = _real_message()
    ata_accounts = (0, 18, 0, 12, 4, 7)  # ata <- index 18, mint <- USDC (static 12)
    hostile = _with(message, ATA_IX, account_indexes=ata_accounts)
    stranger = _keys(hostile, table_addresses(256, {MINT_SLOT: STRANGER_ATA}))
    assert _refused(hostile, stranger) == "ata_address_mismatch"
    ours = _keys(hostile, table_addresses(256, {MINT_SLOT: USDC_ATA}))
    assert verify_swap_transaction(hostile, intent=INTENT, account_keys=ours).ata_creates == 1


# ------------------------------------------- (1) the route is no longer inert
def test_a_route_source_reached_through_a_table_verifies() -> None:
    """``route_account_via_lookup_table`` is gone: a source that only exists in
    the table is checked against the derivation, not refused for being loaded."""
    message = _real_message()
    accounts = list(message.instructions[ROUTE_IX].account_indexes)
    accounts[2] = LOADED_INDEX  # source_token_account <- a loaded slot
    hostile = _with(message, ROUTE_IX, account_indexes=tuple(accounts))
    keys = _keys(hostile, table_addresses(256, {MINT_SLOT: WSOL, LOADED_SLOT: USDC_ATA}))
    assert verify_swap_transaction(hostile, intent=INTENT, account_keys=keys).route_kind == "route"


def test_a_route_destination_from_a_table_that_is_not_our_ata_is_refused() -> None:
    message = _real_message()
    accounts = list(message.instructions[ROUTE_IX].account_indexes)
    accounts[3] = LOADED_INDEX  # destination_token_account <- a loaded slot
    hostile = _with(message, ROUTE_IX, account_indexes=tuple(accounts))
    keys = _keys(hostile, table_addresses(256, {MINT_SLOT: WSOL, LOADED_SLOT: STRANGER_ATA}))
    assert _refused(hostile, keys) == "route_destination_not_wsol_ata"


def test_a_route_authority_from_a_table_that_is_not_the_wallet_is_refused() -> None:
    message = _real_message()
    accounts = list(message.instructions[ROUTE_IX].account_indexes)
    accounts[1] = LOADED_INDEX
    hostile = _with(message, ROUTE_IX, account_indexes=tuple(accounts))
    keys = _keys(hostile, table_addresses(256, {MINT_SLOT: WSOL, LOADED_SLOT: STRANGER_ATA}))
    assert _refused(hostile, keys) == "route_authority_not_wallet"


def test_a_close_account_of_a_table_account_that_is_not_our_wsol_ata_is_refused() -> None:
    message = _real_message()
    close_ix = len(message.instructions) - 1
    hostile = _with(message, close_ix, account_indexes=(LOADED_INDEX, 0, 0))
    keys = _keys(hostile, table_addresses(256, {MINT_SLOT: WSOL, LOADED_SLOT: STRANGER_ATA}))
    assert _refused(hostile, keys) == "close_account_not_wsol_ata"


# ------------------------------------------------------------- the key list itself
def test_a_message_with_tables_and_no_resolved_keys_is_refused() -> None:
    assert _refused(_real_message(), None) == "lookup_tables_unresolved"


def test_a_key_list_that_is_not_this_messages_own_is_refused() -> None:
    message = _real_message()
    keys = _keys(message, table_addresses(256, {MINT_SLOT: WSOL}))
    assert _refused(message, (filler(1), *keys[1:])) == "account_keys_not_the_messages_own"
    assert _refused(message, (*keys, filler(2))) == "account_keys_not_the_messages_own"


def test_an_index_past_the_resolved_list_is_refused() -> None:
    message = _real_message()
    keys = _keys(message, table_addresses(256, {MINT_SLOT: WSOL}))
    hostile = _with(message, ATA_IX, account_indexes=(0, 1, 0, 99, 4, 7))
    assert _refused(hostile, keys) == "account_index_out_of_range:99"


def test_a_program_reached_through_a_table_is_still_refused() -> None:
    message = _real_message()
    keys = _keys(message, table_addresses(256, {MINT_SLOT: WSOL}))
    hostile = replace(
        message,
        instructions=(*message.instructions, VersionedCompiledInstruction(18, (0,), b"\x01")),
    )
    assert _refused(hostile, keys) == "program_via_lookup_table"


# --------------------------------------------------------------- the ordering
def test_readonly_first_resolution_would_verify_an_ata_of_another_mint() -> None:
    """The mutation that must break: with ``writable`` first (the runtime's
    order) index 18 is table slot 11; with the segments swapped it is slot 243.
    Put WSOL at 243 and USDC at 11 and the swapped order signs a message whose
    ``CreateIdempotent`` mint is not the one that will execute."""
    message = _real_message()
    addresses = table_addresses(256, {MINT_SLOT: USDC_MINT, 243: WSOL})
    tables = _tables(message, addresses)
    ours = resolved_account_keys(message, tables)
    assert ours[18] == USDC_MINT
    assert _refused(message, ours) == "ata_address_mismatch"

    wrong = _readonly_first(message, tables)
    assert wrong[18] == WSOL
    assert verify_swap_transaction(message, intent=INTENT, account_keys=wrong).ata_creates == 1


def test_the_runtime_order_is_all_writable_then_all_readonly() -> None:
    message = _real_message()
    addresses = table_addresses(256, {MINT_SLOT: WSOL})
    keys = _keys(message, addresses)
    assert keys[:15] == message.static_account_keys
    assert keys[15:22] == (
        addresses[244],
        addresses[138],
        addresses[137],
        WSOL,
        addresses[139],
        addresses[246],
        addresses[243],
    )


# ------------------------------------------------------------- the regression
def test_a_transaction_with_no_lookup_table_verifies_exactly_as_before() -> None:
    """A message with no table at all: the resolved list is the static one, and
    passing it explicitly changes nothing."""
    message = _no_table_message()
    without = verify_swap_transaction(message, intent=INTENT)
    explicit = verify_swap_transaction(
        message, intent=INTENT, account_keys=message.static_account_keys
    )
    assert without == explicit
    assert without.route_kind == "route"
    assert resolved_account_keys(message, {}) == message.static_account_keys


def _no_table_message() -> VersionedMessage:
    """The real capture with its single lookup emptied — every account it uses
    resolved as a static key."""
    message = _real_message()
    keys = _keys(message, table_addresses(256, {MINT_SLOT: WSOL}))
    return replace(message, static_account_keys=keys, address_table_lookups=())
