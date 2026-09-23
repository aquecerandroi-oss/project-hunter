"""T4.81 — ``verify_spot_swap_tx`` over accounts that only exist behind an
Address Lookup Table: the shape that refused the ``spot/1`` desk's first real
signal (ZECUSDT, 23/09/2026 11:45 BRT, ``ata_account_via_lookup_table``).

Pure: the tables are handed in as an already-read snapshot, exactly as
``spot_send`` hands the resolved key list to the verifier. No network.

The two tests that matter most are the ordering ones: the real recorded
Jupiter transaction (its ``Create ATA`` mint is index 18 — the **first
readonly** loaded address) and the trap where readonly-first resolution would
send the bought tokens to somebody else's token account and still verify.
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
from hunter_meme_executor.spot_verify import SpotSwapIntent, verify_spot_swap_tx
from hunter_meme_executor.treasury_rules import USDC_MINT, TreasurySwapRefused

from .spot_tx_fixtures import (
    ALT_KEYS,
    ALT_TABLE,
    ALT_TABLE_ADDRESSES,
    OUT,
    TICKET,
    WALLET,
    WIF,
    WIF_ATA,
    WSOL,
    alt_buy_message,
    alt_lookup,
    buy_message,
    filler,
    table_addresses,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parent / "fixtures"
ATTACKER_ATA = filler(666)
"""Somebody else's token account — a plausible route destination."""

BUY_INTENT = SpotSwapIntent(
    wallet=WALLET,
    input_mint=WSOL,
    output_mint=WIF,
    in_amount=TICKET,
    min_quoted_out=OUT,
    max_slippage_bps=50,
)


def _keys(message: VersionedMessage, addresses: tuple[str, ...]) -> tuple[str, ...]:
    return resolved_account_keys(message, {ALT_TABLE: LookupTable(ALT_TABLE, addresses)})


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


def _refused(message: VersionedMessage, keys: tuple[str, ...], intent: SpotSwapIntent) -> str:
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(message, intent=intent, account_keys=keys)
    return excinfo.value.reason


# ------------------------------------------------------- the desk's own shape
def test_a_buy_whose_ata_and_mint_come_from_a_table_verifies() -> None:
    message = alt_buy_message()
    verified = verify_spot_swap_tx(
        message, intent=BUY_INTENT, account_keys=_keys(message, ALT_TABLE_ADDRESSES)
    )
    assert verified.route_kind == "route"
    assert verified.ata_creates == 2
    assert verified.wraps_sol is True and verified.unwraps_sol is False
    assert verified.in_amount == TICKET


def test_an_ata_from_a_table_whose_derivation_is_wrong_is_refused() -> None:
    """The mint is ours, the ATA is not derived from it: rent paid into an
    account the wallet does not own."""
    message = alt_buy_message()
    addresses = table_addresses(16, {5: ATTACKER_ATA, 7: WIF})
    assert _refused(message, _keys(message, addresses), BUY_INTENT) == "ata_address_mismatch"


def test_an_ata_from_a_table_derived_for_another_mint_is_refused() -> None:
    other = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    addresses = table_addresses(
        16,
        {5: associated_token_address(WALLET, other, token_program=TOKEN_PROGRAM_ID), 7: other},
    )
    message = alt_buy_message()
    # the derivation itself is consistent, so what refuses it is the route:
    # the swap's output would land in a token account of another mint.
    assert _refused(message, _keys(message, addresses), BUY_INTENT) == "route_destination_mismatch"


def test_a_route_destination_from_a_table_that_is_not_our_ata_is_refused() -> None:
    message = _without_wif_ata(alt_buy_message())
    addresses = table_addresses(16, {5: ATTACKER_ATA, 7: WIF})
    assert _refused(message, _keys(message, addresses), BUY_INTENT) == "route_destination_mismatch"


def test_a_program_id_reached_through_a_table_is_refused() -> None:
    """Whatever the table holds — the allow-list included — a top-level program
    id must be a static key; the runtime's own ``sanitize`` says so."""
    message = alt_buy_message()
    hostile = replace(
        message,
        instructions=(
            *message.instructions[:-1],
            VersionedCompiledInstruction(8, (3, 0, 0), bytes([9])),
        ),
    )
    assert _refused(hostile, _keys(hostile, ALT_TABLE_ADDRESSES), BUY_INTENT) == (
        "program_via_lookup_table"
    )


def test_an_index_past_the_resolved_list_is_refused() -> None:
    message = alt_buy_message()
    hostile = replace(
        message,
        instructions=(
            *message.instructions[:3],
            VersionedCompiledInstruction(4, (0, 8, 0, 99, 5, 2), b"\x01"),
            *message.instructions[4:],
        ),
    )
    keys = _keys(message, ALT_TABLE_ADDRESSES)
    assert _refused(hostile, keys, BUY_INTENT) == "account_index_out_of_range:99"


def test_a_key_list_that_is_not_this_messages_own_is_refused() -> None:
    message = alt_buy_message()
    foreign = (filler(1), *message.static_account_keys[1:], WIF_ATA, WIF)
    assert _refused(message, foreign, BUY_INTENT) == "account_keys_not_the_messages_own"


