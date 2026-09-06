"""Binance USDS-M Futures adapter (public data only, Phase MVP).

:class:`BinanceAdapter` composes :class:`hunter_exchanges.binance.rest.BinanceRestClient`
(REST) and :class:`hunter_exchanges.binance.ws.BinanceWsClient` (WebSocket)
behind the single :class:`hunter_exchanges.base.ExchangeAdapter` Protocol —
callers depend on the Protocol, never on this class directly.
"""

from __future__ import annotations

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
from hunter_exchanges.binance.rest import BinanceRestClient
from hunter_exchanges.binance.ws import BinanceWsClient

__all__ = ["BinanceAdapter"]


class BinanceAdapter:
    """``ExchangeAdapter`` for Binance USDS-M Futures, public endpoints only."""

    code = "binance"

    def __init__(
        self,
        *,
        rest: BinanceRestClient | None = None,
        ws: BinanceWsClient | None = None,
    ) -> None:
        self._rest = rest or BinanceRestClient()
        self._ws = ws or BinanceWsClient()

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]:
        return await self._rest.list_markets(market_type)

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[NormalizedCandle]:
        return await self._rest.fetch_candles(symbol, timeframe, start, end)

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker:
        return await self._rest.fetch_ticker(symbol)

    async def fetch_order_book(self, symbol: str, depth: int = 25) -> NormalizedOrderBook:
        return await self._rest.fetch_order_book(symbol, depth)

    async def fetch_funding(self, symbol: str) -> NormalizedFunding:
        return await self._rest.fetch_funding(symbol)

    async def fetch_open_interest(self, symbol: str) -> NormalizedOpenInterest:
        return await self._rest.fetch_open_interest(symbol)

    async def fetch_realized_funding(
        self, symbol: str, start: datetime, end: datetime | None = None, *, limit: int = 1000
    ) -> list[NormalizedFunding]:
        return await self._rest.fetch_realized_funding(symbol, start, end, limit=limit)

    async def fetch_tickers_24h(self) -> list[NormalizedTicker]:
        return await self._rest.fetch_tickers_24h()

    async def server_time(self) -> datetime:
        return await self._rest.server_time()

    def stream(
        self, symbols: Sequence[str], channels: Sequence[StreamChannel]
    ) -> AsyncIterator[NormalizedEvent]:
        return self._ws.stream(symbols, channels)

    async def update_subscriptions(
        self, added: Sequence[str], removed: Sequence[str], channels: Sequence[StreamChannel]
    ) -> None:
        await self._ws.update_subscriptions(added, removed, channels)

    async def restart_connection(self, key: str) -> None:
        await self._ws.restart_connection(key)

    def connection_state(self) -> str:
        return self._ws.connection_state()

    def connection_states(self) -> dict[str, ConnectionState]:
        return self._ws.connection_states()

    def rest_gate_status(self) -> str:
        """``"ok"``/``"suspended"`` REST admissions (T2.9).

        Additive, like ``connection_states()``: not part of the
        :class:`~hunter_exchanges.base.ExchangeAdapter` Protocol, so an adapter
        or fake that predates it is not forced to implement it — readers use
        ``getattr`` and default to ``"ok"``.
        """
        return self._rest.rest_gate_status()

    async def aclose(self) -> None:
        await self._ws.aclose()
        await self._rest.aclose()
