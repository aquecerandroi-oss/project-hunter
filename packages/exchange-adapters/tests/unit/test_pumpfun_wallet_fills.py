"""T4.12 — a watched wallet's fills from real captured transactions, offline.

The buy is the mainnet fill of ``rpc_tx_buy_raw.json`` (wallet ``AsRQ…``,
through a router with a lookup table); the sell is ``rpc_tx_probe_raw.json``
(wallet ``sssss…``, a public bot — never the operator's). Every lamport below
is the event's own number (T4.8 reconciled the same fields against the
balances); the PumpSwap path is exercised with a synthetic transaction because
no swap of a watched wallet was captured, and it is labelled as such. The RPC
reads go through ``httpx.MockTransport`` — four requests, no socket.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_wallet import WalletRpc
from hunter_exchanges.pumpfun.solana_codec import b58decode, b58encode
from hunter_exchanges.pumpfun.wallet_fills import (
    PUMPSWAP_PROGRAM_ID,
    WSOL_MINT,
    wallet_fills_from_transaction,
)

pytestmark = pytest.mark.unit

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
BUYER = "AsRQHoHxfBYqvxJZxK9RtJUnRZcCwUoh9KNpVxH6Jhnd"
SELLER = "sssssDdMNAWKingjpEojkTNdVuZrBe7FsJLaGtexe7d"
MINT = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
OTHER = "6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F"


def _tx(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text())["result"])


def test_the_real_buy_through_a_router_is_a_curve_fill_lamport_exact() -> None:
    (fill,) = wallet_fills_from_transaction(_tx("rpc_tx_buy_raw.json"), wallet=BUYER, signature="B")
    assert (fill.side, fill.venue, fill.decode, fill.event_index) == (
        "buy",
        "curve",
        "trade_event",
        0,
    )
    assert fill.mint == MINT and fill.slot == 446369982
    assert fill.block_time == datetime.fromtimestamp(1789197249, tz=UTC)
    assert fill.sol_lamports == 977_777_777
    # protocol 9 288 889 + creator 0 + cashback 2 933 334 + network 88 500 (the wallet paid it)
    assert fill.fee_lamports == 9_288_889 + 2_933_334 + 88_500
    assert fill.sol_spent_lamports == 990_088_500 and fill.sol_received_lamports is None
    assert fill.token_amount == Decimal("22628881.309131")
    assert fill.raw["fee_bps"] == {"protocol": 95, "creator": 0, "cashback": 30}
    assert fill.raw["ix_name"] == "buy" and fill.raw["fees"]["network"] == 88_500


def test_the_real_sell_nets_the_leg_minus_every_deduction() -> None:
    (fill,) = wallet_fills_from_transaction(
        _tx("rpc_tx_probe_raw.json"), wallet=SELLER, signature="S"
    )
    assert (fill.side, fill.venue, fill.decode) == ("sell", "curve", "trade_event")
    assert fill.sol_lamports == 724_716_993
    assert fill.fee_lamports == 6_884_812 + 2_174_151 + 100_000
    assert fill.sol_received_lamports == 715_558_030 and fill.sol_spent_lamports is None
    assert fill.token_amount == Decimal("16800146.527261")
    assert fill.block_time == datetime.fromtimestamp(1789198468, tz=UTC)


def test_a_wallet_that_did_not_trade_gets_an_unknown_with_the_reason_and_the_raw() -> None:
    (fill,) = wallet_fills_from_transaction(
        _tx("rpc_tx_probe_raw.json"), wallet=OTHER, signature="S", slot_hint=7
    )
    assert (fill.side, fill.decode, fill.venue) == ("unknown", "none", None)
    assert fill.sol_lamports is None and fill.token_amount is None and not fill.is_fill
    assert fill.raw["reason"] == "no_trade_event_for_wallet"
    assert fill.slot == 446373814  # the transaction's own slot wins over the hint
    assert len(fill.raw["account_keys"]) <= 40 and len(fill.raw["log_head"]) <= 12


def test_a_failed_transaction_is_not_a_fill_and_a_malformed_one_is_an_unknown() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    failed = {**tx, "meta": {**tx["meta"], "err": {"InstructionError": [3, {"Custom": 3}]}}}
    assert wallet_fills_from_transaction(failed, wallet=SELLER, signature="S") == ()
    (fill,) = wallet_fills_from_transaction({}, wallet=SELLER, signature="X", slot_hint=5)
    assert fill.side == "unknown" and fill.raw["reason"] == "malformed_transaction"
    assert fill.slot == 5 and fill.block_time is None


def test_corrupted_event_bytes_are_an_unknown_that_names_the_decoders_error() -> None:
    tx = _tx("rpc_tx_probe_raw.json")
    # Keep the event-CPI tag and the discriminator, cut the body: the decoder
    # raises, and the wallet gets an unknown that names the error, not a fill.
    broken = json.loads(json.dumps(tx))
    corrupted = 0
    for ix in broken["meta"]["innerInstructions"][0]["instructions"]:
        raw = b58decode(ix["data"])
        if len(raw) > 100:
            ix["data"] = b58encode(raw[:-20])
            corrupted += 1
    assert corrupted == 1
    (fill,) = wallet_fills_from_transaction(broken, wallet=SELLER, signature="S")
    assert fill.side == "unknown" and "TradeEvent" in fill.raw["event_error"]
    assert fill.raw["reason"] == "no_trade_event_for_wallet"


def _pool_tx(
    *, sol_before: int, sol_after: int, tokens_before: str, tokens_after: str
) -> dict[str, Any]:
    """A synthetic PumpSwap swap: the wallet pays the fee, its ATA moves, its SOL moves."""
    keys = [OTHER, "AtaAtaAtaAtaAtaAtaAtaAtaAtaAtaAtaAtaAtaAtaA", PUMPSWAP_PROGRAM_ID, "pool"]
    balance = {"mint": MINT, "owner": OTHER, "uiTokenAmount": {"decimals": 6}}
    return {
        "slot": 500,
        "blockTime": 1789200000,
        "transaction": {"message": {"accountKeys": keys, "instructions": []}},
        "meta": {
            "err": None,
            "fee": 5000,
            "preBalances": [sol_before, 2_039_280, 1, 1],
            "postBalances": [sol_after, 2_039_280, 1, 1],
            "preTokenBalances": [
                {
                    **balance,
                    "accountIndex": 1,
                    "uiTokenAmount": {"amount": tokens_before, "decimals": 6},
                }
            ],
            "postTokenBalances": [
                {
                    **balance,
                    "accountIndex": 1,
                    "uiTokenAmount": {"amount": tokens_after, "decimals": 6},
                }
            ],
            "innerInstructions": [],
            "logMessages": [],
        },
    }


def test_a_pumpswap_swap_is_read_from_the_wallets_own_balances_synthetic() -> None:
    buy = _pool_tx(
        sol_before=1_000_000_000,
        sol_after=1_000_000_000 - 5000 - 200_000_000,
        tokens_before="0",
        tokens_after="1500000000",
    )
    (fill,) = wallet_fills_from_transaction(buy, wallet=OTHER, signature="P")
    assert (fill.side, fill.venue, fill.decode) == ("buy", "pool", "balance_delta")
    assert fill.sol_lamports == 200_000_000 and fill.fee_lamports == 5000
    assert fill.sol_spent_lamports == 200_005_000 and fill.token_amount == Decimal("1500")
    assert fill.block_time == datetime.fromtimestamp(1789200000, tz=UTC)
    sell = _pool_tx(
        sol_before=800_000_000,
        sol_after=800_000_000 - 5000 + 150_000_000,
        tokens_before="1500000000",
        tokens_after="0",
    )
    (fill,) = wallet_fills_from_transaction(sell, wallet=OTHER, signature="Q")
    assert (fill.side, fill.sol_lamports, fill.sol_received_lamports) == (
        "sell",
        150_000_000,
        149_995_000,
    )


def test_a_pumpswap_transaction_without_a_clean_delta_is_an_unknown() -> None:
    same_sign = _pool_tx(
        sol_before=1_000_000_000,
        sol_after=1_000_000_000 + 1_000,
        tokens_before="0",
        tokens_after="10",
    )
    (fill,) = wallet_fills_from_transaction(same_sign, wallet=OTHER, signature="R")
    assert fill.side == "unknown" and fill.raw["reason"] == "sol_leg_sign_mismatch"
    wsol_only = _pool_tx(sol_before=10, sol_after=10 - 5000, tokens_before="0", tokens_after="0")
    wsol_only["meta"]["postTokenBalances"] = [
        {
            "accountIndex": 1,
            "mint": WSOL_MINT,
            "owner": OTHER,
            "uiTokenAmount": {"amount": "5", "decimals": 9},
        }
    ]
    (fill,) = wallet_fills_from_transaction(wsol_only, wallet=OTHER, signature="T")
    assert fill.side == "unknown" and fill.raw["reason"] == "no_token_delta"


async def test_the_wallet_rpc_reads_signatures_and_a_transaction_offline() -> None:
    signatures = json.loads((FIXTURES / "rpc_signatures_global_raw.json").read_text())
    probe = json.loads((FIXTURES / "rpc_tx_probe_raw.json").read_text())
    requests: list[dict[str, Any]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if body["method"] == "getSignaturesForAddress":
            return httpx.Response(200, json=signatures)
        if body["params"][0] == "missing":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": None})
        return httpx.Response(200, json=probe)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        rpc = WalletRpc(SolanaRpcClient(http_client=http, rpc_url="https://rpc.test"))
        infos = await rpc.get_signatures_for_address(SELLER, until="CURSOR", limit=50)
        assert len(infos) == 15 and infos[0].failed and not infos[1].failed
        assert infos[0].slot == 446373814
        assert infos[0].block_time == datetime.fromtimestamp(1789198468, tz=UTC)
        assert requests[0]["params"] == [
            SELLER,
            {"limit": 50, "commitment": "finalized", "until": "CURSOR"},
        ]
        tx = await rpc.get_transaction(infos[1].signature)
        assert tx is not None and tx["slot"] == 446373814
        assert requests[1]["params"][1]["maxSupportedTransactionVersion"] == 0
        assert await rpc.get_transaction("missing") is None
    assert len(requests) == 3  # well under the brief's ten