# --------------------------------------------------------------- the ordering
def test_readonly_first_resolution_would_pay_the_route_into_a_stranger_account() -> None:
    """The trap: with ``writable`` first (the runtime's order) the route's
    destination is ``ATTACKER_ATA`` and the buy is refused. With the segments
    swapped it resolves to our own WIF ATA and verifies — a verifier in that
    order would sign a transaction that hands the tokens to somebody else."""
    message = _without_wif_ata(alt_buy_message())
    addresses = table_addresses(16, {5: ATTACKER_ATA, 7: WIF_ATA})
    tables = {ALT_TABLE: LookupTable(ALT_TABLE, addresses)}
    ours = resolved_account_keys(message, tables)
    assert ours[8] == ATTACKER_ATA
    assert _refused(message, ours, BUY_INTENT) == "route_destination_mismatch"

    wrong = _readonly_first(message, tables)
    assert wrong[8] == WIF_ATA
    assert verify_spot_swap_tx(message, intent=BUY_INTENT, account_keys=wrong).route_kind == "route"


def test_the_real_jupiter_transaction_resolves_its_ata_mint_to_wsol_and_verifies() -> None:
    """The recorded mainnet ``POST /swap`` (nothing signed): 15 static keys,
    one table with writable ``(244, 138, 137)`` and readonly
    ``(11, 139, 246, 243)``, and a ``CreateIdempotent`` whose mint is index 18.

    The table's own contents were not captured (the fixture's
    ``addressesByLookupTableAddress`` is null), so the snapshot here is
    synthetic: WSOL is placed at slot 11. What the test proves is therefore the
    **index arithmetic** on a real message — under our order index 18 is the
    first readonly address, table slot 11, and the wallet's WSOL ATA at static
    index 1 derives from it; under the swapped order index 18 would be table
    slot 243 and the same message would be refused."""
    message = _real_message()
    table_address = message.address_table_lookups[0].account_key
    addresses = table_addresses(256, {11: WSOL})
    tables = {table_address: LookupTable(table_address, addresses)}
    keys = resolved_account_keys(message, tables)
    assert keys[15:22] == (
        addresses[244],
        addresses[138],
        addresses[137],
        WSOL,
        addresses[139],
        addresses[246],
        addresses[243],
    )
    verified = verify_spot_swap_tx(message, intent=_REAL_INTENT, account_keys=keys)
    assert verified.route_kind == "route" and verified.ata_creates == 1
    assert verified.unwraps_sol is True

    wrong = _readonly_first(message, tables)
    with pytest.raises(TreasurySwapRefused) as excinfo:
        verify_spot_swap_tx(message, intent=_REAL_INTENT, account_keys=wrong)
    assert excinfo.value.reason == "ata_address_mismatch"


# ------------------------------------------------------------- the regression
def test_a_transaction_with_no_lookup_table_verifies_exactly_as_before() -> None:
    message = buy_message()
    without = verify_spot_swap_tx(message, intent=BUY_INTENT)
    explicit = verify_spot_swap_tx(
        message, intent=BUY_INTENT, account_keys=message.static_account_keys
    )
    assert without == explicit
    assert resolved_account_keys(message, {}) == message.static_account_keys


def test_a_lookup_that_loads_nothing_new_still_verifies_the_static_accounts() -> None:
    message = replace(
        alt_buy_message(),
        instructions=_without_wif_ata(alt_buy_message()).instructions,
        address_table_lookups=(alt_lookup(writable=(5,), readonly=()),),
    )
    keys = _keys(message, ALT_TABLE_ADDRESSES)
    assert keys == (*ALT_KEYS, WIF_ATA)
    assert verify_spot_swap_tx(message, intent=BUY_INTENT, account_keys=keys).ata_creates == 1


# ------------------------------------------------------------------- fixtures
_REAL_INTENT = SpotSwapIntent(
    wallet=WALLET,
    input_mint=USDC_MINT,
    output_mint=WSOL,
    in_amount=1_000_000,
    min_quoted_out=9_487_602,
    max_slippage_bps=50,
)


def _real_message() -> VersionedMessage:
    payload = json.loads((FIXTURES / "jupiter_swap_usdc_to_sol_real.json").read_text("utf-8"))
    return decode_versioned_transaction(base64.b64decode(payload["swapTransaction"])).message


def _without_wif_ata(message: VersionedMessage) -> VersionedMessage:
    """``alt_buy_message`` minus the ``Create WIF ATA`` instruction (the account
    already exists), so the route's destination is the first check to speak."""
    return replace(message, instructions=(*message.instructions[:3], *message.instructions[4:]))


def test_a_key_list_longer_than_the_message_asked_for_is_refused() -> None:
    """Astra (T4.81 diff review): the prefix being right is not enough — the
    length must be the message's own (static + one per lookup position)."""
    message = alt_buy_message()
    padded = (*_keys(message, ALT_TABLE_ADDRESSES), filler(9))
    assert _refused(message, padded, BUY_INTENT) == "account_keys_not_the_messages_own"
