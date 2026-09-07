"""Binance **SPOT** adapter (public data only) - ``docs/plans/M3.md`` T3.0.

:class:`BinanceSpotAdapter` implements the same
:class:`hunter_exchanges.base.ExchangeAdapter` Protocol as the USDS-M one,
composing :class:`~hunter_exchanges.binance_spot.rest.BinanceSpotRestClient`
and :class:`~hunter_exchanges.binance_spot.ws.BinanceSpotWsClient`.

Identity (why ``code == "binance"`` and what is still missing before this
can be wired into the market-worker) is spelled out in
:mod:`hunter_exchanges.binance_spot.identity`. In short: one venue, one
``exchanges`` row, one IP budget - and ``market_type`` is the discriminator,
declared on the adapter and carried by every ``NormalizedMarket``.

Spot has no funding, no open interest, no mark price and no liquidations.
The two Protocol methods that ask for them raise instead of returning a
zero: an invented derivative number is worse than an honest refusal.
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
    NormalizedTrade,
)
from hunter_exchanges.base import ConnectionState, ExchangeError, StreamChannel
from hunter_exchanges.binance_spot.fees import DEFAULT_SCHEDULE, SpotFeeSchedule
from hunter_exchanges.binance_spot.filters import SpotMarketFilters
from hunter_exchanges.binance_spot.identity import EXCHANGE, MARKET_TYPE, market_identity
from hunter_exchanges.binance_spot.normalize import AvgPrice
from hunter_exchanges.binance_spot.rest import BinanceSpotRestClient
from hunter_exchanges.binance_spot.ws import BinanceSpotWsClient

__all__ = ["BinanceSpotAdapter"]


class BinanceSpotAdapter:
    """``ExchangeAdapter`` for Binance spot, public endpoints only."""

    code = EXCHANGE
    #: The discriminator that keeps spot ``BTCUSDT`` from ever being confused
    #: with the perpetual one (``identity.py``). Declared, never inferred.
    market_type = MARKET_TYPE
    #: Published spot fees, with source and policy - never the futures ones.
    fees: SpotFeeSchedule = DEFAULT_SCHEDULE

    def __init__(
        self,
        *,
        rest: BinanceSpotRestClient | None = None,
        ws: BinanceSpotWsClient | None = None,
    ) -> None:
        self._rest = rest or BinanceSpotRestClient()
        self._ws = ws or BinanceSpotWsClient()

    def identity(self, symbol: str) -> str:
        """``"binance:spot:BTCUSDT"`` - the full, collision-free market key."""
        return market_identity(self.code, symbol, self.market_type)

    # ---- REST ----------------------------------------------------------

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]:
        return await self._rest.list_markets(market_type)

    async def fetch_filters(
        self, symbols: Sequence[str] | None = None
    ) -> dict[str, SpotMarketFilters]:
        return await self._rest.fetch_filters(symbols)

    async def fetch_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> list[NormalizedCandle]:
        return await self._rest.fetch_candles(symbol, timeframe, start, end)

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker:
        return await self._rest.fetch_ticker(symbol)

    async def fetch_tickers_24h(
        self, symbols: Sequence[str] | None = None
    ) -> list[NormalizedTicker]:
        return await self._rest.fetch_tickers_24h(symbols)

    async def fetch_order_book(self, symbol: str, depth: int = 20) -> NormalizedOrderBook:
        return await self._rest.fetch_order_book(symbol, depth)

    async def fetch_trades(self, symbol: str, *, limit: int = 500) -> list[NormalizedTrade]:
        return await self._rest.fetch_trades(symbol, limit=limit)

    async def fetch_agg_trades(self, symbol: str, *, limit: int = 500) -> list[NormalizedTrade]:
        return await self._rest.fetch_agg_trades(symbol, limit=limit)

    async def fetch_avg_price(self, symbol: str) -> AvgPrice:
        return await self._rest.fetch_avg_price(symbol)

    async def server_time(self) -> datetime:
        return await self._rest.server_time()

    async def fetch_funding(self, symbol: str) -> NormalizedFunding:
        """Spot has no funding - refused, never a fabricated zero rate."""
        raise ExchangeError(
            f"binance spot has no funding rate ({symbol}); funding is a USDS-M concept",
            exchange=self.code,
            retryable=False,
        )

    async def fetch_open_interest(self, symbol: str) -> NormalizedOpenInterest:
        """Spot has no open interest - refused, never a fabricated zero."""
        raise ExchangeError(
            f"binance spot has no open interest ({symbol}); OI is a USDS-M concept",
            exchange=self.code,
            retryable=False,
        )

    def rest_gate_status(self) -> str:
        return self._rest.rest_gate_status()

    # ---- WebSocket -----------------------------------------------------

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

    def connection_generation(self) -> int:
        return self._ws.connection_generation()

    def queue_progress(self) -> tuple[int, int, int]:
        return self._ws.queue_progress()

    def queue_oldest_pending_ts(self) -> datetime | None:
        return self._ws.queue_oldest_pending_ts()

    def out_of_sequence_count(self) -> int:
        """Book frames dropped by the ``lastUpdateId`` guard (spot-specific)."""
        return self._ws.out_of_sequence_count

    async def aclose(self) -> None:
        await self._ws.aclose()
        await self._rest.aclose()
