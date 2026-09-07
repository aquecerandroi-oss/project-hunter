"""Binance **SPOT** public REST endpoints (``/api/v3``) and their weights.

Every call goes through :class:`~hunter_exchanges.binance_spot.http.SpotHttp`
(shared token bucket ``rl:binance:spot_request_weight``, 6000 weight/min per
IP as ``exchangeInfo.rateLimits`` itself reports).

Weight table - **measured** against the real API on 2026-09-06 by reading
the ``x-mbx-used-weight-1m`` delta of each call (never copied blindly, and
different from the USDS-M table):

=================================  ======  ==========================================
Endpoint                           Weight  Used for
=================================  ======  ==========================================
``GET /api/v3/time``                    1  exchange clock for "is this candle closed"
``GET /api/v3/exchangeInfo``           20  universe + MARKET-order filters
``GET /api/v3/klines``                  2  1m candles (any ``limit`` up to 1000)
``GET /api/v3/ticker/24hr`` 1 sym        2  price/volume for one pair
``GET /api/v3/ticker/24hr`` 2-20         2  a small explicit symbol list
``GET /api/v3/ticker/24hr`` 21-100      40  a large explicit symbol list
``GET /api/v3/ticker/24hr`` all         80  the 24h volume floor (D1, >= 50M USDT)
``GET /api/v3/depth`` limit <=100        5  top-20 hot state, top-100 book walk
``GET /api/v3/depth`` limit <=500       25
``GET /api/v3/depth`` limit <=1000      50
``GET /api/v3/trades``                  25  raw trades (expensive: prefer aggTrades)
``GET /api/v3/aggTrades``                4  aggregate trades
``GET /api/v3/avgPrice``                 2  the NOTIONAL reference for MARKET orders
=================================  ======  ==========================================

Spot has **no** funding, open interest, mark price or liquidation endpoint;
the adapter refuses those calls instead of returning an empty answer.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any, cast

import httpx

from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedMarket,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
)
from hunter_core.domain.types import utcnow
from hunter_exchanges.binance_spot import normalize
from hunter_exchanges.binance_spot.filters import SpotMarketFilters, parse_filters
from hunter_exchanges.binance_spot.http import (
    BASE_URL as BASE_URL,
)
from hunter_exchanges.binance_spot.http import (
    REQUEST_WEIGHT_BUCKET as REQUEST_WEIGHT_BUCKET,
)
from hunter_exchanges.binance_spot.http import (
    REQUEST_WEIGHT_CAPACITY as REQUEST_WEIGHT_CAPACITY,
)
from hunter_exchanges.binance_spot.http import (
    REQUEST_WEIGHT_PERIOD_S as REQUEST_WEIGHT_PERIOD_S,
)
from hunter_exchanges.binance_spot.http import (
    SpotHttp,
)
from hunter_exchanges.rate_limit import IpRateGate, TokenBucketRateLimiter

__all__ = [
    "BASE_URL",
    "REQUEST_WEIGHT_BUCKET",
    "REQUEST_WEIGHT_CAPACITY",
    "REQUEST_WEIGHT_PERIOD_S",
    "BinanceSpotRestClient",
]

_KLINES_PAGE_LIMIT = 1000
_VALID_DEPTH_LIMITS = (5, 10, 20, 50, 100, 500, 1000, 5000)


def _depth_weight(limit: int) -> int:
    if limit <= 100:
        return 5
    if limit <= 500:
        return 25
    if limit <= 1000:
        return 50
    return 250


def _ticker_weight(symbol_count: int | None) -> int:
    """``None`` = every symbol (80). 1-20 -> 2, 21-100 -> 40, >100 -> 80."""
    if symbol_count is None or symbol_count > 100:
        return 80
    if symbol_count > 20:
        return 40
    return 2


class BinanceSpotRestClient:
    """Public spot REST endpoints, all Decimal-normalized and rate limited."""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        http_client: httpx.AsyncClient | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        ip_gate: IpRateGate | None = None,
        max_retries: int = 3,
        backoff_base_s: float = 0.5,
        backoff_max_s: float = 10.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], datetime] = utcnow,
        klines_page_limit: int = _KLINES_PAGE_LIMIT,
    ) -> None:
        self._http = SpotHttp(
            base_url=base_url,
            http_client=http_client,
            rate_limiter=rate_limiter,
            ip_gate=ip_gate,
            max_retries=max_retries,
            backoff_base_s=backoff_base_s,
            backoff_max_s=backoff_max_s,
            sleep=sleep,
        )
        self._clock = clock
        # Binance's own maximum is 1000 rows; injectable so a test can make
        # pagination real instead of asserting it never happens.
        self._klines_page_limit = klines_page_limit

    @property
    def ip_gate(self) -> IpRateGate:
        return self._http.ip_gate

    def rest_gate_status(self) -> str:
        return self._http.rest_gate_status()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]:
        """USDT spot pairs that are actually ``TRADING`` (weight 20)."""
        if market_type is not MarketType.SPOT:
            raise ValueError(f"binance spot adapter only lists SPOT markets, got {market_type}")
        raw = await self._http.get("/api/v3/exchangeInfo", weight=20)
        return normalize.parse_exchange_info(raw)

    async def fetch_filters(
        self, symbols: Sequence[str] | None = None
    ) -> dict[str, SpotMarketFilters]:
        """Every MARKET-order filter, by symbol (weight 20).

        The paper executor needs these to round a quantity and to refuse one
        under ``minNotional`` - they are the same ``exchangeInfo`` payload
        :meth:`list_markets` reads, exposed without the universe filtering.
        """
        raw = await self._http.get("/api/v3/exchangeInfo", weight=20)
        wanted = set(symbols) if symbols is not None else None
        return {
            entry["symbol"]: parse_filters(entry)
            for entry in raw.get("symbols", [])
            if wanted is None or entry["symbol"] in wanted
        }

    async def refresh_request_weight_limit(self) -> tuple[int, float]:
        """Ask the exchange what the REQUEST_WEIGHT budget is (weight 20).

        Returned for the caller to log/compare; a change here means the
        constant in ``http.py`` (and the bucket capacity) must move with it.
        """
        raw = await self._http.get("/api/v3/exchangeInfo", weight=20)
        return normalize.parse_request_weight_limit(raw)

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[NormalizedCandle]:
        """1m candles in ``[start, end)`` - half-open, paginated, never duplicated.

        Two Binance conventions bite here and both are handled explicitly
        (Astra diff review, T3.0a must-fix 2):

        - ``startTime`` **and** ``endTime`` are inclusive, so asking for
          ``[12:00, 12:30)`` with ``endTime = 12:30`` returns the 12:30 bar
          too - a bar outside the window the caller asked for, which would
          quietly contaminate a historical volume window. ``endTime`` is sent
          one millisecond short and the result is filtered to
          ``start <= open_time < end`` regardless;
        - a page boundary repeats a row unless the cursor moves past it, so
          rows are de-duplicated by ``open_time``: the same minute can never
          come back as two candles.
        """
        if timeframe is not Timeframe.M1:
            raise ValueError(f"binance spot adapter only fetches 1m candles, got {timeframe}")
        candles: list[NormalizedCandle] = []
        seen: set[datetime] = set()
        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        now = await self.server_time()
        while cursor_ms < end_ms:
            raw = await self._http.get(
                "/api/v3/klines",
                params={
                    "symbol": symbol,
                    "interval": "1m",
                    "startTime": cursor_ms,
                    "endTime": end_ms - 1,  # inclusive on Binance's side
                    "limit": self._klines_page_limit,
                },
                weight=2,
            )
            if not raw:
                break
            for candle in normalize.parse_klines(raw, symbol=symbol, now=now):
                if candle.open_time in seen:
                    continue
                if not (start <= candle.open_time < end):
                    continue  # never a bar outside the requested window
                seen.add(candle.open_time)
                candles.append(candle)
            last_open_ms = int(raw[-1][0])
            if last_open_ms < cursor_ms:
                break
            cursor_ms = last_open_ms + 60_000
            if len(raw) < self._klines_page_limit:
                break  # short page: no more rows exist
        return candles

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker:
        """``ticker/24hr`` for one symbol (weight 2); carries bid/ask on spot."""
        raw = await self._http.get("/api/v3/ticker/24hr", params={"symbol": symbol}, weight=2)
        return normalize.parse_ticker_24h(raw)

    async def fetch_tickers_24h(
        self, symbols: Sequence[str] | None = None
    ) -> list[NormalizedTicker]:
        """All symbols (weight 80) or an explicit list (weight 2/40).

        ``quote_volume_24h`` here is what the tradable universe's 50M USDT
        floor is measured on - on spot, the execution venue itself (D1).
        """
        params: dict[str, Any] = {}
        if symbols is not None:
            # Binance rejects the whitespace ``json.dumps`` would add.
            params["symbols"] = "[" + ",".join(f'"{s}"' for s in symbols) + "]"
        raw = await self._http.get(
            "/api/v3/ticker/24hr",
            params=params or None,
            weight=_ticker_weight(None if symbols is None else len(symbols)),
        )
        # One symbol answers with an object, a list with an array — both
        # shapes are normalized the same way.
        payload = cast("list[dict[str, Any]] | dict[str, Any]", raw)
        rows = payload if isinstance(payload, list) else [payload]
        return [normalize.parse_ticker_24h(entry) for entry in rows]

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        """``depth`` snapshot; 100 is the depth the book walk needs, 20 the
        hot state's. ``ts`` is the receive time - spot sends no clock here."""
        limit = depth if depth in _VALID_DEPTH_LIMITS else 20
        raw = await self._http.get(
            "/api/v3/depth",
            params={"symbol": symbol, "limit": limit},
            weight=_depth_weight(limit),
        )
        return normalize.parse_depth(raw, symbol=symbol, received_at=self._clock())

    async def fetch_trades(self, symbol: str, *, limit: int = 500) -> list[NormalizedTrade]:
        """``/api/v3/trades`` - weight 25, six times an ``aggTrades`` call."""
        raw = await self._http.get(
            "/api/v3/trades", params={"symbol": symbol, "limit": limit}, weight=25
        )
        return normalize.parse_trades(raw, symbol=symbol)

    async def fetch_agg_trades(self, symbol: str, *, limit: int = 500) -> list[NormalizedTrade]:
        """``/api/v3/aggTrades`` - weight 4; the cheap way to backfill trades."""
        raw = await self._http.get(
            "/api/v3/aggTrades", params={"symbol": symbol, "limit": limit}, weight=4
        )
        return normalize.parse_agg_trades(raw, symbol=symbol)

    async def fetch_avg_price(self, symbol: str) -> normalize.AvgPrice:
        """``/api/v3/avgPrice`` (weight 2) - the reference price the
        ``NOTIONAL`` filter applies to a MARKET order."""
        raw = await self._http.get("/api/v3/avgPrice", params={"symbol": symbol}, weight=2)
        return normalize.parse_avg_price(raw, symbol=symbol)

    async def server_time(self) -> datetime:
        """``/api/v3/time`` (weight 1) - the exchange's own clock, never ours."""
        raw = await self._http.get("/api/v3/time", weight=1)
        return normalize.parse_server_time(raw)
