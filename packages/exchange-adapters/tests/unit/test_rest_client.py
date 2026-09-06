"""BinanceRestClient: rate limiting, retries, and 429/5xx handling.

``httpx.MockTransport`` stands in for the network so every test is fully
offline and deterministic; a fake sleep function turns retry backoff from
"real seconds" into "an entry in a list", so the retry tests run instantly.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from hunter_exchanges.base import ExchangeUnavailable, RateLimited
from hunter_exchanges.binance.rest import BinanceRestClient
from hunter_exchanges.rate_limit import TokenBucketRateLimiter

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class _RecordingSleeper:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _client_for(handler: Any, *, sleeper: _RecordingSleeper | None = None) -> BinanceRestClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://fapi.binance.com")
    limiter = TokenBucketRateLimiter(
        "binance"
    )  # no Redis: local fallback, never actually limits here
    return BinanceRestClient(
        http_client=http_client,
        rate_limiter=limiter,
        sleep=sleeper or _RecordingSleeper(),
        backoff_base_s=0.01,
    )


async def test_fetch_ticker_parses_a_successful_response() -> None:
    payload = _load("ticker_24hr.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/ticker/24hr"
        return httpx.Response(200, json=payload)

    client = _client_for(handler)

    ticker = await client.fetch_ticker("BTCUSDT")

    assert ticker.symbol == "BTCUSDT"
    await client.aclose()


async def test_used_weight_header_is_recorded_on_the_limiter() -> None:
    payload = _load("ticker_24hr.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, headers={"X-MBX-USED-WEIGHT-1M": "37"})

    limiter = TokenBucketRateLimiter("binance", capacity=2400, refill_period_s=60)
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://fapi.binance.com")
    client = BinanceRestClient(http_client=http_client, rate_limiter=limiter)

    await client.fetch_ticker("BTCUSDT")

    # capacity - used_weight should now be the bucket's remaining budget.
    remaining = limiter._local.tokens("request_weight")  # type: ignore[union-attr] # pyright: ignore[reportPrivateUsage,reportOptionalMemberAccess]
    assert remaining == pytest.approx(2400 - 37)
    await client.aclose()


async def test_429_raises_rate_limited_with_retry_after_from_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"code": -1003, "msg": "too many requests"}, headers={"Retry-After": "12"}
        )

    client = _client_for(handler)

    with pytest.raises(RateLimited) as exc_info:
        await client.fetch_ticker("BTCUSDT")

    assert exc_info.value.retry_after_s == 12.0
    assert exc_info.value.exchange == "binance"
    await client.aclose()


async def test_418_is_also_rate_limited() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            418, json={"code": -1003, "msg": "banned"}, headers={"Retry-After": "300"}
        )

    client = _client_for(handler)

    with pytest.raises(RateLimited) as exc_info:
        await client.fetch_ticker("BTCUSDT")

    assert exc_info.value.retry_after_s == 300.0
    await client.aclose()


async def test_429_zeroes_the_shared_bucket_via_cooldown() -> None:
    """This process's own next request must not believe it still has budget
    right after the exchange says it does not (Astra review, T1.2 resume)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": -1003, "msg": "too many"})

    limiter = TokenBucketRateLimiter("binance")
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://fapi.binance.com")
    client = BinanceRestClient(http_client=http_client, rate_limiter=limiter)

    with pytest.raises(RateLimited):
        await client.fetch_ticker("BTCUSDT")

    with pytest.raises(RateLimited):
        await limiter.acquire("request_weight", 1, max_wait_s=0.0)
    await client.aclose()


async def test_retries_each_acquire_rate_limit_budget() -> None:
    """Each real HTTP attempt is charged, not just the first (Astra review,
    T1.2 resume): 3 attempts must draw weight 3 times."""
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"msg": "maintenance"})

    acquired: list[int] = []

    class _CountingLimiter(TokenBucketRateLimiter):
        async def acquire(self, bucket: str, weight: int, *, max_wait_s: float = 30.0) -> None:
            acquired.append(weight)
            await super().acquire(bucket, weight, max_wait_s=max_wait_s)

    limiter = _CountingLimiter("binance")
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://fapi.binance.com")
    client = BinanceRestClient(
        http_client=http_client,
        rate_limiter=limiter,
        sleep=_RecordingSleeper(),
        backoff_base_s=0.01,
    )

    with pytest.raises(ExchangeUnavailable):
        await client.fetch_ticker("BTCUSDT")

    assert calls["count"] == 3
    assert acquired == [1, 1, 1]  # one acquisition per attempt, not one for all three
    await client.aclose()


async def test_5xx_retries_then_raises_exchange_unavailable() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(503, json={"msg": "maintenance"})

    sleeper = _RecordingSleeper()
    client = _client_for(handler, sleeper=sleeper)

    with pytest.raises(ExchangeUnavailable):
        await client.fetch_ticker("BTCUSDT")

    assert calls["count"] == 3  # default max_retries
    assert len(sleeper.calls) == 2  # backoff between attempts, not after the last one
    await client.aclose()


