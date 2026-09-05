"""In-memory ``ExchangeAdapter`` for testing consumers (market-worker et al.).

No network, no Redis — every REST-shaped method returns whatever was passed
in at construction time, and :meth:`FakeExchangeAdapter.stream` yields a
scripted sequence of events and then blocks (simulating an open connection
that has caught up) until the consumer cancels it, exactly like a real
adapter would keep a connection open with nothing new to say.
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
from hunter_exchanges.base import ConnectionState, StreamChannel


class FakeExchangeAdapter:
    """A scriptable ``ExchangeAdapter`` double.

    ``connection_states``, if given, is consumed one value per
    :meth:`connection_state` call and holds on the last value once exhausted
    — lets a test script "connecting -> connected -> reconnecting" and then
    stay reconnecting.
    """

    def __init__(
        self,
        *,
        code: str = "fake",
        markets: Sequence[NormalizedMarket] = (),
        candles: Sequence[NormalizedCandle] = (),
        ticker: NormalizedTicker | None = None,
        order_book: NormalizedOrderBook | None = None,
        funding: NormalizedFunding | None = None,
        open_interest: NormalizedOpenInterest | None = None,
        events: Sequence[NormalizedEvent] = (),
        connection_states: Sequence[str] = ("connected",),
        per_connection_states: dict[str, ConnectionState] | None = None,
        server_time: datetime | None = None,
        realized_funding: Sequence[NormalizedFunding] = (),
    ) -> None:
        self.code = code
        self._markets = list(markets)
        self._candles = list(candles)
        self._ticker = ticker
        self._order_book = order_book
        self._funding = funding
        self._open_interest = open_interest
        self._events = list(events)
        self._connection_states = list(connection_states) or ["disconnected"]
        self._state_index = 0
        self._per_connection_states = per_connection_states or {}
        self._server_time = server_time
        self._realized_funding = list(realized_funding)
        self.closed = False
        self.stream_calls: list[tuple[tuple[str, ...], tuple[StreamChannel, ...]]] = []
        self.subscription_changes: list[tuple[list[str], list[str]]] = []
        self.restarted_connections: list[str] = []

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]:
        return [m for m in self._markets if m.market_type == market_type]

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[NormalizedCandle]:
        return [
            c
            for c in self._candles
            if c.symbol == symbol and c.timeframe == timeframe and start <= c.open_time <= end
        ]

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker:
        if self._ticker is None:
            raise LookupError(f"FakeExchangeAdapter has no ticker configured for {symbol!r}")
        return self._ticker

    async def fetch_order_book(self, symbol: str, depth: int = 25) -> NormalizedOrderBook:
        if self._order_book is None:
            raise LookupError(f"FakeExchangeAdapter has no order book configured for {symbol!r}")
        return self._order_book

    async def fetch_funding(self, symbol: str) -> NormalizedFunding:
        if self._funding is None:
            raise LookupError(f"FakeExchangeAdapter has no funding configured for {symbol!r}")
        return self._funding

    async def fetch_open_interest(self, symbol: str) -> NormalizedOpenInterest:
        if self._open_interest is None:
            raise LookupError(f"FakeExchangeAdapter has no open interest configured for {symbol!r}")
        return self._open_interest

    async def fetch_realized_funding(
        self, symbol: str, start: datetime, end: datetime | None = None, *, limit: int = 1000
    ) -> list[NormalizedFunding]:
        return [
            f
            for f in self._realized_funding
            if f.symbol == symbol and f.ts >= start and (end is None or f.ts <= end)
        ][:limit]

    async def update_subscriptions(
        self, added: Sequence[str], removed: Sequence[str], channels: Sequence[StreamChannel]
    ) -> None:
        self.subscription_changes.append((list(added), list(removed)))

    def stream(
        self, symbols: Sequence[str], channels: Sequence[StreamChannel]
    ) -> AsyncIterator[NormalizedEvent]:
        self.stream_calls.append((tuple(symbols), tuple(channels)))
        return self._stream_gen()

    async def _stream_gen(self) -> AsyncIterator[NormalizedEvent]:
        for event in self._events:
            yield event
        await (
            asyncio.Event().wait()
        )  # block "forever" (until the consumer cancels), like a live socket

    def connection_state(self) -> str:
        state = self._connection_states[min(self._state_index, len(self._connection_states) - 1)]
        if self._state_index < len(self._connection_states) - 1:
            self._state_index += 1
        return state

    def connection_states(self) -> dict[str, ConnectionState]:
        """Scriptable per-connection detail (see :class:`ConnectionState`)."""
        return dict(self._per_connection_states)

    async def server_time(self) -> datetime:
        """The exchange's own clock — configured at construction, never guessed."""
        if self._server_time is None:
            raise LookupError("FakeExchangeAdapter has no server_time configured")
        return self._server_time

    async def restart_connection(self, key: str) -> None:
        """Records the request (F8); no real tasks to cancel/restart here."""
        self.restarted_connections.append(key)

    async def aclose(self) -> None:
        self.closed = True
