"""``MayhemState`` (T4.2e): the PDAs by the pump IDL's seeds, the discriminators by
Anchor's convention, the inferred layout held to an identity with no constant in
it, and the batch read — all offline, over the five live accounts of 12/09/2026
(``t42e_rpc_mayhem_accounts*_raw.json``)."""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.mayhem_state import (
    GLOBAL_PARAMS_DISCRIMINATOR,
    MAYHEM_PROGRAM_ID,
    MAYHEM_STATE_DISCRIMINATOR,
    MAYHEM_STATE_LEN,
    MayhemRefused,
    anchor_account_discriminator,
    decode_mayhem_state,
    decode_mint_supply,
    decode_token_account_amount,
    mayhem_accounts_for,
    mayhem_flow_from_accounts,
    mayhem_pdas,
)
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.pumpfun.solana_codec import b58encode

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
BATCHES = (
    "t42e_rpc_mayhem_accounts",
    "t42e_rpc_mayhem_accounts_paused",
    "t42e_rpc_mayhem_accounts_fh42k",
)
FIXTURE_MINT = "2sduGq1bDtMbu6apCs3cfmqfyA32bkXA4CCBdTW5pump"
AGENT_WALLET = "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s"
"""``pump.fun/docs/mayhem-mode``'s published agent wallet (A4.1b §5.2)."""


def _accounts() -> dict[str, dict[str, Any]]:
    """Every captured account by address, across the three batch fixtures."""
    out: dict[str, dict[str, Any]] = {}
    for name in BATCHES:
        raw = json.loads((FIXTURES / f"{name}_raw.json").read_text())
        meta = json.loads((FIXTURES / f"{name}_addresses.json").read_text())
        for (_, address), account in zip(meta["addresses"], raw["result"]["value"], strict=True):
            out[address] = account
    return out


def _mints() -> list[str]:
    mints: list[str] = []
    for name in BATCHES:
        mints += json.loads((FIXTURES / f"{name}_addresses.json").read_text())["mints"]
    return mints


def _flow(mint: str, accounts: dict[str, dict[str, Any]]):
    curve_addr, state_addr, vault_addr, mint_addr = mayhem_accounts_for(mint)
    curve, state, vault, spl_mint = (
        accounts[a] for a in (curve_addr, state_addr, vault_addr, mint_addr)
    )
    return mayhem_flow_from_accounts(
        mint,
        curve=decode_bonding_curve_account(curve["data"][0], owner=curve["owner"]),
        state=decode_mayhem_state(state["data"][0], owner=state["owner"]),
        vault_tokens=decode_token_account_amount(vault["data"][0], owner=vault["owner"]),
        mint_supply=decode_mint_supply(spl_mint["data"][0], owner=spl_mint["owner"]),
        slot=1,
        commitment="finalized",
    )


def test_the_pdas_come_from_the_idl_seeds_and_match_the_live_addresses() -> None:
    meta = json.loads((FIXTURES / "t42e_rpc_mayhem_accounts_addresses.json").read_text())
    by_label = dict(meta["addresses"])
    pdas = mayhem_pdas()
    assert pdas.global_params == by_label["global_params"]
    assert pdas.sol_vault == by_label["sol_vault"] == AGENT_WALLET, (
        "the sol-vault PDA is the agent wallet the docs publish"
    )
    for mint in meta["mints"]:
        assert mayhem_accounts_for(mint) == (
            by_label[f"bc:{mint}"],
            by_label[f"ms:{mint}"],
            by_label[f"vault:{mint}"],
            mint,
        )


def test_the_program_has_no_idl_on_chain_and_the_discriminators_are_anchors() -> None:
    idl = json.loads((FIXTURES / "t42e_rpc_mayhem_idl_raw.json").read_text())
    assert idl["result"]["value"] is None, "the Anchor IDL account of MAyh… is absent"
    assert MAYHEM_STATE_DISCRIMINATOR.hex() == "b1fdbf7dcb16866b"
    assert GLOBAL_PARAMS_DISCRIMINATOR.hex() == "79c1f857c3384c0b"
    assert anchor_account_discriminator("BondingCurve").hex() == "17b7f83760d8ac60", (
        "the same convention names the pump account decode.py validates"
    )
    accounts = _accounts()
    meta = json.loads((FIXTURES / "t42e_rpc_mayhem_accounts_addresses.json").read_text())
    by_label = dict(meta["addresses"])
    global_params = base64.b64decode(accounts[by_label["global_params"]]["data"][0])
    assert global_params[:8] == GLOBAL_PARAMS_DISCRIMINATOR and len(global_params) == 318
    assert accounts[by_label["global_params"]]["owner"] == MAYHEM_PROGRAM_ID


def test_every_live_account_decodes_reconciles_and_names_its_mint() -> None:
    accounts = _accounts()
    seen = 0
    for mint in _mints():
        state_account = accounts[mayhem_accounts_for(mint)[1]]
        raw = base64.b64decode(state_account["data"][0])
        assert len(raw) == MAYHEM_STATE_LEN
        state = decode_mayhem_state(state_account["data"][0], owner=state_account["owner"])
        assert state.mint == mint
        assert state.window_end - state.window_start == 86_400
        flow = _flow(mint, accounts)
        assert flow.agent_extra_supply == Decimal(1_000_000_000)
        assert flow.mint_supply == Decimal(2_000_000_000)
        assert flow.vault_tokens + flow.agent_net_sold_tokens == flow.agent_extra_supply
        assert flow.curve.is_mayhem_mode and flow.curve_total_supply == Decimal(1_000_000_000)
        seen += 1
    assert seen == 5