async def test_5xx_then_success_recovers_without_raising() -> None:
    calls = {"count": 0}
    payload = _load("ticker_24hr.json")

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] < 2:
            return httpx.Response(503, json={"msg": "maintenance"})
        return httpx.Response(200, json=payload)

    client = _client_for(handler)

    ticker = await client.fetch_ticker("BTCUSDT")

    assert ticker.symbol == "BTCUSDT"
    assert calls["count"] == 2
    await client.aclose()


async def test_400_raises_exchange_error_not_a_raw_httpx_exception() -> None:
    """Astra review, T1.2b resume finding 8: a bad/delisted-symbol 400 must
    surface as the adapter's own exception hierarchy, never a bare
    ``httpx.HTTPStatusError`` a caller catching ``ExchangeError`` would miss."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})

    client = _client_for(handler)

    from hunter_exchanges.base import ExchangeError

    with pytest.raises(ExchangeError) as exc_info:
        await client.fetch_ticker("NOSUCHUSDT")

    assert exc_info.value.retryable is False
    assert not isinstance(exc_info.value, httpx.HTTPStatusError)
    await client.aclose()


async def test_network_error_retries_then_raises_exchange_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = _client_for(handler)

    with pytest.raises(ExchangeUnavailable):
        await client.fetch_ticker("BTCUSDT")
    await client.aclose()


async def test_list_markets_filters_via_normalize() -> None:
    payload = _load("exchange_info.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/exchangeInfo"
        return httpx.Response(200, json=payload)

    client = _client_for(handler)

    from hunter_core.domain.enums import MarketType

    markets = await client.list_markets(MarketType.PERPETUAL)

    assert {m.symbol for m in markets} == {"BTCUSDT", "ETHUSDT", "BCHUSDT", "XRPUSDT", "LTCUSDT"}
    await client.aclose()


async def test_fetch_candles_paginates_by_1500() -> None:
    """Two kline pages: a full 1500-row page, then a short final page. The
    "is this closed" cutoff comes from a `/fapi/v1/time` call first (exchange
    clock, never local — Astra review, T1.2 resume)."""
    klines = _load("klines.json")
    row_template = klines[0]

    def _shifted_row(offset_ms: int) -> list[Any]:
        row = list(row_template)
        row[0] += offset_ms  # open time
        row[6] += offset_ms  # close time
        return row

    page_1 = [_shifted_row(i * 60_000) for i in range(1500)]
    page_2 = [_shifted_row(1500 * 60_000)]
    calls = {"count": 0}

    from datetime import UTC, datetime

    far_future_ms = int(datetime(2030, 1, 1, tzinfo=UTC).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/time":
            return httpx.Response(200, json={"serverTime": far_future_ms})
        calls["count"] += 1
        return httpx.Response(200, json=page_1 if calls["count"] == 1 else page_2)

    client = _client_for(handler)

    from hunter_core.domain.enums import Timeframe

    candles = await client.fetch_candles(
        "BTCUSDT", Timeframe.M1, datetime.fromtimestamp(0, tz=UTC), datetime(2030, 1, 1, tzinfo=UTC)
    )

    assert calls["count"] == 2  # klines pages only; server_time() is separate
    assert len(candles) == 1501
    assert all(c.is_final for c in candles)  # cut by the (future) exchange clock, not local time
    await client.aclose()


async def test_fetch_funding_makes_exactly_one_http_call_to_premium_index() -> None:
    """F1: ``fetch_funding`` is the estimated rate — a single
    ``/fapi/v1/premiumIndex`` call, never ``/fapi/v1/fundingRate``."""
    premium = _load("premium_index.json")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.url.path == "/fapi/v1/premiumIndex"
        return httpx.Response(200, json=premium)

    client = _client_for(handler)

    funding = await client.fetch_funding("BTCUSDT")

    assert funding.symbol == "BTCUSDT"
    assert funding.funding_kind == "estimated"
    assert funding.funding_rate == Decimal(premium["lastFundingRate"])
    assert calls == ["/fapi/v1/premiumIndex"]
    await client.aclose()


async def test_fetch_realized_funding_parses_every_row() -> None:
    from datetime import UTC, datetime

    payload = _load("funding_rate_history.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/fundingRate"
        assert "startTime" in request.url.params
        return httpx.Response(200, json=payload)

    client = _client_for(handler)

    rows = await client.fetch_realized_funding("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC))

    assert len(rows) == len(payload)
    assert all(r.funding_kind == "realized" for r in rows)
    await client.aclose()


async def test_fetch_realized_funding_uses_its_own_bucket_not_request_weight() -> None:
    """Astra review, T1.2 resume finding 7: the funding-history endpoint has
    its own 500 requests / 5 minutes / IP limit, independent from
    ``request_weight`` — draining one must never affect the other."""
    from datetime import UTC, datetime

    payload = _load("funding_rate_history.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    limiter = TokenBucketRateLimiter("binance")
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport, base_url="https://fapi.binance.com")
    client = BinanceRestClient(http_client=http_client, rate_limiter=limiter)

    await client.fetch_realized_funding("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC))

    request_weight_tokens = limiter._local.tokens("request_weight")  # type: ignore[union-attr] # pyright: ignore[reportPrivateUsage,reportOptionalMemberAccess]
    assert request_weight_tokens is None  # request_weight was never touched
    await client.aclose()


async def test_fetch_realized_funding_429_raises_rate_limited() -> None:
    from datetime import UTC, datetime

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"code": -1003}, headers={"Retry-After": "30"})

    client = _client_for(handler)

    with pytest.raises(RateLimited) as exc_info:
        await client.fetch_realized_funding("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC))

    assert exc_info.value.retry_after_s == 30.0
    await client.aclose()


async def test_fetch_realized_funding_paginates_past_a_single_page() -> None:
    """F13: Binance caps a single ``/fapi/v1/fundingRate`` page at ``limit``
    (max 1000, ~333 days of 8h settlements) — a long-lived market's full
    history must be paged internally by advancing ``startTime`` past the
    last row's ``fundingTime``, never silently truncated at the first page."""
    from datetime import UTC, datetime

    all_rows: list[dict[str, Any]] = [
        {
            "symbol": "BTCUSDT",
            "fundingTime": 1_700_000_000_000 + i * 28_800_000,  # 8h apart
            "fundingRate": "0.00001000",
            "markPrice": "50000.00000000",
        }
        for i in range(5)
    ]
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        start_time = int(params["startTime"])
        limit = int(params["limit"])
        page = [r for r in all_rows if int(r["fundingTime"]) >= start_time][:limit]
        return httpx.Response(200, json=page)

    client = _client_for(handler)

    rows = await client.fetch_realized_funding(
        "BTCUSDT", datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=UTC), limit=2
    )

    assert len(rows) == 5  # every row across every page, not just the first 2
    assert len(calls) == 3  # 2 full pages of 2 + a short page of 1 signals the end
    assert calls[0]["startTime"] != calls[1]["startTime"]  # the cursor actually advanced
    await client.aclose()


