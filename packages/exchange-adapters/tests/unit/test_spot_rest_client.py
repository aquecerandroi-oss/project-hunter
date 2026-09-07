"""BinanceSpotRestClient: official spot weights, 429/418, retries, pagination.

``httpx.MockTransport`` stands in for the network so every test is offline;
the weights asserted here are the ones measured against the real API on
2026-09-06 (``x-mbx-used-weight-1m`` deltas, see the T3.0a report) and
declared in ``rest.py``'s table.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from hunter_core.domain.enums import MarketType, Timeframe
from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, RateLimited
from hunter_exchanges.binance_spot.rest import (
    REQUEST_WEIGHT_BUCKET,
    REQUEST_WEIGHT_CAPACITY,
    BinanceSpotRestClient,
)
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


class _SpyLimiter:
    """Records what was charged to which bucket, and never actually waits."""

    def __init__(self) -> None:
        self.acquired: list[tuple[str, int]] = []
        self.cooldowns: list[tuple[str, float]] = []
        self.used_weights: list[tuple[str, int]] = []
        self.redis: Any = None
        self.suspended = False
        self.ip_gate: Any = None

    async def acquire(self, bucket: str, weight: int = 1) -> None:
        self.acquired.append((bucket, weight))

    async def cooldown(self, bucket: str, *, retry_after_s: float) -> None:
        self.cooldowns.append((bucket, retry_after_s))

    async def record_used_weight(self, bucket: str, used: int) -> None:
        self.used_weights.append((bucket, used))


Handler = Callable[[httpx.Request], httpx.Response]


def _always(
    status: int = 200, *, body: Any = None, headers: dict[str, str] | None = None
) -> Handler:
    """A MockTransport handler that answers every request the same way."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body, headers=headers)

    return handler


def _client(
    handler: Handler,
    *,
    limiter: Any = None,
    sleeper: _RecordingSleeper | None = None,
    klines_page_limit: int = 1000,
) -> BinanceSpotRestClient:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://api.binance.com"
    )
    return BinanceSpotRestClient(
        http_client=http_client,
        rate_limiter=cast("TokenBucketRateLimiter", limiter or _SpyLimiter()),
        sleep=sleeper or _RecordingSleeper(),
        backoff_base_s=0.01,
        klines_page_limit=klines_page_limit,
    )


