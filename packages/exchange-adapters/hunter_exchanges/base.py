"""Exchange adapter contract (docs/ARCHITECTURE.md §6, docs/EXCHANGE_INTEGRATION.md §2).

An adapter speaks one exchange's dialect and returns only ``Normalized*``
models from :mod:`hunter_core.domain.market`. No raw payload leaves the
package except inside an explicitly labelled ``metadata`` dict. Workers
depend on this Protocol, never on a concrete adapter, so a fake adapter can
drive them in tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
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


@dataclass
class ConnectionState:
    """Point-in-time status of one WebSocket connection an adapter owns.

    Additive (``docs/plans/M1.md`` T1.2): not a required member of
    :class:`ExchangeAdapter` yet — ``connection_state()`` (the aggregate
    worst-of-all-connections string) stays the only Protocol requirement so
    an adapter/fake that predates this field isn't forced to implement
    per-connection reporting mid-milestone. An adapter that has one may
    expose it via a plain ``connection_states() -> dict[str, ConnectionState]``
    method. ``ws_state`` mirrors :meth:`ExchangeAdapter.connection_state`'s
    values. ``last_data_event_*`` only ever advances on an actual data frame
    (ACK/ping never count).
    """

    route: str
    ws_state: str
    subscriptions: tuple[str, ...] = ()
    last_data_event_monotonic: float | None = None
    last_data_event_ts: datetime | None = None
    reconnects: int = 0
    connect_attempt_started_monotonic: float | None = None
    dropped_events: int = 0
    """Events discarded by the adapter's bounded internal queue (T1.2b) to
    keep a slow consumer from growing memory without limit — never counts a
    dropped final kline, which the queue is never allowed to discard."""


class ExchangeError(Exception):
    """Base class for every failure raised by an adapter."""

    def __init__(self, message: str, *, exchange: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.exchange = exchange
        self.retryable = retryable


class RateLimited(ExchangeError):
    """The exchange (or our own token bucket) refused the call; wait ``retry_after_s``.

    ``reason`` names *why* our own side refused when the refusal was not about
    spent budget — today only ``"redis_unavailable"``, i.e. REST admissions are
    suspended because the shared rate-limit coordination cannot be reached
    (T2.9, fail-closed). Callers that want to wait for coordination to come
    back instead of burning a retry attempt branch on it; ``None`` means the
    ordinary "no budget right now".
    """

    def __init__(
        self, message: str, *, exchange: str, retry_after_s: float, reason: str | None = None
    ) -> None:
        super().__init__(message, exchange=exchange, retryable=True)
        self.retry_after_s = retry_after_s
        self.reason = reason


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


@runtime_checkable
class ExchangeAdapterExtras(Protocol):
    """T1.2b capabilities, kept out of :class:`ExchangeAdapter` on purpose.

    Merging these four into ``ExchangeAdapter`` directly would make every
    ``adapter: ExchangeAdapter``-typed call site require them structurally
    (pyright, not just ``isinstance``) — breaking on the market-worker's own
    ``tests/fakes.py::FakeAdapter``, which this package must not modify. Every
    caller that wants one of these already checks for it defensively
    (``getattr(adapter, "update_subscriptions", None)`` in
    ``hunter_market_worker.streaming``/``funding``), so this Protocol exists
    only for adapters (:class:`~hunter_exchanges.binance.BinanceAdapter`,
    :class:`~hunter_exchanges.testing.fake_adapter.FakeExchangeAdapter`) that
    implement the full, honest shape to type-check against.
    """

    async def fetch_realized_funding(
        self, symbol: str, start: datetime, end: datetime | None = None, *, limit: int = 1000
    ) -> list[NormalizedFunding]:
        """Settled funding history (``funding_kind="realized"``), for backfill."""
        ...

    async def server_time(self) -> datetime:
        """The exchange's own clock — never the local one, for recovery cutoffs."""
        ...

    def connection_states(self) -> dict[str, ConnectionState]:
        """Per-connection detail; see :class:`ConnectionState`."""
        ...

    async def update_subscriptions(
        self, added: Sequence[str], removed: Sequence[str], channels: Sequence[StreamChannel]
    ) -> None:
        """Apply an incremental universe diff to an open :meth:`stream` call.

        Symbols that stay subscribed must never be resubscribed — only the
        diff (``added``/``removed``) travels to the exchange.
        """
        ...

    async def restart_connection(self, key: str) -> None:
        """Cancel and restart exactly one connection's task in place (F8).

        Every other connection is left completely untouched — unlike a
        blanket ``aclose()`` + reopen-everything fallback, which turns one
        stalled connection into an avoidable book/ticker hole across the
        whole monitored universe.
        """
        ...
