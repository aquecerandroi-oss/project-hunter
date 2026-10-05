"""T4.8f: the PumpSwap program redeployed on 2026-10-02 (slot 452654882) added three
**remaining accounts** to ``sell`` — ``pool_v2`` (read-only), a ``buyback_fee_recipient`` of
``GlobalConfig.buyback_fee_recipients`` (read-only) and that recipient's WSOL ATA (writable). Without
them the program answers ``Custom 6062 InvalidPoolV2`` ("pool_v2 remaining account is missing or
invalid"): found by the mainnet simulation of our own sell (05/10), never by the T4.29a fixtures
(the on-chain IDL was not republished; the GitHub one lists 21 accounts).

Parity is read off real post-upgrade sells (Jupiter routes through PumpSwap,
``t48e_rpc_amm_tx_*``): every account, signer/writable flag and the argument bytes of the
PumpSwap ``sell`` instruction, rebuilt by our builder, must equal the chain's.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58decode,
    find_program_address,
    pubkey_bytes,
    serialize_message,
)
from hunter_exchanges.pumpswap.decode import (
    PUMPSWAP_PROGRAM_ID,
    WSOL_MINT,
    Pool,
    decode_global_config,
)
from hunter_exchanges.pumpswap.pdas import pool_v2_address, user_volume_accumulator_address
from hunter_exchanges.pumpswap.sell_event import sell_events_from_transaction
from hunter_exchanges.pumpswap.tx import (
    SELL_ACCOUNT_NAMES,
    SELL_DISCRIMINATOR,
    SELL_REMAINING_ACCOUNT_NAMES,
    PumpSwapSellIntent,
    build_pumpswap_sell_instruction,
    build_sell_message,
)
from hunter_exchanges.pumpswap.verify import UnverifiedTransaction, verify_pumpswap_sell_message

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpswap"
SIGS = ("5A1byFyLnuFA", "5mrYZLam93Kd", "Yi2iyHP47jiP")  # V99d routes through an extra program
# real sells of pools whose ``coin_creator`` is the default pubkey: 23 accounts, no ``pool_v2``
NOCREATOR_SIGS = ("2bYPbC8hziYA", "22nLsgeWxBer", "4mvEcZZp8mj5")
# real POST-UPGRADE sells of cashback pools: 26 accounts, the accumulator pair first
CASHBACK_SIGS = ("5dAf16Nw5mkU", "2cCMbceo4zut")  # 2026-10-04 and 2026-10-03, after the redeploy
BLOCKHASH = "7Pptc9XnPvGCz2SExsdbLzYAWCXbGmYyewGefDCVU4A6"


def _tx(sig12: str) -> dict[str, Any]:
    if sig12 in NOCREATOR_SIGS:
        name = f"t48f_rpc_amm_tx_nocreator_{sig12}_raw.json"
    elif sig12 in CASHBACK_SIGS:
        name = f"t48f_rpc_amm_tx_cashback_sell_{sig12}_raw.json"
    else:
        name = f"t48e_rpc_amm_tx_{sig12}_raw.json"
    return json.loads((FIXTURES / name).read_text())


def _config() -> Any:
    value = json.loads((FIXTURES / "t48f_rpc_global_config_raw.json").read_text())["result"][
        "value"
    ]
    return decode_global_config(value["data"][0], owner=value["owner"])


def _chain_sell(tx: dict[str, Any]) -> tuple[list[str], list[bool], list[bool], bytes]:
    """``(accounts, is_signer, is_writable, data)`` of the PumpSwap ``sell`` in a real tx."""
    message = tx["transaction"]["message"]
    keys = list(message["accountKeys"])
    loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
    n = len(keys)
    header = message["header"]
    keys += list(loaded.get("writable", [])) + list(loaded.get("readonly", []))

    def signer(i: int) -> bool:
        return i < header["numRequiredSignatures"]

    def writable(i: int) -> bool:
        if i < n:
            if i < header["numRequiredSignatures"]:
                return i < header["numRequiredSignatures"] - header["numReadonlySignedAccounts"]
            return i < n - header["numReadonlyUnsignedAccounts"]
        return i - n < len(loaded.get("writable", []))

    # top-level instructions (a direct sell) first, then CPIs (a routed one)
    candidates = list(message["instructions"])
    for group in tx["meta"]["innerInstructions"]:
        candidates += group["instructions"]
    for ix in candidates:
        if keys[ix["programIdIndex"]] != PUMPSWAP_PROGRAM_ID:
            continue
        data = b58decode(ix["data"])
        if data[:8] == SELL_DISCRIMINATOR:
            idx = ix["accounts"]
            return (
                [keys[i] for i in idx],
                [signer(i) for i in idx],
                [writable(i) for i in idx],
                data,
            )
    raise AssertionError("no PumpSwap sell in the transaction")


def _intent_from_chain(tx: dict[str, Any], *, cashback: bool = False) -> PumpSwapSellIntent:
    accounts, _signer, _writable, data = _chain_sell(tx)
    (event,) = sell_events_from_transaction(tx)
    pool = Pool(
        pool_bump=0,
        index=0,
        creator=event.user,
        base_mint=accounts[3],
        quote_mint=accounts[4],
        lp_mint=accounts[3],
        pool_base_token_account=accounts[7],
        pool_quote_token_account=accounts[8],
        lp_supply=0,
        coin_creator=event.coin_creator,
        is_mayhem_mode=False,
        is_cashback_coin=cashback,
    )
    return PumpSwapSellIntent(
        pool_address=accounts[0],
        pool=pool,
        user=accounts[1],
        base_token_program=accounts[11],
        base_amount_in=int.from_bytes(data[8:16], "little"),
        min_quote_amount_out=int.from_bytes(data[16:24], "little"),
        protocol_fee_recipient=accounts[9],
        buyback_fee_recipient=accounts[-2],
    )


@pytest.mark.parametrize("sig", SIGS)
def test_our_sell_instruction_equals_the_real_post_upgrade_one_account_for_account(
    sig: str,
) -> None:
    tx = _tx(sig)
    accounts, signer, writable, data = _chain_sell(tx)
    ix = build_pumpswap_sell_instruction(_intent_from_chain(tx))
    assert len(accounts) == 24 == len(ix.accounts)
    assert [a.pubkey for a in ix.accounts] == accounts
    assert [a.is_writable for a in ix.accounts] == writable
    assert [a.is_signer for a in ix.accounts][1] is True and signer[1] is True
    assert ix.data == data


@pytest.mark.parametrize("sig", SIGS)
def test_the_three_remaining_accounts_are_pool_v2_buyback_recipient_and_its_wsol_ata(
    sig: str,
) -> None:
    accounts, _signer, writable, _data = _chain_sell(_tx(sig))
    base_mint = accounts[3]
    assert accounts[21] == pool_v2_address(base_mint)
    assert (
        accounts[21]
        == find_program_address([b"pool-v2", pubkey_bytes(base_mint)], PUMPSWAP_PROGRAM_ID)[0]
    )
    assert accounts[22] in _config().buyback_fee_recipients
    assert accounts[23] == associated_token_address(
        accounts[22], WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    assert writable[21:] == [False, False, True]
    assert SELL_REMAINING_ACCOUNT_NAMES == ("pool_v2", "buyback_fee_recipient", "buyback_wsol_ata")
    assert len(SELL_ACCOUNT_NAMES) == 21


def test_global_config_decodes_the_eight_buyback_fee_recipients() -> None:
    config = _config()
    assert len(config.buyback_fee_recipients) == 8
    assert config.buyback_fee_recipients[0] == "5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD"
    assert config.buyback_fee_recipients[3] == "3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR"
    assert config.protocol_fee_recipients and config.coin_creator_fee_basis_points == 5


def test_a_truncated_global_config_has_no_buyback_recipients_not_a_crash() -> None:
    """A GlobalConfig that ends before the buyback array (an older layout): ``()`` — and the
    builder refuses by name, never signs a sell without the account the program now demands."""
    value = json.loads((FIXTURES / "t48f_rpc_global_config_raw.json").read_text())["result"][
        "value"
    ]
    raw = base64.b64decode(value["data"][0])[:640]
    short = decode_global_config(base64.b64encode(raw).decode(), owner=value["owner"])
    assert short.buyback_fee_recipients == ()
    assert short.protocol_fee_recipients  # the part it always had still decodes


def _signed_message(sig: str) -> tuple[PumpSwapSellIntent, bytes]:
    intent = _intent_from_chain(_tx(sig))
    message = build_sell_message(
        intent,
        payer=intent.user,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=120_000,
        compute_unit_price_micro_lamports=5_000,
        create_wsol_ata=True,
    )
    return intent, serialize_message(message)


def test_the_verifier_accepts_the_24_account_sell_and_refuses_another_buyback_recipient() -> None:
    intent, raw = _signed_message("5mrYZLam93Kd")
    verify_pumpswap_sell_message(
        raw,
        intent,
        compute_unit_limit_cap=200_000,
        compute_unit_price_cap_micro_lamports=10_000,
        expected_blockhash=BLOCKHASH,
    )
    swapped = replace(intent, buyback_fee_recipient=_config().buyback_fee_recipients[5])
    with pytest.raises(UnverifiedTransaction, match="message_bytes_differ"):
        verify_pumpswap_sell_message(
            raw,
            swapped,
            compute_unit_limit_cap=200_000,
            compute_unit_price_cap_micro_lamports=10_000,
            expected_blockhash=BLOCKHASH,
        )


@pytest.mark.parametrize("sig", NOCREATOR_SIGS)
def test_a_pool_without_a_coin_creator_has_no_pool_v2_account(sig: str) -> None:
    """Real post-upgrade sells of pools whose ``coin_creator`` is the default pubkey carry 23
    accounts: ``pool_v2`` is passed only when the pool has a coin creator (official SDK 1.20.0).
    These three are direct sells of pools quoted in a **custom mint** (not WSOL, not the desk's
    pools), so only the shape of the tail is asserted: the buyback ATA is of the *quote* mint."""
    accounts, _signer, writable, _data = _chain_sell(_tx(sig))
    (event,) = sell_events_from_transaction(_tx(sig))
    assert event.coin_creator == "11111111111111111111111111111111"
    assert accounts[4] != WSOL_MINT and len(accounts) == 23
    assert pool_v2_address(accounts[3]) not in accounts
    assert accounts[-2] in _config().buyback_fee_recipients
    assert accounts[-1] == associated_token_address(
        accounts[-2], accounts[4], token_program=accounts[12]
    )
    assert writable[21:] == [False, True]


_DEFAULT = "11111111111111111111111111111111"


def _cashback_intent() -> PumpSwapSellIntent:
    intent = _intent_from_chain(_tx("5mrYZLam93Kd"))
    return replace(intent, pool=replace(intent.pool, is_cashback_coin=True))


def test_a_cashback_pool_leads_the_remaining_accounts_with_the_volume_accumulator() -> None:
    """The layout of the official ``@pump-fun/pump-swap-sdk`` 1.20.0 — accumulator WSOL ATA (w),
    accumulator (w), then ``pool_v2`` (r, if a coin creator), buyback (r), its ATA (w) — proven
    against two real cashback sells (``test_our_sell_equals_a_real_cashback_sell...`` below) and by
    a mainnet simulation of our own bytes on a migrated cashback pool (T4.8f F4)."""
    intent = _cashback_intent()
    accumulator = user_volume_accumulator_address(intent.user)
    ix = build_pumpswap_sell_instruction(intent)
    tail = ix.accounts[21:]
    assert [a.pubkey for a in tail] == [
        associated_token_address(accumulator, WSOL_MINT, token_program=TOKEN_PROGRAM_ID),
        accumulator,
        pool_v2_address(intent.pool.base_mint),
        intent.buyback_fee_recipient,
        associated_token_address(
            intent.buyback_fee_recipient, WSOL_MINT, token_program=TOKEN_PROGRAM_ID
        ),
    ]
    assert [a.is_writable for a in tail] == [True, True, False, False, True]
    assert (
        accumulator
        == find_program_address(
            [b"user_volume_accumulator", pubkey_bytes(intent.user)], PUMPSWAP_PROGRAM_ID
        )[0]
    )


def test_a_cashback_pool_without_a_coin_creator_has_no_pool_v2_either() -> None:
    intent = _cashback_intent()
    bare = replace(intent, pool=replace(intent.pool, coin_creator=_DEFAULT))
    ix = build_pumpswap_sell_instruction(bare)
    assert len(ix.accounts) == 21 + 2 + 2
    assert pool_v2_address(bare.pool.base_mint) not in [a.pubkey for a in ix.accounts]


def test_the_verifier_round_trips_the_cashback_variant() -> None:
    intent = _cashback_intent()
    message = build_sell_message(
        intent,
        payer=intent.user,
        recent_blockhash=BLOCKHASH,
        compute_unit_limit=120_000,
        compute_unit_price_micro_lamports=5_000,
        create_wsol_ata=True,
    )
    verify_pumpswap_sell_message(
        serialize_message(message),
        intent,
        compute_unit_limit_cap=200_000,
        compute_unit_price_cap_micro_lamports=10_000,
        expected_blockhash=BLOCKHASH,
    )


def test_a_pool_without_a_coin_creator_builds_23_accounts_for_the_desks_wsol_pools() -> None:
    """The desk's pools are WSOL-quoted; with a default ``coin_creator`` our builder drops
    ``pool_v2`` exactly like the chain's 23-account sells."""
    intent = _intent_from_chain(_tx("5mrYZLam93Kd"))
    bare = replace(intent, pool=replace(intent.pool, coin_creator=_DEFAULT))
    ix = build_pumpswap_sell_instruction(bare)
    assert len(ix.accounts) == 23
    assert [a.is_writable for a in ix.accounts[21:]] == [False, True]
    assert ix.accounts[21].pubkey == bare.buyback_fee_recipient


