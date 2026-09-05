"""A minimal ``ExchangeAdapter`` test double.

docs/plans/M1.md T1.3 brief: develop against the Protocol only; the concrete
Binance adapter (``hunter_exchanges.binance``, T1.2) is written concurrently
and must not be touched or imported here. Every REST method returns
whatever the test pre-loads; ``stream()`` yields events pushed with
:meth:`FakeAdapter.push_event` (or raises one pushed as an exception) until
cancelled.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from hunter_core.domain.enums import MarketType, Timeframe
from hunter_core.domain.market import (
    NormalizedCandle,
    NormalizedEvent,
    NormalizedFunding,
    NormalizedMarket,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
)
from hunter_exchanges.base import ExchangeUnavailable, StreamChannel


class FakeAdapter:
    """In-memory ``ExchangeAdapter`` double for market-worker tests."""

    def __init__(self, code: str = "fake") -> None:
        self.code = code
        self.markets: list[NormalizedMarket] = []
        self.tickers: dict[str, NormalizedTicker] = {}
        self.order_books: dict[str, NormalizedOrderBook] = {}
        self.fundings: dict[str, NormalizedFunding] = {}
        self.open_interests: dict[str, NormalizedOpenInterest] = {}
        self.candles_response: dict[str, list[NormalizedCandle]] = {}
        self._ws_state = "connected"
        self._queue: asyncio.Queue[NormalizedEvent | BaseException] = asyncio.Queue()
        self.closed = False
        self.stream_started = asyncio.Event()
        self.subscriptions_updated = asyncio.Event()
        self.subscription_changes: list[tuple[list[str], list[str]]] = []
        self.stream_calls: list[tuple[list[str], list[StreamChannel]]] = []
        self.fetch_candles_calls: list[tuple[str, Timeframe, datetime, datetime]] = []
        self.fetch_open_interest_calls: list[str] = []

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]:
        return [m for m in self.markets if m.market_type == market_type]

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[NormalizedCandle]:
        self.fetch_candles_calls.append((symbol, timeframe, start, end))
        return self.candles_response.get(symbol, [])

    async def fetch_tickers_24h(self) -> list[NormalizedTicker]:
        return list(self.tickers.values())

    async def update_subscriptions(
        self, added: list[str], removed: list[str], channels: Sequence[StreamChannel]
    ) -> None:
        self.subscription_changes.append((added, removed))
        self.subscriptions_updated.set()

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker:
        ticker = self.tickers.get(symbol)
        if ticker is None:
            raise ExchangeUnavailable(f"no fake ticker for {symbol}", exchange=self.code)
        return ticker

    async def fetch_order_book(self, symbol: str, depth: int = 25) -> NormalizedOrderBook:
        book = self.order_books.get(symbol)
        if book is None:
            raise ExchangeUnavailable(f"no fake book for {symbol}", exchange=self.code)
        return book

    async def fetch_funding(self, symbol: str) -> NormalizedFunding:
        funding = self.fundings.get(symbol)
        if funding is None:
            raise ExchangeUnavailable(f"no fake funding for {symbol}", exchange=self.code)
        return funding

    async def fetch_open_interest(self, symbol: str) -> NormalizedOpenInterest:
        self.fetch_open_interest_calls.append(symbol)
        oi = self.open_interests.get(symbol)
        if oi is None:
            raise ExchangeUnavailable(f"no fake OI for {symbol}", exchange=self.code)
        return oi

    async def push_event(self, event: NormalizedEvent | BaseException) -> None:
        await self._queue.put(event)

    async def stream(
        self, symbols: Sequence[str], channels: Sequence[StreamChannel]
    ) -> AsyncIterator[NormalizedEvent]:
        self.stream_calls.append((list(symbols), list(channels)))
        self.stream_started.set()
        try:
            while True:
                item = await self._queue.get()
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            # Mirrors the real Binance adapter (ws.py's StreamConsumer.consume):
            # the generator's own ``finally`` runs ``on_close`` (here, the
            # adapter's own ``aclose``) whenever the generator is closed —
            # cancellation, ``stream.aclose()``, or an exception.
            await self.aclose()

    def connection_state(self) -> str:
        return self._ws_state

    def set_connection_state(self, state: str) -> None:
        self._ws_state = state

    async def aclose(self) -> None:
        self.closed = True


class FakeRuntime:
    """Stands in for ``WorkerRuntime`` in tests that only need ``.instance``,
    ``.redis`` and the two ``mark_*`` counters — never a real Postgres/Redis
    connected process."""

    def __init__(self, redis: object = None, instance: str = "test:1") -> None:
        self.redis = redis
        self.instance = instance
        self.success = asyncio.Event()
        self.success_count = 0
        self.error_count = 0

    def mark_success(self) -> None:
        self.success_count += 1
        self.success.set()

    def mark_error(self) -> None:
        self.error_count += 1