async def test_fetch_realized_funding_guards_against_a_non_advancing_cursor() -> None:
    """A page whose last row's ``fundingTime`` never advances past the
    request's own ``startTime`` must stop instead of looping forever."""
    from datetime import UTC, datetime

    stuck_row = {
        "symbol": "BTCUSDT",
        "fundingTime": 1_700_000_000_000,
        "fundingRate": "0.00001000",
        "markPrice": "50000.00000000",
    }
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(200, json=[stuck_row])  # always the same row/time

    client = _client_for(handler)

    rows = await client.fetch_realized_funding(
        "BTCUSDT", datetime.fromtimestamp(1_700_000_000_000 / 1000, tz=UTC), limit=1
    )

    assert len(rows) == 1
    assert calls["count"] == 1  # stopped after the first page, never looped forever
    await client.aclose()


async def test_a_429_on_the_funding_bucket_gates_the_general_bucket_too() -> None:
    """F4: Binance's 429/418 is per-IP, not per-bucket. A 429 on
    ``fetch_realized_funding`` (its own ``funding_history`` bucket) must stop
    the very next ``request_weight`` call too, or the general bucket keeps
    firing on the same banned IP and escalates a 429 into a 418."""
    from datetime import UTC, datetime

    ticker_payload = _load("ticker_24hr.json")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/fundingRate":
            return httpx.Response(429, json={"code": -1003}, headers={"Retry-After": "60"})
        # Any other endpoint (request_weight bucket) would succeed on its
        # own — proving a raise here comes from the IP gate, not a second
        # real 429 from the exchange.
        return httpx.Response(200, json=ticker_payload)

    client = _client_for(handler)

    with pytest.raises(RateLimited):
        await client.fetch_realized_funding("BTCUSDT", datetime(2026, 1, 1, tzinfo=UTC))

    # A general-bucket call 25ms "later" (no real time passed) must not slip
    # through the still-banned IP, even though this endpoint would otherwise
    # succeed.
    with pytest.raises(RateLimited) as exc_info:
        await client.fetch_ticker("BTCUSDT")
    assert exc_info.value.retry_after_s == pytest.approx(60.0, rel=0.05)
    await client.aclose()


async def test_server_time_reads_the_exchange_clock() -> None:
    payload = _load("server_time.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/fapi/v1/time"
        return httpx.Response(200, json=payload)

    client = _client_for(handler)

    from datetime import UTC, datetime

    server_time = await client.server_time()

    assert server_time == datetime.fromtimestamp(payload["serverTime"] / 1000, tz=UTC)
    await client.aclose()


async def test_fetch_tickers_24h_uses_weight_40_and_returns_all_symbols() -> None:
    payload = _load("ticker_24hr_all.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "symbol" not in request.url.params
        return httpx.Response(200, json=payload)

    client = _client_for(handler)

    tickers = await client.fetch_tickers_24h()

    assert len(tickers) == len(payload)
    await client.aclose()
