"""Copy-trade pilot (H-037): the production adapters over ``SolanaRpcClient.call`` (faked, no network)."""

from __future__ import annotations

from typing import Any

import pytest

from hunter_exchanges.pumpfun.leader_source_wiring import (
    rpc_fetch_tx,
    rpc_list_signatures,
    rpc_wallet_seeder,
)

pytestmark = pytest.mark.unit

TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


class FakeRpc:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, list[Any]]] = []

    async def call(self, method: str, params: list[Any]) -> Any:
        self.calls.append((method, params))
        answer = self.answers[method]
        if callable(answer):
            return answer(params)
        return answer


def token_account(mint: str, amount: str) -> dict[str, Any]:
    return {
        "account": {"data": {"parsed": {"info": {"mint": mint, "tokenAmount": {"amount": amount}}}}}
    }


async def test_one_refusal_pauses_the_fetch_the_listing_and_the_seed_alike() -> None:
    from hunter_exchanges.base import RateLimited
    from hunter_exchanges.pumpfun.leader_source_rpc_guard import RpcGuard, RpcRefused

    class Raising(FakeRpc):
        async def call(self, method: str, params: list[Any]) -> Any:
            self.calls.append((method, params))
            if method == "getTransaction":
                raise RateLimited("429", exchange="p", retry_after_s=60.0)
            return {"context": {"slot": 1}, "value": []}

    raising = Raising({})
    guard = RpcGuard(raising)
    with pytest.raises(RpcRefused):
        await rpc_fetch_tx(guard)("SIG")
    with pytest.raises(RpcRefused):
        await rpc_list_signatures(guard)("W", None, 1, None)
    with pytest.raises(RpcRefused):
        await rpc_wallet_seeder(guard)("W")
    assert [m for m, _ in raising.calls] == ["getTransaction"]


async def test_fetch_tx_asks_for_confirmed_json_with_version_1() -> None:
    rpc = FakeRpc({"getTransaction": {"slot": 5}})
    tx = await rpc_fetch_tx(rpc)("SIG")
    assert tx == {"slot": 5}
    ((method, params),) = rpc.calls
    assert method == "getTransaction" and params[0] == "SIG"
    assert params[1] == {
        "encoding": "json",
        "commitment": "confirmed",
        "maxSupportedTransactionVersion": 1,
    }


async def test_fetch_tx_returns_none_when_the_node_does_not_have_it_yet() -> None:
    assert await rpc_fetch_tx(FakeRpc({"getTransaction": None}))("SIG") is None


async def test_list_signatures_reads_confirmed_with_the_cursor_and_skips_junk() -> None:
    rpc = FakeRpc(
        {
            "getSignaturesForAddress": [
                {"signature": "S2", "slot": 9, "blockTime": 1789197249, "err": None},
                {"signature": "S1", "slot": 8, "blockTime": None, "err": {"x": 1}},
                {"nonsense": True},
            ]
        }
    )
    got = await rpc_list_signatures(rpc)("W", "ANCHOR", 50, "CURSOR")
    assert [(g.signature, g.slot, g.failed) for g in got] == [("S2", 9, False), ("S1", 8, True)]
    assert got[0].block_time is not None and got[1].block_time is None
    ((_, params),) = rpc.calls
    assert params == [
        "W",
        {"limit": 50, "commitment": "confirmed", "until": "ANCHOR", "before": "CURSOR"},
    ]


async def test_the_seed_is_sol_plus_every_token_of_both_token_programs_summed_per_mint() -> None:
    def tokens(params: list[Any]) -> dict[str, Any]:
        program = params[1]["programId"]
        if program == TOKEN:
            return {
                "context": {"slot": 100},
                "value": [
                    token_account("M1", "5"),
                    token_account("M1", "7"),
                    token_account("M2", "0"),
                ],
            }
        assert program == TOKEN_2022
        return {"context": {"slot": 98}, "value": [token_account("M3", "11")]}

    rpc = FakeRpc(
        {
            "getBalance": {"context": {"slot": 101}, "value": 42},
            "getTokenAccountsByOwner": tokens,
        }
    )
    snap = await rpc_wallet_seeder(rpc)("W")
    assert snap.sol_lamports == 42 and snap.sol_slot == 101
    assert snap.tokens == {"M1": (12, 100), "M3": (11, 98)}  # each mint keeps its own read's slot
    assert (
        snap.tokens_slot == 100
    )  # a mint absent from every list is zero only after the newest read
    assert {c[0] for c in rpc.calls} == {"getBalance", "getTokenAccountsByOwner"}
    token_calls = [p for m, p in rpc.calls if m == "getTokenAccountsByOwner"]
    assert all(p[2] == {"encoding": "jsonParsed", "commitment": "confirmed"} for p in token_calls)


async def test_a_malformed_seed_answer_is_an_error_not_a_zero_balance() -> None:
    rpc = FakeRpc(
        {"getBalance": {"context": {"slot": 1}, "value": "x"}, "getTokenAccountsByOwner": {}}
    )
    with pytest.raises(ValueError, match="seed"):
        await rpc_wallet_seeder(rpc)("W")
