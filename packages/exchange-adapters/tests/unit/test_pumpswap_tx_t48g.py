"""T4.8g — our PumpSwap ``sell`` against real sells that landed AFTER the 2026-10-08 redeploy
(PumpSwap slot 454596406, 16:20:03Z): the 24-account shape (``pool_v2``, a buyback recipient of
``GlobalConfig.buyback_fee_recipients`` and its WSOL ATA) is still exactly what the program takes.

Same method as ``test_pumpswap_tx_t48f.py``. Fixtures ``t48g_rpc_amm_tx_sell_*_raw.json`` (slot
454630902, read-only, provenance in ``t48g_provenance.json``): WSOL-quoted pools with a coin creator,
the desk's own shape. ``GlobalConfig`` is the 2026-10-08 read — byte-identical to T4.8f's.

Of the 29 real sells read (51 PumpSwap transactions with a Sell/BuyEvent, 0 decode errors), 11 were
WSOL-quoted: 9 identical to ours account for account, 2 differing only in a caller's choice
(``accounts[6]``, or ``global_config`` writable); the other 18 are custom-quote pools.

**Not proven here:** a *cashback* PumpSwap sell (26 accounts) after this redeploy. None of the 29
(nor of a sample of cashback pools) was one; that layout is covered by T4.8f's two real sells
(``test_pumpswap_tx_t48f.py``, before this redeploy) and by a mainnet simulation of our own bytes on
2026-10-08 (``t48g_simulation_proof_mainnet.json``), not by a real post-redeploy trade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from hunter_exchanges.pumpfun.solana_codec import (
    TOKEN_PROGRAM_ID,
    associated_token_address,
    b58decode,
)
from hunter_exchanges.pumpswap.decode import (
    PUMPSWAP_PROGRAM_ID,
    WSOL_MINT,
    Pool,
    decode_global_config,
)
from hunter_exchanges.pumpswap.pdas import pool_v2_address
from hunter_exchanges.pumpswap.sell_event import sell_events_from_transaction
from hunter_exchanges.pumpswap.tx import (
    SELL_DISCRIMINATOR,
    PumpSwapSellIntent,
    build_pumpswap_sell_instruction,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpswap"
DEPLOY_SLOT = 454_596_406
# fixture -> writable-flag diffs the CALLER (a router) chose
SELLS = {
    "t48g_rpc_amm_tx_sell_2C8QHNSJtxoh_raw.json": set[int](),
    "t48g_rpc_amm_tx_sell_5cWuAY9xJtrp_raw.json": set[int](),
    "t48g_rpc_amm_tx_sell_AXNiK4CmYw5m_raw.json": set[int](),
    "t48g_rpc_amm_tx_sell_YdnQWgW72poy_raw.json": set[int](),
    "t48g_rpc_amm_tx_sell_5b3eUPbMhPAH_raw.json": {2},  # global_config passed writable
}


def _tx(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


def _config() -> Any:
    value = _tx("t48g_rpc_global_config_raw.json")["result"]["value"]
    return decode_global_config(value["data"][0], owner=value["owner"])


def _chain_sell(tx: dict[str, Any]) -> tuple[list[str], list[bool], list[bool], bytes]:
    message = tx["transaction"]["message"]
    keys = list(message["accountKeys"])
    loaded = cast(dict[str, list[str]], tx["meta"].get("loadedAddresses") or {})
    n = len(keys)
    header = message["header"]
    keys += list(loaded.get("writable", [])) + list(loaded.get("readonly", []))

    def writable(i: int) -> bool:
        if i < n:
            if i < header["numRequiredSignatures"]:
                return i < header["numRequiredSignatures"] - header["numReadonlySignedAccounts"]
            return i < n - header["numReadonlyUnsignedAccounts"]
        return i - n < len(loaded.get("writable", []))

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
                [i < header["numRequiredSignatures"] for i in idx],
                [writable(i) for i in idx],
                data,
            )
    raise AssertionError("no PumpSwap sell in the transaction")


def _intent(tx: dict[str, Any]) -> PumpSwapSellIntent:
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
        is_cashback_coin=False,
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


@pytest.mark.parametrize("name", list(SELLS))
def test_our_sell_equals_a_real_post_redeploy_sell_account_for_account(name: str) -> None:
    tx = _tx(name)
    assert tx["slot"] > DEPLOY_SLOT
    accounts, signer, writable, data = _chain_sell(tx)
    ix = build_pumpswap_sell_instruction(_intent(tx))
    assert len(accounts) == 24 == len(ix.accounts)
    assert [a.pubkey for a in ix.accounts] == accounts
    caller = {i for i, a in enumerate(ix.accounts) if a.is_writable != writable[i]}
    assert caller == SELLS[name], f"writable flags differing from the chain: {sorted(caller)}"
    assert [a.is_signer for a in ix.accounts] == signer
    assert ix.data == data
    # the structural tail: pool_v2 (r), a buyback recipient of GlobalConfig (r), its WSOL ATA (w)
    assert accounts[4] == WSOL_MINT
    assert accounts[21] == pool_v2_address(accounts[3])
    assert accounts[22] in _config().buyback_fee_recipients
    assert accounts[23] == associated_token_address(
        accounts[22], WSOL_MINT, token_program=TOKEN_PROGRAM_ID
    )
    assert writable[21:] == [False, False, True]


def test_global_config_of_the_new_deploy_is_byte_identical_to_t48fs() -> None:
    new = _tx("t48g_rpc_global_config_raw.json")["result"]
    old = _tx("t48f_rpc_global_config_raw.json")["result"]
    assert new["context"]["slot"] > old["context"]["slot"]
    assert new["value"]["data"][0] == old["value"]["data"][0]
    assert len(_config().buyback_fee_recipients) == 8