async def test_list_markets_calls_api_v3_and_returns_spot_markets() -> None:
    payload = _load("spot_exchange_info.json")
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, json=payload)

    limiter = _SpyLimiter()
    client = _client(handler, limiter=limiter)

    markets = await client.list_markets(MarketType.SPOT)

    assert seen == ["/api/v3/exchangeInfo"]
    assert {m.symbol for m in markets} == {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT"}
    assert all(m.market_type is MarketType.SPOT for m in markets)
    assert limiter.acquired == [(REQUEST_WEIGHT_BUCKET, 20)]
    await client.aclose()


async def test_list_markets_refuses_a_perpetual_request() -> None:
    client = _client(_always(body={}))

    with pytest.raises(ValueError, match="SPOT"):
        await client.list_markets(MarketType.PERPETUAL)
    await client.aclose()


async def test_fetch_filters_exposes_the_market_order_rules_per_symbol() -> None:
    payload = _load("spot_exchange_info.json")
    client = _client(_always(body=payload))

    filters = await client.fetch_filters()

    assert filters["BTCUSDT"].step_size == Decimal("0.00001000")
    assert filters["BTCUSDT"].apply_min_to_market is True
    await client.aclose()


async def test_the_request_weight_budget_comes_from_the_exchange_itself() -> None:
    """6000/min is what ``exchangeInfo.rateLimits`` says today - the client
    re-reads it and adjusts instead of trusting a hardcoded constant."""
    payload = _load("spot_exchange_info.json")
    limiter = TokenBucketRateLimiter(
        "binance", capacity=REQUEST_WEIGHT_CAPACITY, refill_period_s=60
    )
    client = _client(_always(body=payload), limiter=limiter)

    reported = await client.refresh_request_weight_limit()

    assert reported == (REQUEST_WEIGHT_CAPACITY, 60.0) == (6000, 60.0)
    await client.aclose()


@pytest.mark.parametrize(
    ("depth", "expected_weight"),
    [(20, 5), (100, 5), (500, 25), (1000, 50)],
)
async def test_depth_weight_follows_the_official_spot_table(
    depth: int, expected_weight: int
) -> None:
    payload = _load("spot_depth.json")
    limiter = _SpyLimiter()
    client = _client(_always(body=payload), limiter=limiter)

    await client.fetch_order_book("BTCUSDT", depth)

    assert limiter.acquired == [(REQUEST_WEIGHT_BUCKET, expected_weight)]
    await client.aclose()


async def test_order_book_uses_the_receive_time_and_the_last_update_id() -> None:
    payload = _load("spot_depth.json")
    client = _client(_always(body=payload))

    book = await client.fetch_order_book("BTCUSDT", 20)

    assert book.sequence == 99769463659
    assert book.ts == book.received_at
    assert book.ts.tzinfo is UTC
    await client.aclose()


async def test_ticker_weights_follow_the_symbol_count_table() -> None:
    single = _load("spot_ticker_24hr.json")
    every = _load("spot_ticker_24hr_all.json")
    limiter = _SpyLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("symbol"):
            return httpx.Response(200, json=single)
        return httpx.Response(200, json=every)

    client = _client(handler, limiter=limiter)

    await client.fetch_ticker("BTCUSDT")
    await client.fetch_tickers_24h(["BTCUSDT", "ETHUSDT"])
    await client.fetch_tickers_24h()

    assert limiter.acquired == [
        (REQUEST_WEIGHT_BUCKET, 2),
        (REQUEST_WEIGHT_BUCKET, 2),
        (REQUEST_WEIGHT_BUCKET, 80),
    ]
    await client.aclose()


async def test_trades_and_agg_trades_have_very_different_weights() -> None:
    limiter = _SpyLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        name = (
            "spot_trades.json" if request.url.path.endswith("/trades") else "spot_agg_trades.json"
        )
        return httpx.Response(200, json=_load(name))

    client = _client(handler, limiter=limiter)

    trades = await client.fetch_trades("BTCUSDT", limit=5)
    agg = await client.fetch_agg_trades("BTCUSDT", limit=5)

    assert len(trades) == 5 and len(agg) == 5
    assert limiter.acquired == [(REQUEST_WEIGHT_BUCKET, 25), (REQUEST_WEIGHT_BUCKET, 4)]
    await client.aclose()


async def test_avg_price_is_fetched_for_the_notional_filter() -> None:
    limiter = _SpyLimiter()
    client = _client(_always(body=_load("spot_avg_price.json")), limiter=limiter)

    avg = await client.fetch_avg_price("BTCUSDT")

    assert avg.price == Decimal("80471.72575004")
    assert avg.mins == 5
    assert limiter.acquired == [(REQUEST_WEIGHT_BUCKET, 2)]
    await client.aclose()


async def test_fetch_candles_paginates_without_ever_repeating_a_candle() -> None:
    """Mandatory case "duplicate candle": Binance's ``startTime`` is
    inclusive, so a second page repeats the last row of the first one.

    The page limit is squeezed to 3 so the client really paginates (a full
    1000-row limit would end on the first short page and never exercise the
    boundary - Astra diff review).
    """
    rows = _load("spot_klines.json")  # 5 rows: 1788738180 .. 1788738420
    pages = [rows[:3], rows[2:]]  # deliberate one-row overlap at 1788738300
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/time"):
            return httpx.Response(200, json={"serverTime": 1788739000000})
        calls.append(dict(request.url.params))
        page = pages[min(len(calls) - 1, len(pages) - 1)]
        return httpx.Response(200, json=page)

    client = _client(handler, klines_page_limit=3)

    candles = await client.fetch_candles(
        "BTCUSDT",
        Timeframe.M1,
        datetime.fromtimestamp(1788738180, tz=UTC),
        datetime.fromtimestamp(1788738480, tz=UTC),
    )

    open_times = [c.open_time for c in candles]
    assert len(calls) >= 2, "the test must actually paginate"
    assert len(open_times) == len(set(open_times))
    assert open_times == sorted(open_times)
    assert [int(t.timestamp()) for t in open_times] == [
        1788738180,
        1788738240,
        1788738300,
        1788738360,
        1788738420,
    ]
    await client.aclose()


async def test_fetch_candles_never_returns_a_bar_outside_the_window() -> None:
    """``[start, end)`` is half-open, but Binance's ``endTime`` is inclusive:
    the bar opening exactly at ``end`` must not come back, and ``endTime`` is
    asked for one millisecond short (Astra diff review, must-fix 2)."""
    rows = _load("spot_klines.json")
    seen_params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/time"):
            return httpx.Response(200, json={"serverTime": 1788739000000})
        seen_params.append(dict(request.url.params))
        return httpx.Response(200, json=rows)  # the exchange sends the end bar too

    client = _client(handler)

    candles = await client.fetch_candles(
        "BTCUSDT",
        Timeframe.M1,
        datetime.fromtimestamp(1788738180, tz=UTC),
        datetime.fromtimestamp(1788738420, tz=UTC),  # the 1788738420 bar is OUT
    )

    assert [int(c.open_time.timestamp()) for c in candles] == [
        1788738180,
        1788738240,
        1788738300,
        1788738360,
    ]
    assert seen_params[0]["endTime"] == str(1788738420 * 1000 - 1)
    await client.aclose()


async def test_fetch_candles_charges_weight_2_per_page() -> None:
    limiter = _SpyLimiter()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/time"):
            return httpx.Response(200, json={"serverTime": 1788739000000})
        return httpx.Response(200, json=_load("spot_klines.json"))

    client = _client(handler, limiter=limiter)

    await client.fetch_candles(
        "BTCUSDT",
        Timeframe.M1,
        datetime.fromtimestamp(1788738180, tz=UTC),
        datetime.fromtimestamp(1788738480, tz=UTC),
    )

    assert (REQUEST_WEIGHT_BUCKET, 2) in limiter.acquired
    assert (REQUEST_WEIGHT_BUCKET, 1) in limiter.acquired  # /api/v3/time
    await client.aclose()


async def test_a_delisted_symbol_is_a_hard_error_not_a_retry_loop() -> None:
    """Mandatory case "delisted symbol": Binance answers ``400 -1121 Invalid
    symbol``; retrying it forever would burn the shared weight budget."""
    sleeper = _RecordingSleeper()

    client = _client(_always(400, body={"code": -1121, "msg": "Invalid symbol."}), sleeper=sleeper)

    with pytest.raises(ExchangeError) as excinfo:
        await client.fetch_ticker("DELISTEDUSDT")

    assert excinfo.value.retryable is False
    assert not isinstance(excinfo.value, RateLimited)
    assert sleeper.calls == []
    await client.aclose()


async def test_429_becomes_rate_limited_and_cools_the_bucket_down() -> None:
    limiter = _SpyLimiter()

    client = _client(
        _always(429, body={"code": -1003}, headers={"Retry-After": "12"}), limiter=limiter
    )

    with pytest.raises(RateLimited) as excinfo:
        await client.fetch_ticker("BTCUSDT")

    assert excinfo.value.retry_after_s == 12
    assert limiter.cooldowns == [(REQUEST_WEIGHT_BUCKET, 12.0)]
    await client.aclose()


async def test_418_is_an_ip_ban_and_never_retried_silently() -> None:
    limiter = _SpyLimiter()
    client = _client(_always(418, headers={"Retry-After": "120"}), limiter=limiter)

    with pytest.raises(RateLimited) as excinfo:
        await client.fetch_ticker("BTCUSDT")

    assert excinfo.value.retry_after_s == 120
    assert len(limiter.acquired) == 1  # charged once, never retried
    await client.aclose()


async def test_used_weight_header_reconciles_the_shared_bucket() -> None:
    limiter = _SpyLimiter()
    client = _client(
        _always(body=_load("spot_ticker_24hr.json"), headers={"X-MBX-USED-WEIGHT-1M": "137"}),
        limiter=limiter,
    )

    await client.fetch_ticker("BTCUSDT")

    assert limiter.used_weights == [(REQUEST_WEIGHT_BUCKET, 137)]
    await client.aclose()


async def test_a_5xx_retries_with_backoff_then_reports_unavailable() -> None:
    sleeper = _RecordingSleeper()
    client = _client(_always(503), sleeper=sleeper)

    with pytest.raises(ExchangeUnavailable):
        await client.fetch_ticker("BTCUSDT")

    assert len(sleeper.calls) == 2  # 3 attempts, 2 waits
    await client.aclose()


async def test_a_malformed_body_is_a_malformed_message_not_a_fake_ticker() -> None:
    client = _client(_always(body={"symbol": "BTCUSDT"}))

    with pytest.raises(ExchangeError):
        await client.fetch_ticker("BTCUSDT")
    await client.aclose()


async def test_the_spot_bucket_is_not_the_usds_m_one() -> None:
    """Same venue, same IP - but ``/api/v3`` and ``/fapi/v1`` have separate
    weight budgets, so they must never share a bucket key."""
    from hunter_exchanges.binance.rest import REQUEST_WEIGHT_BUCKET as FUTURES_BUCKET

    assert REQUEST_WEIGHT_BUCKET != FUTURES_BUCKET
    assert REQUEST_WEIGHT_CAPACITY == 6000