def test_the_fixture_coin_holds_exactly_the_record_plus_the_agents_net_sells() -> None:
    """``2sduGq…``: 822 644 036,902123 real tokens = 793 100 000 + 29 544 036,902123 —
    the humans' net is zero (``real_sol_reserves`` = 1 lamport) and the excess
    over the record is the agent's, to the subunit."""
    flow = _flow(FIXTURE_MINT, _accounts())
    assert flow.curve_real_token_reserves == Decimal("822644036.902123")
    assert flow.agent_net_sold_tokens == Decimal("29544036.902123")
    assert flow.agent_net_sol_in == Decimal("-0.606946990"), "the agent took 0,607 SOL out"
    assert flow.curve_reserve_without_agent == Decimal("793100000")
    bought = _flow("4BTPZVKt4zC9ukLFBgEe3hQcXLTE8ATRBZFuMnRTpump", _accounts())
    assert bought.agent_net_sold_tokens == Decimal("-9988703.539400"), "a net buyer is negative"
    assert bought.agent_net_sol_in == Decimal("0.020081941")
    assert bought.vault_tokens == Decimal("1009988703.539400")
    dumped = _flow("Fh42kAfy27CGoUA8CgFwpTGMubzndaAyTy2gghu5pump", _accounts())
    assert dumped.agent_net_sold_tokens == Decimal("999999991.751764"), (
        "6,5 h in: the billion, sold"
    )
    assert dumped.curve_real_token_reserves > Decimal(1_700_000_000)


def test_a_flow_that_does_not_reconcile_is_refused_by_name() -> None:
    accounts = _accounts()
    curve_addr, state_addr, vault_addr, mint_addr = mayhem_accounts_for(FIXTURE_MINT)
    curve = decode_bonding_curve_account(
        accounts[curve_addr]["data"][0], owner=accounts[curve_addr]["owner"]
    )
    state = decode_mayhem_state(
        accounts[state_addr]["data"][0], owner=accounts[state_addr]["owner"]
    )
    vault = decode_token_account_amount(
        accounts[vault_addr]["data"][0], owner=accounts[vault_addr]["owner"]
    )
    supply = decode_mint_supply(accounts[mint_addr]["data"][0], owner=accounts[mint_addr]["owner"])
    with pytest.raises(MayhemRefused) as refused:
        mayhem_flow_from_accounts(
            FIXTURE_MINT, curve=curve, state=state, vault_tokens=vault + 1, mint_supply=supply
        )
    assert refused.value.reason == "identity_failed"
    with pytest.raises(MayhemRefused) as mismatch:
        mayhem_flow_from_accounts(
            "4BTPZVKt4zC9ukLFBgEe3hQcXLTE8ATRBZFuMnRTpump",
            curve=curve,
            state=state,
            vault_tokens=vault,
            mint_supply=supply,
        )
    assert mismatch.value.reason == "mint_mismatch"


@pytest.mark.parametrize("mutation", ["owner", "discriminator", "short", "base64"])
def test_the_decoder_refuses_what_is_not_a_mayhem_state(mutation: str) -> None:
    account = _accounts()[mayhem_accounts_for(FIXTURE_MINT)[1]]
    data, owner = account["data"][0], account["owner"]
    if mutation == "owner":
        owner = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
    elif mutation == "discriminator":
        raw = bytearray(base64.b64decode(data))
        raw[0] ^= 1
        data = base64.b64encode(raw).decode()
    elif mutation == "short":
        data = base64.b64encode(base64.b64decode(data)[:80]).decode()
    else:
        data = "not*base64"
    with pytest.raises(MalformedMessage):
        decode_mayhem_state(data, owner=owner)


def _mock(accounts: dict[str, dict[str, Any]], calls: list[list[str]]) -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["method"] == "getMultipleAccounts"
        addresses, options = body["params"]
        assert options == {"encoding": "base64", "commitment": "finalized"}
        calls.append(addresses)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "context": {"slot": 446421000},
                    "value": [accounts.get(address) for address in addresses],
                },
            },
        )

    return httpx.MockTransport(respond)


async def test_the_batch_read_serves_25_mints_per_call_and_names_every_refusal() -> None:
    accounts = _accounts()
    calls: list[list[str]] = []
    mints = _mints()
    standard = "5ejAEbzxiZuwUNgZcoryoAY8gA5oCAVJZx5AyDnApump"
    padding = [b58encode(i.to_bytes(32, "big")) for i in range(1, 30 - len(mints))]
    async with httpx.AsyncClient(transport=_mock(accounts, calls)) as http:
        client = SolanaRpcClient(http_client=http, rpc_url="https://rpc.test")
        batch = await client.get_mayhem_flows([*mints, standard, *padding])
    assert batch.calls == 2 and [len(c) for c in calls] == [100, 20]
    assert batch.slot == 446421000
    assert set(batch.flows) == set(mints)
    assert batch.flows[FIXTURE_MINT].slot == 446421000
    assert batch.flows[FIXTURE_MINT].commitment == "finalized"
    assert batch.refused[standard] == "curve_not_found", "an unknown mint has no curve here"
    assert all(batch.refused[m] == "curve_not_found" for m in padding)


async def test_a_curve_without_a_mayhem_state_is_refused_as_not_mayhem() -> None:
    accounts = dict(_accounts())
    del accounts[mayhem_accounts_for(FIXTURE_MINT)[1]]
    calls: list[list[str]] = []
    async with httpx.AsyncClient(transport=_mock(accounts, calls)) as http:
        batch = await SolanaRpcClient(
            http_client=http, rpc_url="https://rpc.test"
        ).get_mayhem_flows([FIXTURE_MINT])
    assert batch.flows == {} and batch.refused == {FIXTURE_MINT: "not_mayhem"}
