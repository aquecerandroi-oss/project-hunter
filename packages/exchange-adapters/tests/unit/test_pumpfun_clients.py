import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import ExchangeError, MalformedMessage, RateLimited
from hunter_exchanges.pumpfun.rest import PumpFunRestClient
from hunter_exchanges.pumpfun.rpc import SolanaRpcClient
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


@pytest.mark.parametrize("status", [404, 429, 503])
async def test_rest_errors(status: int) -> None:
    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(lambda _: httpx.Response(status))
    ) as http:
        client = PumpFunRestClient(http_client=http, max_retries=1)
        with pytest.raises(ExchangeError):
            await client.get_curve_state("mint")


async def test_rest_all_routes() -> None:
    coin: dict[str, Any] = json.loads(
        (FIXTURES / "frontend_api_v3_coin_by_mint_response_raw.json").read_text()
    )
    paths: list[str] = []
    listing_raw = json.loads((FIXTURES / "mayhem_list_raw.json").read_text())
    overview_raw = json.loads((FIXTURES / "mayhem_overview_raw.json").read_text())

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(str(request.url))
        if request.url.path == "/coins/mayhem-mode":
            return httpx.Response(200, json=listing_raw)
        if request.url.path == "/mayhem/overview":
            return httpx.Response(200, json=overview_raw)
        return httpx.Response(200, json=coin)

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = PumpFunRestClient(http_client=http)
        state = await client.get_curve_state(str(coin["mint"]))
        listing = await client.list_mayhem(limit=1, mayhem_state="paused")
        overview = await client.get_mayhem_overview()
        assert state.mint == coin["mint"]
        assert listing[0].mint == listing_raw[0]["mint"]
        assert overview.source == "pumpfun_rest"
        assert overview.metadata["activeCoins"] == overview_raw["activeCoins"]
        assert "mayhemState=paused" in paths[1]


async def test_rpc_finalized_read() -> None:
    payload: dict[str, Any] = json.loads(
        (FIXTURES / "rpc_get_account_info_bonding_curve_raw.json").read_text()
    )

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["method"] == "getAccountInfo"
        assert body["params"] == ["curve", {"encoding": "base64", "commitment": "finalized"}]
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = SolanaRpcClient(http_client=http)
        state = await client.get_curve_state("mint", "curve")
        assert state.source == "solana_rpc"
        assert state.commitment == "finalized"
        assert state.slot == 446342118
        assert state.mayhem_enabled is True


@pytest.mark.parametrize(
    "payload", [{"error": {"code": -32000}}, {"result": {"value": None}}, {"result": {"value": {}}}]
)
async def test_rpc_rejects_missing_account(payload: dict[str, Any]) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as http:
        with pytest.raises((ExchangeError, MalformedMessage)):
            await SolanaRpcClient(http_client=http).get_curve_state("mint", "curve")


async def test_rest_bucket_waits_after_60() -> None:
    now = [0.0]
    waits: list[float] = []

    async def sleep(delay: float) -> None:
        waits.append(delay)
        now[0] += delay

    limiter = TokenBucketRateLimiter(
        "pumpfun", capacity=60, refill_period_s=60, clock=lambda: now[0], sleep=sleep
    )
    for _ in range(61):
        await limiter.acquire("coins", 1)
    assert sum(waits) == pytest.approx(1)


async def test_rpc_429_is_not_retried() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"Retry-After": "2"}))
    ) as http:
        with pytest.raises(RateLimited):
            await SolanaRpcClient(http_client=http).get_curve_state("mint", "curve")


async def test_rest_transport_error_redacts_injected_url() -> None:
    def fail(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("https://test/?key=private-test-value")

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(fail)
    ) as http:
        with pytest.raises(ExchangeError) as error:
            await PumpFunRestClient(http_client=http, max_retries=1).get_curve_state("mint")
        assert "private-test-value" not in str(error.value)
