"""Binance USDS-M Futures REST client — public endpoints only.

``docs/EXCHANGE_INTEGRATION.md`` §5: every call goes through the shared
:class:`~hunter_exchanges.rate_limit.TokenBucketRateLimiter` (``request_weight``
bucket, official per-endpoint weights below) before hitting the network;
``X-MBX-USED-WEIGHT-1M`` on every response reconciles the bucket, and a
``429``/``418`` response becomes :class:`~hunter_exchanges.base.RateLimited`
straight from ``Retry-After`` — never a silent retry loop (CLAUDE.md /
``exchange-integration-specialist.md``: "A 429/418 is a system_event, never a
silent retry loop"). A network error or ``5xx`` retries with backoff and
becomes :class:`~hunter_exchanges.base.ExchangeUnavailable` after
``max_retries`` attempts — the caller sees UNAVAILABLE, never an invented
number.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import httpx

from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedFunding,
    NormalizedMarket,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
)
from hunter_exchanges.base import ExchangeError, ExchangeUnavailable, RateLimited
from hunter_exchanges.binance import normalize
from hunter_exchanges.rate_limit import IpRateGate, TokenBucketRateLimiter

BASE_URL = "https://fapi.binance.com"
REQUEST_WEIGHT_BUCKET = "request_weight"
#: Binance documents ``GET /fapi/v1/fundingRate`` separately: 500 requests /
#: 5 minutes / IP, independent of the shared ``request_weight`` budget
#: (docs/EXCHANGE_INTEGRATION.md §5 / Astra review, T1.2 resume finding 7).
FUNDING_HISTORY_BUCKET = "funding_history"
FUNDING_HISTORY_CAPACITY = 500
FUNDING_HISTORY_WINDOW_S = 300.0
_KLINES_PAGE_LIMIT = 1500
_USED_WEIGHT_HEADER = "X-MBX-USED-WEIGHT-1M"


def _klines_weight(limit: int) -> int:
    """Weight table for ``GET /fapi/v1/klines`` (Binance USDS-M Futures docs)."""
    if limit < 100:
        return 1
    if limit < 500:
        return 2
    if limit < 1000:
        return 5
    return 10


def _depth_weight(limit: int) -> int:
    """Weight table for ``GET /fapi/v1/depth``."""
    if limit <= 50:
        return 2
    if limit <= 100:
        return 5
    if limit <= 500:
        return 10
    return 20


class BinanceRestClient:
    """Public REST endpoints for Binance USDS-M Futures.

    ``clock``/``sleep`` are injectable so retry backoff never actually waits
    in unit tests; ``http_client`` lets tests inject a transport that serves
    fixtures instead of the network (``httpx.MockTransport``).
    """

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        funding_rate_limiter: TokenBucketRateLimiter | None = None,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 10.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(10.0, connect=5.0)
        )
        self._rate_limiter = rate_limiter or TokenBucketRateLimiter("binance")
        # A dedicated, smaller bucket for the funding history endpoint's own
        # IP-wide limit — sharing the same Redis connection (when there is
        # one) as the main limiter so every process on this IP sees the same
        # budget, but never the same capacity/refill rate as request_weight.
        self._funding_rate_limiter = funding_rate_limiter or TokenBucketRateLimiter(
            "binance",
            redis=self._rate_limiter.redis,
            capacity=FUNDING_HISTORY_CAPACITY,
            refill_period_s=FUNDING_HISTORY_WINDOW_S,
        )
        # F4: a 429/418 is per-IP, not per-bucket. One gate, shared by every
        # bucket this client owns (whether built here or injected by the
        # caller), so a Retry-After on the funding-history bucket also stops
        # the very next request_weight call instead of escalating a 429 into
        # a 418 IP ban.
        self._ip_gate = IpRateGate()
        self._rate_limiter.ip_gate = self._ip_gate
        self._funding_rate_limiter.ip_gate = self._ip_gate
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._sleep = sleep

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _backoff(self, attempt: int) -> None:
        delay = min(self._backoff_max_s, self._backoff_base_s * (2**attempt))
        await self._sleep(delay + random.uniform(0, delay * 0.1))

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        weight: int,
        limiter: TokenBucketRateLimiter | None = None,
        bucket: str = REQUEST_WEIGHT_BUCKET,
    ) -> Any:
        limiter = limiter or self._rate_limiter
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            is_last_attempt = attempt == self._max_retries - 1
            # Charged every attempt, not just the first: a retry is a real
            # HTTP request Binance's own weight accounting counts too (Astra
            # review, T1.2 resume: acquiring once let 3 requests through on
            # 1 unit of budget).
            await limiter.acquire(bucket, weight)
            try:
                response = await self._client.get(path, params=params)
            except httpx.TransportError as exc:
                last_exc = ExchangeUnavailable(
                    f"binance transport error: {exc}", exchange="binance"
                )
                if not is_last_attempt:
                    await self._backoff(attempt)
                continue
            used_weight = response.headers.get(_USED_WEIGHT_HEADER)
            # The used-weight header always reflects request_weight, never a
            # dedicated per-endpoint limit (e.g. funding history) — applying
            # it there would let a shared-IP request_weight burst resurrect
            # budget this bucket never actually spent.
            if used_weight is not None and bucket == REQUEST_WEIGHT_BUCKET:
                await limiter.record_used_weight(bucket, int(used_weight))
            if response.status_code in (429, 418):
                # This process's own budget stops believing it has room the
                # instant the exchange says otherwise (Astra review, T1.2
                # resume) — never a silent retry loop either way. The
                # Retry-After also gates every other bucket on this IP (F4)
                # so a weight-1 call on a different bucket 25ms later can't
                # escalate the 429 into a 418 ban.
                retry_after = float(response.headers.get("Retry-After", "60"))
                await limiter.cooldown(bucket, retry_after_s=retry_after)
                raise RateLimited(
                    f"binance responded {response.status_code} for {path}",
                    exchange="binance",
                    retry_after_s=retry_after,
                )
            if response.status_code >= 500:
                last_exc = ExchangeUnavailable(
                    f"binance {response.status_code} for {path}", exchange="binance"
                )
                if not is_last_attempt:
                    await self._backoff(attempt)
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # Any other 4xx (bad/delisted symbol, bad param, ...): never
                # the adapter's own exception hierarchy leaking a raw httpx
                # type past this module (Astra review, T1.2b resume finding
                # 8) — and never retryable, since retrying the same request
                # yields the same client error every time.
                raise ExchangeError(
                    f"binance {response.status_code} for {path}: {response.text[:200]}",
                    exchange="binance",
                    retryable=False,
                ) from exc
            return response.json()
        raise last_exc or ExchangeUnavailable(
            f"binance request failed after retries: {path}", exchange="binance"
        )

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]:
        """Only :class:`MarketType.PERPETUAL` is supported in the MVP scope."""
        if market_type is not MarketType.PERPETUAL:
            raise ValueError(f"binance adapter only lists PERPETUAL markets, got {market_type}")
        raw = await self._get("/fapi/v1/exchangeInfo", weight=1)
        return normalize.parse_exchange_info(raw)

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[NormalizedCandle]:
        if timeframe is not Timeframe.M1:
            raise ValueError(f"binance adapter only fetches 1m candles in the MVP, got {timeframe}")
        candles: list[NormalizedCandle] = []
        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        # Exchange time, not local: T1.3's bootstrap cuts "is this candle
        # closed" by the server's own clock (docs/plans/M1.md "Decisão
        # conjunta") so local clock drift never mis-marks an already-closed
        # candle as still forming (or the reverse).
        now = await self.server_time()
        while cursor_ms < end_ms:
            raw = await self._get(
                "/fapi/v1/klines",
                params={
                    "symbol": symbol,
                    "interval": "1m",
                    "startTime": cursor_ms,
                    "endTime": end_ms,
                    "limit": _KLINES_PAGE_LIMIT,
                },
                weight=_klines_weight(_KLINES_PAGE_LIMIT),
            )
            if not raw:
                break
            page = normalize.parse_klines(raw, symbol=symbol, now=now)
            candles.extend(page)
            last_open_ms = raw[-1][0]
            if last_open_ms <= cursor_ms:
                break
            cursor_ms = last_open_ms + 60_000
            if len(raw) < _KLINES_PAGE_LIMIT:
                break
        return candles

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker:
        raw = await self._get("/fapi/v1/ticker/24hr", params={"symbol": symbol}, weight=1)
        return normalize.parse_ticker_24h(raw)

    async def fetch_tickers_24h(self) -> list[NormalizedTicker]:
        """All-symbols variant of ``ticker/24hr`` (weight 40) for universe ranking."""
        raw = await self._get("/fapi/v1/ticker/24hr", weight=40)
        return [normalize.parse_ticker_24h(entry) for entry in raw]

    async def fetch_order_book(self, symbol: str, depth: int = 25) -> NormalizedOrderBook:
        limit = depth if depth in (5, 10, 20, 50, 100, 500, 1000) else 20
        raw = await self._get(
            "/fapi/v1/depth", params={"symbol": symbol, "limit": limit}, weight=_depth_weight(limit)
        )
        return normalize.parse_order_book(raw, symbol=symbol)

    async def fetch_funding(self, symbol: str) -> NormalizedFunding:
        """The *estimated*, not-yet-settled funding rate (F1: single
        ``/fapi/v1/premiumIndex`` call, weight 1). Realized/settled history
        is a distinct call — :meth:`fetch_realized_funding`."""
        premium = await self._get("/fapi/v1/premiumIndex", params={"symbol": symbol}, weight=1)
        return normalize.parse_funding(premium, symbol=symbol)

    async def fetch_realized_funding(
        self, symbol: str, start: datetime, end: datetime | None = None, *, limit: int = 1000
    ) -> list[NormalizedFunding]:
        """``GET /fapi/v1/fundingRate`` — settled funding history (``funding_kind="realized"``).

        Its own ``rl:binance:funding_history`` bucket, weight 1
        (docs/EXCHANGE_INTEGRATION.md §5): separate from ``request_weight``.
        Paginates internally (F13) like :meth:`fetch_candles`: a page caps
        at ``limit`` (Binance's max 1000 rows, ~333 days of 8h settlements)
        — a long-lived market's full history would otherwise silently stop
        at the first page. Advances ``startTime`` past the last row's own
        ``fundingTime`` every iteration; stops on a short page (fewer than
        ``limit`` rows: no more data), on reaching ``end``, or if a page
        somehow fails to advance the cursor (never spins forever).
        """
        rows: list[NormalizedFunding] = []
        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000) if end is not None else None
        while end_ms is None or cursor_ms <= end_ms:
            params: dict[str, Any] = {"symbol": symbol, "startTime": cursor_ms, "limit": limit}
            if end_ms is not None:
                params["endTime"] = end_ms
            raw = await self._get(
                "/fapi/v1/fundingRate",
                params=params,
                weight=1,
                limiter=self._funding_rate_limiter,
                bucket=FUNDING_HISTORY_BUCKET,
            )
            if not raw:
                break
            rows.extend(normalize.parse_realized_funding(entry) for entry in raw)
            last_funding_ms = int(raw[-1]["fundingTime"])
            if last_funding_ms <= cursor_ms:
                break  # cursor didn't advance: stop rather than loop forever
            cursor_ms = last_funding_ms + 1
            if len(raw) < limit:
                break  # short page: no more rows exist
        return rows

    async def fetch_open_interest(self, symbol: str) -> NormalizedOpenInterest:
        raw = await self._get("/fapi/v1/openInterest", params={"symbol": symbol}, weight=1)
        return normalize.parse_open_interest(raw, symbol=symbol)

    async def server_time(self) -> datetime:
        """``GET /fapi/v1/time`` — the exchange's own clock.

        T1.3's recovery bootstrap cuts its "closed candle" window by this,
        never by the local clock (``docs/plans/M1.md`` "Decisão conjunta").
        Not part of the ``ExchangeAdapter`` Protocol (``base.py``) yet: kept
        Binance-specific/additive here so it does not force every other fake
        adapter in the tree to grow the method mid-milestone.
        """
        raw = await self._get("/fapi/v1/time", weight=1)
        return normalize.parse_server_time(raw)
