"""Wave 1a of H-030, part B — the premise of the offline tests, checked against the real node (``live``).

``tests/unit/test_rpc_v1_transactions.py`` replays a recorded ``-32015`` and recorded transactions.
This test asks the public RPC itself, read-only, about three of the very transactions recorded in
``tests/fixtures/t1a_provenance.json``, so that two claims do not rest on a mock:

1. with ``maxSupportedTransactionVersion: 0`` the node still refuses the version-1 transaction, and
   with ``1`` it serves it (the bug and its fix);
2. for a legacy and a version-0 transaction the reply at ``0`` and at ``1`` is **identical** (the
   change alters nothing for them).

Never in CI (``live`` marker, opt-in env var). Run:
``HUNTER_LIVE_TESTS=1 uv run pytest packages/exchange-adapters/tests/live/test_live_tx_version.py -m live -q``
A public node keeps only recent history: if a recorded signature has been pruned the test skips
rather than fails.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest

from ..unit.t1a_chain import load

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("HUNTER_LIVE_TESTS") != "1",
        reason="set HUNTER_LIVE_TESTS=1 to hit the real Solana public RPC",
    ),
]

_URL = "https://api.mainnet-beta.solana.com"
_V1 = "pumpfun/t1a_rpc_v1_pump_sell_37gcmBFxPWmF_raw.json"
_LEGACY = "pumpswap/t1a_rpc_amm_buy_exact_3YxgSPJioUJp_raw.json"
_V0 = "pumpswap/t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"


def _get(client: httpx.Client, signature: str, max_version: int) -> dict[str, Any]:
    response = client.post(
        _URL,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTransaction",
            "params": [
                signature,
                {
                    "encoding": "json",
                    "commitment": "finalized",
                    "maxSupportedTransactionVersion": max_version,
                },
            ],
        },
    )
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def _signature(relative: str) -> str:
    return str(load(relative)["transaction"]["signatures"][0])


def test_the_node_refuses_version_1_at_zero_and_serves_it_at_one() -> None:
    signature = _signature(_V1)
    with httpx.Client(timeout=30) as client:
        at_one = _get(client, signature, 1)
        assert "error" not in at_one, at_one  # an RPC error is a failure, not "pruned"
        if at_one.get("result") is None:
            pytest.skip("the public node no longer holds this transaction")
        at_zero = _get(client, signature, 0)
    assert at_zero["error"]["code"] == -32015
    assert at_one["result"]["version"] == 1
    assert at_one["result"] == load(_V1)  # the recorded fixture is what the node serves


@pytest.mark.parametrize("fixture", [_LEGACY, _V0])
def test_legacy_and_v0_replies_are_identical_at_zero_and_at_one(fixture: str) -> None:
    signature = _signature(fixture)
    with httpx.Client(timeout=30) as client:
        at_zero = _get(client, signature, 0)
        at_one = _get(client, signature, 1)
    assert "error" not in at_zero and "error" not in at_one, (at_zero, at_one)
    if at_zero.get("result") is None:
        pytest.skip("the public node no longer holds this transaction")
    assert at_zero == at_one
    assert at_one["result"] == load(fixture)
