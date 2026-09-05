"""Exchange adapter contract (docs/ARCHITECTURE.md §6, docs/EXCHANGE_INTEGRATION.md §2).

An adapter speaks one exchange's dialect and returns only ``Normalized*``
models from :mod:`hunter_core.domain.market`. No raw payload leaves the
package except inside an explicitly labelled ``metadata`` dict. Workers
depend on this Protocol, never on a concrete adapter, so a fake adapter can
drive them in tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

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


class StreamChannel(StrEnum):
    """Public WebSocket channels every adapter maps to its own stream names."""

    TRADES = "trades"  # Binance aggTrade / Bybit publicTrade
    BOOK_TICKER = "book_ticker"  # best bid/ask
    BOOK = "book"  # partial book snapshot (top N)
    KLINE_1M = "kline_1m"
    MARK_PRICE = "mark_price"  # funding, mark, index
    LIQUIDATIONS = "liquidations"


class ExchangeError(Exception):
    """Base class for every failure raised by an adapter."""

    def __init__(self, message: str, *, exchange: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.exchange = exchange
        self.retryable = retryable


class RateLimited(ExchangeError):
    """The exchange (or our own token bucket) refused the call; wait ``retry_after_s``."""

    def __init__(self, message: str, *, exchange: str, retry_after_s: float) -> None:
        super().__init__(message, exchange=exchange, retryable=True)
        self.retry_after_s = retry_after_s


class ExchangeUnavailable(ExchangeError):
    """Network/5xx/maintenance: the data is UNAVAILABLE, never to be invented."""


class MalformedMessage(ExchangeError):
    """A payload the adapter could not normalize; logged and skipped, never guessed."""

    def __init__(self, message: str, *, exchange: str) -> None:
        super().__init__(message, exchange=exchange, retryable=False)


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Public-data contract. Private endpoints (orders, permissions) come in Phase 3."""

    code: str  # "binance" | "bybit"

    async def list_markets(self, market_type: MarketType) -> list[NormalizedMarket]: ...

    async def fetch_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> list[NormalizedCandle]: ...

    async def fetch_ticker(self, symbol: str) -> NormalizedTicker: ...

    async def fetch_order_book(self, symbol: str, depth: int = 25) -> NormalizedOrderBook: ...

    async def fetch_funding(self, symbol: str) -> NormalizedFunding: ...

    async def fetch_open_interest(self, symbol: str) -> NormalizedOpenInterest: ...

    def stream(
        self,
        symbols: Sequence[str],
        channels: Sequence[StreamChannel],
    ) -> AsyncIterator[NormalizedEvent]:
        """Yield normalized events forever; reconnects and resubscribes internally.

        Connection state changes are surfaced through :meth:`connection_state`
        so the worker can publish ``stale``/``reconnecting`` honestly instead
        of showing frozen numbers.
        """
        ...

    def connection_state(self) -> str:
        """``connected`` | ``connecting`` | ``reconnecting`` | ``disconnected``."""
        ...

    async def aclose(self) -> None: ...
