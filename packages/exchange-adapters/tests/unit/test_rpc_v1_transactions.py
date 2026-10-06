"""Wave 1a of H-030, part B: ``getTransaction`` must be asked for ``maxSupportedTransactionVersion: 1``.

The public RPC answers ``-32015`` ("Transaction version (1) is not supported by the requesting
client") to a ``getTransaction``/``getBlock`` with ``maxSupportedTransactionVersion: 0`` whenever the
transaction is a **version 1** one — 18 of 115 successful pump transactions and 18 of 100 PumpSwap
ones read on 2026-10-05, 13 % of one sampled block. ``tx_rpc.py`` (the meme-executor's reconciliation
reads) and ``rpc_wallet.py`` (the watched-wallet loop) both sent ``0``.

Fixtures: ``t1a_rpc_get_transaction_v1_unsupported_error_raw.json`` is the public RPC's REAL ``-32015``
reply; ``t1a_rpc_v1_*_raw.json`` are REAL version-1 transactions (``fixtures/t1a_provenance.json``).
:func:`_serve` reproduces the node's rule from that reply: a transaction newer than the version the
caller declared is refused with the recorded error; ``legacy`` is always served. No network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import ExchangeError
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_wallet import WalletRpc
from hunter_exchanges.pumpfun.trade_event import trade_events_from_transaction
from hunter_exchanges.pumpfun.tx_rpc import SolanaTxRpcClient
from hunter_exchanges.pumpfun.wallet_fills import (
    ata_close_refund_lamports,
    rent_labels,
    wallet_fills_from_transaction,
)
from hunter_exchanges.pumpswap.buy_event import buy_events_from_transaction
from hunter_exchanges.pumpswap.sell_event import sell_events_from_transaction

from .t1a_chain import load, tx_fixture

_ERROR = "pumpfun/t1a_rpc_get_transaction_v1_unsupported_error_raw.json"
V1_PUMP_SELL = ("pumpfun", "t1a_rpc_v1_pump_sell_37gcmBFxPWmF_raw.json")
V1_PUMP_BUY = ("pumpfun", "t1a_rpc_v1_pump_buy_4b5YwBKdr5_raw.json")
V1_AMM_SELL = ("pumpswap", "t1a_rpc_v1_amm_sell_5Ls5TV77aYS3_raw.json")
V1_AMM_BUY = ("pumpswap", "t1a_rpc_v1_amm_buy_exact_holder_rewards_4JMsAJNT9otk_raw.json")
LEGACY_AMM_BUY = ("pumpswap", "t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json")
V0_AMM_BUY = ("pumpswap", "t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json")


def _serve(
    tx: dict[str, Any], seen: list[dict[str, Any]]
) -> Callable[[httpx.Request], httpx.Response]:
    error = load(_ERROR)

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        declared = body["params"][1].get("maxSupportedTransactionVersion")
        version = tx["version"]
        if version != "legacy" and (declared is None or declared < version):
            return httpx.Response(200, json=error)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": tx})

    return respond


def test_the_recorded_node_reply_is_the_32015_this_test_stands_in_for() -> None:
    error = load(_ERROR)["error"]
    assert error["code"] == -32015
    assert "Transaction version (1) is not supported" in error["message"]
    assert '"maxSupportedTransactionVersion": 1' in error["message"]


@pytest.mark.parametrize("fixture", [V1_PUMP_SELL, V1_PUMP_BUY, V1_AMM_SELL, V1_AMM_BUY])
def test_the_execution_path_client_reads_a_version_1_transaction(fixture: tuple[str, str]) -> None:
    tx = tx_fixture(*fixture)
    assert tx["version"] == 1
    seen: list[dict[str, Any]] = []
    client = SolanaTxRpcClient(
        "https://rpc.test",
        http_client=httpx.Client(transport=httpx.MockTransport(_serve(tx, seen))),
    )
    result = client.get_transaction(tx["transaction"]["signatures"][0], commitment="finalized")
    assert result == tx
    assert seen[0]["params"][1] == {
        "encoding": "json",
        "commitment": "finalized",
        "maxSupportedTransactionVersion": 1,
    }


@pytest.mark.parametrize("fixture", [V1_PUMP_SELL, V1_AMM_SELL])
async def test_the_wallet_loop_client_reads_a_version_1_transaction(
    fixture: tuple[str, str],
) -> None:
    tx = tx_fixture(*fixture)
    seen: list[dict[str, Any]] = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(_serve(tx, seen))) as http:
        rpc = WalletRpc(SolanaRpcClient(http_client=http, rpc_url="https://rpc.test"))
        result = await rpc.get_transaction(tx["transaction"]["signatures"][0])
    assert result == tx
    assert seen[0]["params"][1] == {
        "encoding": "json",
        "commitment": "finalized",
        "maxSupportedTransactionVersion": 1,
    }


@pytest.mark.parametrize("fixture", [LEGACY_AMM_BUY, V0_AMM_BUY])
def test_legacy_and_version_0_transactions_are_served_exactly_as_before(
    fixture: tuple[str, str],
) -> None:
    """The change must not alter what a legacy or v0 reply looks like to the caller: same request
    but for the declared version, same returned object, ``None`` still means "not found"."""
    tx = tx_fixture(*fixture)
    seen: list[dict[str, Any]] = []
    client = SolanaTxRpcClient(
        "https://rpc.test",
        http_client=httpx.Client(transport=httpx.MockTransport(_serve(tx, seen))),
    )
    assert client.get_transaction("sig") == tx
    assert set(seen[0]["params"][1]) == {"encoding", "commitment", "maxSupportedTransactionVersion"}
    assert seen[0]["params"][1]["encoding"] == "json"
    assert seen[0]["params"][1]["commitment"] == "confirmed"  # the default is untouched

    def not_found(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": None})

    gone = SolanaTxRpcClient(
        "https://rpc.test", http_client=httpx.Client(transport=httpx.MockTransport(not_found))
    )
    assert gone.get_transaction("sig") is None


def test_a_node_that_still_refuses_is_an_error_never_a_silent_none() -> None:
    """A -32015 (a future version 2, say) surfaces as the client's ``ExchangeError`` with the code;
    the reader must not turn it into "transaction not found"."""
    error = load(_ERROR)

    def always_unsupported(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=error)

    client = SolanaTxRpcClient(
        "https://rpc.test",
        http_client=httpx.Client(transport=httpx.MockTransport(always_unsupported)),
    )
    with pytest.raises(ExchangeError, match="-32015"):
        client.get_transaction("sig")


# -- the parsers downstream of getTransaction handle a version-1 reply --------------------------
# A v1 message has `transactionConfig` instead of `addressTableLookups`, no lookup tables, and an
# empty `meta.loadedAddresses`; `accountKeys`, `instructions` and `innerInstructions` keep the
# legacy shape. Every parser below reads only those, so it must give the same answers.


def test_a_v1_response_has_the_shape_the_parsers_read() -> None:
    for fixture in (V1_PUMP_SELL, V1_PUMP_BUY, V1_AMM_SELL, V1_AMM_BUY):
        tx = tx_fixture(*fixture)
        message = tx["transaction"]["message"]
        assert "addressTableLookups" not in message and "transactionConfig" in message
        assert tx["meta"]["loadedAddresses"] == {"readonly": [], "writable": []}
        assert isinstance(message["accountKeys"][0], str)  # plain pubkeys, not jsonParsed objects


def test_the_curve_trade_of_a_v1_transaction_decodes_to_a_wallet_fill() -> None:
    tx = tx_fixture(*V1_PUMP_BUY)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    (fill,) = wallet_fills_from_transaction(
        tx, wallet=event.user, signature=tx["transaction"]["signatures"][0]
    )
    assert fill.side == "buy" and fill.mint == event.mint
    assert fill.block_time == datetime.fromtimestamp(tx["blockTime"], tz=UTC)


def test_the_curve_sell_of_a_v1_transaction_decodes_to_a_wallet_fill() -> None:
    tx = tx_fixture(*V1_PUMP_SELL)
    (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
    (fill,) = wallet_fills_from_transaction(
        tx, wallet=event.user, signature=tx["transaction"]["signatures"][0]
    )
    assert fill.side == "sell" and fill.mint == event.mint


def test_the_pumpswap_events_of_v1_transactions_decode() -> None:
    (sell,) = sell_events_from_transaction(tx_fixture(*V1_AMM_SELL))
    assert sell.user_quote_amount_out > 0
    (buy,) = buy_events_from_transaction(tx_fixture(*V1_AMM_BUY))
    assert buy.money_conserves


def test_the_rent_accounting_reads_a_version_1_transaction() -> None:
    """``rent_labels`` / ``ata_close_refund_lamports`` index balances by the same key order a v1
    reply has (static keys, empty loaded lists): they answer instead of raising."""
    for fixture, side in ((V1_PUMP_BUY, "buy"), (V1_PUMP_SELL, "sell")):
        tx = tx_fixture(*fixture)
        (event,) = trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)
        ata_rent, account_rent = rent_labels(tx, event.user)
        refund = ata_close_refund_lamports(tx, event.user)
        pinned = {"buy": (1_513_840, None, None), "sell": (None, None, None)}[side]
        assert (ata_rent, account_rent, refund) == pinned
        assert event.is_buy == (side == "buy")
