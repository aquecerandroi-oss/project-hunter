"""Binance USDS-M Futures WebSocket client — two routes, reconnect, backoff.

``docs/plans/M1.md`` T1.2 / T1.2b / "Decisão conjunta Claude ⇄ Astra":

- Two combined-stream routes (:func:`hunter_exchanges.binance.streams.route_for_channel`),
  <= 200 symbols per connection per route, each its own task merged into one
  ``AsyncIterator`` (:class:`~hunter_exchanges.binance.event_queue.StreamConsumer`).
  The connect/rotate/backoff loop itself lives in
  :mod:`~hunter_exchanges.binance.connection` (:class:`~hunter_exchanges.binance.connection.ConnectionRunner`).
- Proactive, jittered reconnect before Binance's 24h limit (no backoff);
  reconnect-after-error backoff 1s -> 60s with jitter, capped at
  ``MAX_RECONNECT_FAILURES`` failures *demonstrated* by real data or a clean
  lifetime — past that :class:`~hunter_exchanges.base.ExchangeUnavailable`
  reaches :meth:`stream`'s consumer instead of retrying forever (T1.2b).
- A malformed message is logged and counted, never raised out of :meth:`stream`.
- Incremental subscription changes (T1.2b, :meth:`update_subscriptions`,
  :mod:`hunter_exchanges.binance.subscriptions`): symbols that stay
  subscribed are never resubscribed — only the diff travels as a live
  ``SUBSCRIBE``/``UNSUBSCRIBE`` frame over the existing connection for that
  route; overflow opens a new connection the same way :meth:`stream` does.
- :meth:`restart_connection` (F8) restarts exactly one connection's task,
  leaving every other connection untouched.
- :meth:`connection_states` reports one :class:`ConnectionState` per
  connection, updated by **data events only** (ACK/ping frames never count).

``connect_fn``/``clock``/``sleep``/``rand`` are injectable so tests never
touch a real socket or wait real seconds.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from hunter_core.domain.market import NormalizedEvent
from hunter_core.logging import get_logger
from hunter_exchanges.base import (
    ConnectionState,
    MalformedMessage,
    StreamChannel,
)
from hunter_exchanges.binance.connection import (
    CONNECT_TIMEOUT_S,
    IDLE_TIMEOUT_S,
    MAX_CONNECTION_AGE_S,
    MAX_RECONNECT_FAILURES,
    ConnectFn,
    ConnectionRunner,
)
from hunter_exchanges.binance.event_queue import DEFAULT_MAXSIZE, StreamConsumer
from hunter_exchanges.binance.streams import (
    BOOK_DEPTH as BOOK_DEPTH,  # re-exported for callers (API/UI book.depth projection)
)
from hunter_exchanges.binance.streams import (
    ROUTE_MARKET,
    ROUTE_PUBLIC,
    event_ts,
    group_symbols,
    parse_stream_message,
    split_channels_by_route,
)
from hunter_exchanges.binance.subscriptions import (
    SubscriptionController,
    SymbolGroup,
    is_control_ack,
)

logger = get_logger(__name__)

PUBLIC_WS_BASE_URL = "wss://fstream.binance.com/public/stream?streams="
MARKET_WS_BASE_URL = "wss://fstream.binance.com/market/stream?streams="

WsState = str  # "connected" | "connecting" | "reconnecting" | "disconnected"
_STATE_SEVERITY: dict[WsState, int] = {
    "connected": 0,
    "connecting": 1,
    "reconnecting": 2,
    "disconnected": 3,
}


class BinanceWsClient:
    """Manages one combined-stream connection per (route, <= 200 symbols) group."""

    def __init__(
        self,
        *,
        public_base_url: str = PUBLIC_WS_BASE_URL,
        market_base_url: str = MARKET_WS_BASE_URL,
        connect_fn: ConnectFn | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        max_connection_age_s: float = MAX_CONNECTION_AGE_S,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
        queue_maxsize: int = DEFAULT_MAXSIZE,
        max_reconnect_failures: int = MAX_RECONNECT_FAILURES,
    ) -> None:
        self._sleep = sleep
        self._queue_maxsize = queue_maxsize
        self._states: dict[str, ConnectionState] = {}
        # F6/F8: SubscriptionController restarts exactly one connection
        # (never a blanket teardown) on a rejected/timed-out SUBSCRIBE ack
        # or a send() failure in update().
        self._subs = SubscriptionController(
            start=self._start_group, restart=self.restart_connection, sleep=sleep
        )
        self._malformed_count = 0
        self._key_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_trade: dict[str, tuple[Decimal, datetime, int]] = {}
        self._consumer: StreamConsumer | None = None
        self._runner = ConnectionRunner(
            base_urls={ROUTE_PUBLIC: public_base_url, ROUTE_MARKET: market_base_url},
            subs=self._subs,
            states=self._states,
            handle_raw_message=self._handle_raw_message,
            connect_fn=connect_fn,
            clock=clock,
            sleep=sleep,
            rand=rand,
            max_connection_age_s=max_connection_age_s,
            idle_timeout_s=idle_timeout_s,
            connect_timeout_s=connect_timeout_s,
            max_reconnect_failures=max_reconnect_failures,
        )

    def connection_state(self) -> WsState:
        """The worst ``ws_state`` across every connection (``base.py`` contract)."""
        if not self._states:
            return "disconnected"
        return max((s.ws_state for s in self._states.values()), key=lambda s: _STATE_SEVERITY[s])

    def connection_states(self) -> dict[str, ConnectionState]:
        """A snapshot (not live references) keyed by ``"{route}:{index}"``."""
        return {key: replace(state) for key, state in self._states.items()}

    @property
    def malformed_count(self) -> int:
        return self._malformed_count

    def stream(
        self, symbols: Sequence[str], channels: Sequence[StreamChannel]
    ) -> AsyncIterator[NormalizedEvent]:
        self._consumer = StreamConsumer(self._queue_maxsize)
        self._last_trade = {}
        for route, route_channels in split_channels_by_route(channels).items():
            for index, group in enumerate(group_symbols(list(symbols))):
                self._subs.add_group(
                    SymbolGroup(
                        key=f"{route}:{index}",
                        route=route,
                        channels=tuple(route_channels),
                        symbols=list(group),
                    )
                )
        return self._consumer.consume(self.aclose)

    async def update_subscriptions(
        self, added: Sequence[str], removed: Sequence[str], channels: Sequence[StreamChannel]
    ) -> None:
        """Apply an incremental universe diff without touching unaffected symbols."""
        await self._subs.update(added, removed, channels, self._states)
        # F11: a removed symbol's cached last-trade price must not outlive
        # its subscription — otherwise weeks of universe churn (the 15-
        # minute top-N refresh) grow this dict forever.
        for symbol in removed:
            self._last_trade.pop(symbol, None)

    async def restart_connection(self, key: str) -> None:
        """Cancel and restart exactly one connection's task (F6/F8).

        Every other connection's task and :class:`ConnectionState` is left
        completely untouched — unlike the worker's ``restart_stream=True``
        fallback (``aclose()`` then reopen everything), which turns one
        stalled connection into an avoidable book/ticker hole across the
        whole monitored universe.
        """
        old_task = self._key_tasks.pop(key, None)
        if old_task is not None:
            old_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old_task
        group = self._subs.groups.get(key)
        if group is None:
            logger.warning("binance_ws_restart_unknown_key", key=key)
            return
        self._start_group(group)

    def _start_group(self, group: SymbolGroup) -> None:
        self._states[group.key] = ConnectionState(route=group.route, ws_state="connecting")
        task = asyncio.ensure_future(self._runner.run(group.key, group.route))
        assert self._consumer is not None
        task.add_done_callback(self._consumer.on_task_done)
        self._key_tasks[group.key] = task

    async def _handle_raw_message(self, raw: str | bytes, key: str) -> bool:
        """Returns ``True`` only for a recognized, well-formed data frame —
        never for a control ACK or a malformed payload, so callers can tell
        "the socket returned bytes" from "the exchange is really talking to
        us" (Astra review, T1.2b resume round 2)."""
        state = self._states[key]
        try:
            raw_obj: Any = json.loads(raw)
            if isinstance(raw_obj, dict):
                obj = cast("dict[str, Any]", raw_obj)
                if is_control_ack(obj):
                    await self._subs.resolve_ack(obj, self._states)
                    return False
            envelope = cast("dict[str, Any]", raw_obj)
            stream: Any = envelope["stream"]
            data: dict[str, Any] = envelope["data"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            self._malformed_count += 1
            logger.warning("binance_ws_malformed_envelope", error=str(exc))
            return False
        symbol = str(data.get("s", "")).upper()
        cached = self._last_trade.get(symbol)
        try:
            event = parse_stream_message(stream, data, last_price=cached[0] if cached else None)
        except MalformedMessage as exc:
            self._malformed_count += 1
            logger.warning("binance_ws_malformed_message", stream=stream, error=str(exc))
            return False
        # A recognized, well-formed frame is a data event even when it defers
        # emitting a NormalizedEvent (a bookTicker before any trade is seen).
        state.last_data_event_monotonic = self._runner.clock()
        state.last_data_event_ts = self._frame_ts(data, event)
        if event is None:
            return True
        if getattr(event, "kind", None) == "trade":
            # F10: tie-break on the aggregate trade id when timestamps are
            # equal — two trades in the same millisecond delivered out of
            # order (id 2 @ 200, then id 1 @ 100) must not regress the
            # cached price a later bookTicker republishes.
            trade_id = int(event.trade_id)  # type: ignore[union-attr]
            if cached is None or (event.ts, trade_id) >= (cached[1], cached[2]):  # type: ignore[union-attr]
                self._last_trade[symbol] = (event.price, event.ts, trade_id)  # type: ignore[union-attr]
        assert self._consumer is not None
        await self._consumer.put(key, event, self._states)
        return True

    def _frame_ts(self, data: dict[str, object], event: NormalizedEvent | None) -> datetime | None:
        ts = getattr(event, "ts", None) or getattr(event, "close_time", None)
        if ts is not None:
            return ts  # type: ignore[return-value]
        try:
            return event_ts(data)  # deferred bookTicker: no event yet, frame is still timestamped
        except (KeyError, MalformedMessage):
            return None

    async def aclose(self) -> None:
        tasks = list(self._key_tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("binance_ws_task_error_during_close", error=str(exc))
        self._key_tasks.clear()
        self._states.clear()
        self._subs.reset()
