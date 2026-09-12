"""The curve batch (T4.2f) over the live capture of 12/09/2026 13:07:58 UTC:
140 of the freshest coins in two ``getMultipleAccounts`` (100 + 41, the 41st a
probe of an address that is not a curve), the block time of each slot, every
refusal by name, and the public RPC's own limit headers. Offline."""

from __future__ import annotations

import base64
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.rpc import METHOD_SPACING_S, SolanaRpcClient
from hunter_exchanges.pumpfun.rpc_curves import (
    ACCOUNTS_PER_CALL,
    CURVE_EMPTIED,
    CURVE_NOT_FOUND,
    MALFORMED,
    UNSUPPORTED_QUOTE,
    curve_addresses,
    decode_curve_batch,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"
ABSENT = "11111111111111111111111111111111"
BLOCK_TIMES = {446436963: datetime(2026, 9, 12, 13, 7, 47, tzinfo=UTC)}
BLOCK_TIMES[446436965] = datetime(2026, 9, 12, 13, 7, 48, tzinfo=UTC)
READ, NON_SOL, EMPTIED = 115, 23, 2
"""What the 140 freshest coins of 13:07 UTC were on chain: 115 SOL curves, 23
quoted in something else (USDC, ``pumpCmXq…``, eleven ``Xs…`` mints — a sixth
of the new listings, a declared blindness of a SOL-only adapter), 2 already
emptied by ``migrate``."""


def _batch(index: int) -> tuple[list[str], list[str], dict[str, Any]]:
    meta = json.loads((FIXTURES / f"t42f_rpc_curves_batch{index}_addresses.json").read_text())
    raw = json.loads((FIXTURES / f"t42f_rpc_curves_batch{index}_raw.json").read_text())
    mints = [name.removeprefix("ABSENT:") for name, _ in meta["addresses"]]
    return mints, [address for _, address in meta["addresses"]], raw


def _mints() -> list[str]:
    return _batch(1)[0] + _batch(2)[0]


def _transport(
    *,
    block_time: dict[str, Any] | None = None,
    batches: dict[int, dict[str, Any]] | None = None,
    status: int = 200,
    calls: list[str] | None = None,
) -> httpx.MockTransport:
    expected = {1: _batch(1)[1], 2: _batch(2)[1]}
    raws = batches or {1: _batch(1)[2], 2: _batch(2)[2]}
    times = json.loads((FIXTURES / "t42f_rpc_block_time_raw.json").read_text())

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if calls is not None:
            calls.append(body["method"])
        if status != 200:
            return httpx.Response(status, headers={"Retry-After": "3"})
        if body["method"] == "getBlockTime":
            if block_time is not None:
                return httpx.Response(200, json=block_time)
            return httpx.Response(200, json=times[str(body["params"][0])])
        assert body["method"] == "getMultipleAccounts"
        addresses, options = body["params"]
        assert options == {"encoding": "base64", "commitment": "finalized"}
        index = 1 if len(addresses) == ACCOUNTS_PER_CALL else 2
        assert addresses == expected[index], "the derived PDAs are the capture's addresses"
        return httpx.Response(200, json=raws[index])

    return httpx.MockTransport(respond)


async def _read(transport: httpx.MockTransport, mints: list[str], **kw: Any) -> Any:
    async with httpx.AsyncClient(transport=transport) as http:
        client = SolanaRpcClient(http_client=http, rpc_url="https://rpc.test")
        return await client.get_curve_states(mints, **kw)


async def test_the_batch_reads_a_hundred_curves_per_call_stamped_with_the_slots_block_time() -> (
    None
):
    calls: list[str] = []
    batch = await _read(_transport(calls=calls), _mints())
    assert calls == ["getMultipleAccounts", "getBlockTime", "getMultipleAccounts", "getBlockTime"]
    assert batch.calls == 4 and batch.slots == (446436963, 446436965)
    assert len(batch.states) == READ and batch.block_time_missing == 0
    reasons: Counter[str] = Counter(batch.refused.values())
    assert reasons == {UNSUPPORTED_QUOTE: NON_SOL, CURVE_EMPTIED: EMPTIED, CURVE_NOT_FOUND: 1}
    assert batch.refused[ABSENT] == CURVE_NOT_FOUND
    first, second = _batch(1)[0], _batch(2)[0]
    for mint in first:
        if mint in batch.states:
            state = batch.states[mint]
            assert state.slot == 446436963 and state.observed_at == BLOCK_TIMES[446436963]
    for mint in second:
        if mint in batch.states:
            state = batch.states[mint]
            assert state.slot == 446436965 and state.observed_at == BLOCK_TIMES[446436965]
    state = batch.states[first[1]]
    assert state.source == "solana_rpc" and state.commitment == "finalized"
    assert state.received_at > state.observed_at, "finalized reads lag the chain: ~11 s live"
    assert sum(1 for s in batch.states.values() if s.mayhem_enabled) == 45
    assert not any(s.complete for s in batch.states.values()), "the two complete ones are emptied"
    # One reading against the decoder by hand: the same bytes, the same numbers.
    raw = _batch(1)[2]["result"]["value"][1]
    decoded = decode_bonding_curve_account(raw["data"][0], owner=raw["owner"])
    assert state.real_token_reserves * 10**6 == decoded.real_token_reserves
    assert state.virtual_sol_reserves * 10**9 == decoded.virtual_sol_reserves


async def test_a_slot_without_a_block_time_keeps_received_at_and_is_counted() -> None:
    batch = await _read(
        _transport(block_time={"jsonrpc": "2.0", "id": 1, "result": None}), _mints()
    )
    assert batch.block_time_missing == READ and batch.calls == 4
    for state in batch.states.values():
        assert state.observed_at == state.received_at and state.slot is not None
    erring = await _read(
        _transport(block_time={"jsonrpc": "2.0", "id": 1, "error": {"code": -32004}}), _mints()
    )
    assert erring.block_time_missing == READ and len(erring.states) == READ, (
        "an RPC error on the block time is a counted absence, never a lost batch"
    )


async def test_without_block_time_the_batch_costs_one_call_per_hundred() -> None:
    calls: list[str] = []
    batch = await _read(_transport(calls=calls), _mints(), with_block_time=False)
    assert calls == ["getMultipleAccounts", "getMultipleAccounts"] and batch.calls == 2
    assert all(s.observed_at == s.received_at for s in batch.states.values())


def test_every_refusal_is_named_never_a_number() -> None:
    mints, _, raw = _batch(1)
    now = datetime(2026, 9, 12, 13, 8, tzinfo=UTC)
    baseline, refused0, _ = decode_curve_batch(
        mints, raw["result"], block_time=None, received_at=now
    )
    assert len(baseline) == 79 and Counter(refused0.values()) == {
        UNSUPPORTED_QUOTE: 19,
        CURVE_EMPTIED: 2,
    }
    emptied = next(m for m, why in refused0.items() if why == CURVE_EMPTIED)
    account = raw["result"]["value"][mints.index(emptied)]
    decoded = decode_bonding_curve_account(account["data"][0], owner=account["owner"])
    assert decoded.complete and decoded.virtual_token_reserves == decoded.real_sol_reserves == 0, (
        "migrate zeroes the curve on chain; the REST mirror keeps the old numbers"
    )
    values = list(raw["result"]["value"])
    sol = [mints.index(m) for m in mints if m in baseline][:4]  # four SOL curves, in order
    values[sol[0]] = None
    values[sol[1]] = dict(values[sol[1]], owner="MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e")
    short = base64.b64encode(base64.b64decode(values[sol[2]]["data"][0])[:80]).decode()
    values[sol[2]] = dict(values[sol[2]], data=[short, "base64"])
    usdc = bytearray(base64.b64decode(values[sol[3]]["data"][0]))
    usdc[83:115] = b"\x01" * 32  # quote_mint is not the System Program id: not native SOL
    values[sol[3]] = dict(values[sol[3]], data=[base64.b64encode(bytes(usdc)).decode(), "base64"])
    result = {"context": {"slot": 446436963}, "value": values}
    states, refused, slot = decode_curve_batch(mints, result, block_time=None, received_at=now)
    assert slot == 446436963 and len(states) == 75
    assert {mints[i]: refused[mints[i]] for i in sol} == {
        mints[sol[0]]: CURVE_NOT_FOUND,
        mints[sol[1]]: CURVE_NOT_FOUND,
        mints[sol[2]]: MALFORMED,
        mints[sol[3]]: UNSUPPORTED_QUOTE,
    }


@pytest.mark.parametrize(
    "result",
    [
        {"context": {"slot": 1}, "value": [None] * 3},
        {"context": {}, "value": [None] * 100},
        {"context": {"slot": -1}, "value": [None] * 100},
        {"value": "nope"},
    ],
)
def test_a_response_that_is_not_a_batch_is_refused_as_a_whole(result: dict[str, Any]) -> None:
    now = datetime(2026, 9, 12, 13, 8, tzinfo=UTC)
    with pytest.raises(MalformedMessage):
        decode_curve_batch(_batch(1)[0], result, block_time=None, received_at=now)


async def test_a_429_on_the_batch_is_rate_limited_never_retried() -> None:
    calls: list[str] = []
    with pytest.raises(RateLimited):
        await _read(_transport(status=429, calls=calls), _mints())
    assert calls == ["getMultipleAccounts"]


def test_the_addresses_are_the_idl_pdas_and_the_capture_names_the_rpcs_own_limits() -> None:
    mints, addresses, _ = _batch(1)
    assert curve_addresses(mints) == list(zip(mints, addresses, strict=True))
    log = json.loads((FIXTURES / "t42f_capture_http_log.json").read_text())
    rpc = [entry for entry in log["rpc"] if entry["url"].startswith("rpc:")]
    assert {entry["status"] for entry in rpc} == {200}
    headers = next(entry["ratelimit"] for entry in rpc if entry["url"] == "rpc:getBlockTime")
    assert headers["x-ratelimit-method-limit"] == "10" and headers["x-ratelimit-rps-limit"] == "250"
    assert METHOD_SPACING_S == 1.0, "one call per second per method: under the header's 10"
    batch1 = next(e for e in rpc if e["name"] == "rpc_curves_batch1")
    assert batch1["bytes"] == 34591 and batch1["ms"] == 467, "100 curves in one call, half a second"
