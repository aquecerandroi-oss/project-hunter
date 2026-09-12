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


async def test_rest_global_params_are_read_for_the_coins_creation_instant() -> None:
    """``GET /global-params/{created_timestamp_ms}`` (T4.2d): the curve parameters
    in force when the coin was created — the denominator of progress and the
    fill threshold come from here, never from a constant. The path carries the
    instant; the response is the T4.0c capture's shape."""
    raw: dict[str, Any] = {
        "slot": 354155511,
        "signature": "5" * 88,
        "initial_virtual_token_reserves": 1073000000000000,
        "initial_virtual_sol_reserves": 30000000000,
        "initial_virtual_quote_reserves": 4292000000,
        "initial_real_token_reserves": 793100000000000,
        "token_total_supply": 1000000000000000,
        "fee_basis_points": 95,
        "timestamp": 1752856476446,
    }
    paths: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=raw)

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        params = await PumpFunRestClient(http_client=http).get_global_params(1789184732000)
        assert paths == ["/global-params/1789184732000"]
        assert params.initial_real_token_reserves == 793100000000000
        assert params.timestamp == 1752856476446
    async with httpx.AsyncClient(
        base_url="https://test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=[raw])),
    ) as http:
        with pytest.raises(MalformedMessage):
            await PumpFunRestClient(http_client=http).get_global_params(1789184732000)


async def test_rest_sol_price_is_a_quote_with_its_instant_and_staleness() -> None:
    """``/sol-price`` as captured live on 2026-09-12 02:34 BRT (plantão meme, run 1):
    the price becomes a ``Decimal`` from the JSON number, ``asOfTimestamp`` (epoch
    ms) becomes an aware UTC instant, and ``stale`` is carried, not assumed."""
    raw: dict[str, Any] = json.loads((FIXTURES / "sol_price_raw.json").read_text())

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/sol-price"
        return httpx.Response(200, content=json.dumps(raw))

    async with httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(respond)
    ) as http:
        client = PumpFunRestClient(http_client=http)
        quote = await client.get_sol_price()
    assert quote.source == "pumpfun_rest:/sol-price"
    assert str(quote.price_usd).startswith("101.4445")
    assert quote.as_of.isoformat() == "2026-09-12T05:34:01.238000+00:00"
    assert quote.stale is False
    assert quote.observed_at.tzinfo is not None


@pytest.mark.parametrize("payload", [[1], {"solPrice": "abc", "asOfTimestamp": 1}, {"solPrice": 1}])
async def test_rest_sol_price_refuses_a_malformed_quote(payload: Any) -> None:
    async with httpx.AsyncClient(
        base_url="https://test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps(payload))),
    ) as http:
        client = PumpFunRestClient(http_client=http, max_retries=1)
        with pytest.raises(MalformedMessage):
            await client.get_sol_price()


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