@pytest.mark.parametrize("sig", CASHBACK_SIGS)
def test_our_sell_equals_a_real_cashback_sell_account_for_account(sig: str) -> None:
    """Two real post-upgrade sells of migrated **cashback** pools (26 accounts): the five remaining accounts
    — accumulator WSOL ATA (w), accumulator (w), ``pool_v2`` (r), buyback recipient (r) and its
    WSOL ATA (w) — are exactly what our builder emits for ``is_cashback_coin``."""
    tx = _tx(sig)
    accounts, _signer, writable, data = _chain_sell(tx)
    (event,) = sell_events_from_transaction(tx)
    assert tx["slot"] > 452_654_882, "landed after the PumpSwap redeploy"
    assert event.layout == "2026-10-02/idl_extension_trailing_u64" and len(accounts) == 26
    intent = _intent_from_chain(tx, cashback=True)
    ix = build_pumpswap_sell_instruction(intent)
    assert len(ix.accounts) == 26
    differing = {i for i, a in enumerate(ix.accounts) if a.pubkey != accounts[i]}
    assert differing <= {5, 6}, (
        f"only the caller's own token accounts may differ: {sorted(differing)}"
    )
    assert [a.is_writable for a in ix.accounts] == writable
    assert ix.data == data
    accumulator = user_volume_accumulator_address(intent.user)
    assert accounts[21] == associated_token_address(
        accumulator, WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    assert accounts[22] == accumulator and accounts[23] == pool_v2_address(accounts[3])
    assert writable[21:] == [True, True, False, False, True]
