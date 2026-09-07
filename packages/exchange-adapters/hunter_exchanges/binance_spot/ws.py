"""Binance **SPOT** WebSocket client: one route, sequence guard, reconnect.

Reuses the USDS-M connection machinery rather than copying it - the
connect/rotate/idle/backoff loop
(:class:`~hunter_exchanges.binance.connection.ConnectionRunner`), the
subscription diff bookkeeping
(:class:`~hunter_exchanges.binance.subscriptions.SubscriptionController`)
and the bounded queue
(:class:`~hunter_exchanges.binance.event_queue.StreamConsumer`) all take the
spot stream naming and route splitting by injection (T3.0a). What is
genuinely different lives here:

- **one route** (``spot``), one endpoint, 1024 streams per connection
  (200 symbols x 4 channels = 800 in practice);
- **5 incoming messages/s per connection**, a real disconnect risk: every
  socket is throttled and opened with the library's own keepalive PING off
  (:mod:`hunter_exchanges.binance_spot.throttle`);
- **book sequence guard** on ``lastUpdateId`` (:meth:`_accept_book`), since
  the partial-depth stream is a timestamp-less snapshot;
- **receive-time stamping** for the channels Binance sends no clock on -
  see :mod:`hunter_exchanges.binance_spot.streams`.

Reconnects are the adapter's business; the *gap* they leave is the worker's:
:meth:`connection_generation` advances on every (re)connection beyond a
key's first, which is the signal ``CoverageTracker`` uses to break a claimed
coverage interval and open an ``ingestion_gaps`` row. Nothing here ever
fabricates the minutes lost while the socket was down.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import orjson

from hunter_core.domain.market import NormalizedEvent
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_exchanges.base import ConnectionState, MalformedMessage, StreamChannel
from hunter_exchanges.binance.connection import (
    CONNECT_TIMEOUT_S,
    IDLE_TIMEOUT_S,
    MAX_CONNECTION_AGE_S,
    MAX_RECONNECT_FAILURES,
    ConnectFn,
    ConnectionRunner,
)
from hunter_exchanges.binance.event_queue import DEFAULT_MAXSIZE, StreamConsumer
from hunter_exchanges.binance.subscription_plan import is_control_ack
from hunter_exchanges.binance.subscriptions import SubscriptionController, SymbolGroup
from hunter_exchanges.binance_spot.streams import (
    MAX_CONTROL_MESSAGES_PER_S,
    ROUTE_SPOT,
    WS_BASE_URL,
    group_symbols,
    parse_stream_message,
    split_channels_by_route,
    stream_name,
)
from hunter_exchanges.binance_spot.throttle import spot_connect, throttled_connect

logger = get_logger(__name__)

__all__ = ["CONTROL_SEND_BUDGET_PER_S", "BinanceSpotWsClient"]

#: One of Binance's five messages/s is left for the websockets library's own
#: PONG replies, which we do not schedule.
CONTROL_SEND_BUDGET_PER_S = MAX_CONTROL_MESSAGES_PER_S - 1

_STATE_SEVERITY: dict[str, int] = {
    "connected": 0,
    "connecting": 1,
    "reconnecting": 2,
    "disconnected": 3,
}


class BinanceSpotWsClient:
    """Manages one connection per group of at most 200 spot symbols."""

    def __init__(
        self,
        *,
        base_url: str = WS_BASE_URL,
        connect_fn: ConnectFn | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        received_at_fn: Callable[[], datetime] = utcnow,
        max_connection_age_s: float = MAX_CONNECTION_AGE_S,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
        queue_maxsize: int = DEFAULT_MAXSIZE,
        max_reconnect_failures: int = MAX_RECONNECT_FAILURES,
        control_budget_per_s: int = CONTROL_SEND_BUDGET_PER_S,
    ) -> None:
        self._sleep = sleep
        self._received_at = received_at_fn
        self._queue_maxsize = queue_maxsize
        self._states: dict[str, ConnectionState] = {}
        self._subs = SubscriptionController(
            start=self._start_group,
            restart=self.restart_connection,
            sleep=sleep,
            stream_name_fn=stream_name,
            split_channels_fn=split_channels_by_route,
        )
        self._malformed_count = 0
        self._out_of_sequence_count = 0
        self._duplicate_book_count = 0
        self._key_tasks: dict[str, asyncio.Task[None]] = {}
        self._last_trade: dict[str, tuple[Decimal, datetime, int]] = {}
        self._last_book_sequence: dict[str, int] = {}
        self._consumer: StreamConsumer | None = None
        self._generation = 0
        self._started_keys: set[str] = set()
        monotonic_clock = clock or (lambda: asyncio.get_running_loop().time())
        self._runner = ConnectionRunner(
            base_urls={ROUTE_SPOT: base_url},
            subs=self._subs,
            states=self._states,
            handle_raw_message=self._handle_raw_message,
            connect_fn=throttled_connect(
                connect_fn or spot_connect,
                max_per_s=control_budget_per_s,
                clock=monotonic_clock,
                sleep=sleep,
            ),
            clock=monotonic_clock,
            sleep=sleep,
            rand=rand,
            max_connection_age_s=max_connection_age_s,
            idle_timeout_s=idle_timeout_s,
            connect_timeout_s=connect_timeout_s,
            max_reconnect_failures=max_reconnect_failures,
            on_reconnect=self._bump_generation,
            stream_name_fn=stream_name,
        )

    # ---- observability -------------------------------------------------

    @property
    def malformed_count(self) -> int:
        return self._malformed_count

    @property
    def out_of_sequence_count(self) -> int:
        """Partial-depth frames dropped because ``lastUpdateId`` went
        **backwards**: a stale snapshot that would have overwritten a newer
        book. Never counts a mere repeat - see :attr:`duplicate_book_count`
        (Astra diff review: an unchanged book republishing the same id is not
        a regression and must not read like one)."""
        return self._out_of_sequence_count

    @property
    def duplicate_book_count(self) -> int:
        """Partial-depth frames dropped because ``lastUpdateId`` repeated -
        the book did not change, so there is nothing new to deliver."""
        return self._duplicate_book_count

    def _bump_generation(self) -> None:
        self._generation += 1

    def connection_generation(self) -> int:
        """(Re)connections beyond each key's first - the coverage break signal."""
        return self._generation

    def queue_progress(self) -> tuple[int, int, int]:
        """``(enqueued, delivered, evicted)`` for the current stream call."""
        if self._consumer is None:
            return 0, 0, 0
        enqueued, evicted = self._consumer.queue.progress()
        return enqueued, self._consumer.delivered, evicted

    def queue_oldest_pending_ts(self) -> datetime | None:
        if self._consumer is None:
            return None
        return self._consumer.oldest_pending_ts()

    def connection_state(self) -> str:
        if not self._states:
            return "disconnected"
        return max((s.ws_state for s in self._states.values()), key=lambda s: _STATE_SEVERITY[s])

    def connection_states(self) -> dict[str, ConnectionState]:
        return {key: replace(state) for key, state in self._states.items()}

    # ---- lifecycle -----------------------------------------------------

    def stream(
        self, symbols: Sequence[str], channels: Sequence[StreamChannel]
    ) -> AsyncIterator[NormalizedEvent]:
        self._consumer = StreamConsumer(self._queue_maxsize)
        self._last_trade = {}
        self._last_book_sequence = {}
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
        await self._subs.update(added, removed, channels, self._states)
        for symbol in removed:
            self._last_trade.pop(symbol, None)
            self._last_book_sequence.pop(symbol, None)

    async def restart_connection(self, key: str) -> None:
        old_task = self._key_tasks.pop(key, None)
        if old_task is not None:
            old_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old_task
        group = self._subs.groups.get(key)
        if group is None:
            logger.warning("binance_spot_ws_restart_unknown_key", key=key)
            return
        self._start_group(group)

    def _start_group(self, group: SymbolGroup) -> None:
        if group.key in self._started_keys:
            self._bump_generation()
        self._started_keys.add(group.key)
        self._states[group.key] = ConnectionState(route=group.route, ws_state="connecting")
        task = asyncio.ensure_future(self._runner.run(group.key, group.route))
        assert self._consumer is not None
        task.add_done_callback(self._consumer.on_task_done)
        self._key_tasks[group.key] = task

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
                logger.warning("binance_spot_ws_task_error_during_close", error=str(exc))
        self._key_tasks.clear()
        self._states.clear()
        self._started_keys.clear()
        self._subs.reset()

    # ---- frame handling ------------------------------------------------

    async def _handle_raw_message(self, raw: str | bytes, key: str) -> bool:
        """``True`` only for a recognized, well-formed data frame - never for
        a control ACK or a malformed payload."""
        state = self._states[key]
        try:
            raw_obj: Any = orjson.loads(raw)
            if isinstance(raw_obj, dict):
                obj = cast("dict[str, Any]", raw_obj)
                if is_control_ack(obj):
                    await self._subs.resolve_ack(obj, self._states)
                    return False
            envelope = cast("dict[str, Any]", raw_obj)
            stream: Any = envelope["stream"]
            data: dict[str, Any] = envelope["data"]
        except (orjson.JSONDecodeError, KeyError, TypeError) as exc:
            self._malformed_count += 1
            logger.warning("binance_spot_ws_malformed_envelope", error=str(exc))
            return False
        received_at = self._received_at()
        symbol = str(stream).partition("@")[0].upper()
        cached = self._last_trade.get(symbol)
        try:
            event = parse_stream_message(
                stream,
                data,
                last_price=cached[0] if cached else None,
                received_at=received_at,
            )
        except MalformedMessage as exc:
            self._malformed_count += 1
            logger.warning("binance_spot_ws_malformed_message", stream=stream, error=str(exc))
            return False
        # A recognized, well-formed frame is proof of life even when it emits
        # no event (a bookTicker before any trade, a stale book).
        state.last_data_event_monotonic = self._runner.clock()
        state.last_data_event_ts = self._frame_ts(event, received_at)
        if event is None:
            return True
        kind = getattr(event, "kind", None)
        if kind == "book" and not self._accept_book(event, symbol):
            return True
        if kind == "trade":
            self._remember_trade(event, symbol)
        assert self._consumer is not None
        await self._consumer.put(key, event, self._states)
        return True

    def _accept_book(self, event: Any, symbol: str) -> bool:
        """Sequence guard: ``lastUpdateId`` must strictly advance.

        A *smaller* id is a stale frame (out of sequence, warned); an *equal*
        one is the same book republished (duplicate, debug). Both are dropped
        - neither adds anything to the last delivered book - but counted
        apart, so a real regression is never buried under harmless repeats.
        """
        sequence = int(event.sequence)
        previous = self._last_book_sequence.get(symbol)
        if previous is not None and sequence == previous:
            self._duplicate_book_count += 1
            logger.debug("binance_spot_ws_book_duplicate", symbol=symbol, sequence=sequence)
            return False
        if previous is not None and sequence < previous:
            self._out_of_sequence_count += 1
            logger.warning(
                "binance_spot_ws_book_out_of_sequence",
                symbol=symbol,
                sequence=sequence,
                previous=previous,
            )
            return False
        self._last_book_sequence[symbol] = sequence
        return True

    def _remember_trade(self, event: Any, symbol: str) -> None:
        """Newest trade price for the next bookTicker; ties break on the id."""
        cached = self._last_trade.get(symbol)
        trade_id = int(event.trade_id)
        if cached is None or (event.ts, trade_id) >= (cached[1], cached[2]):
            self._last_trade[symbol] = (event.price, event.ts, trade_id)

    def _frame_ts(self, event: NormalizedEvent | None, received_at: datetime) -> datetime:
        ts = getattr(event, "ts", None) or getattr(event, "close_time", None)
        return cast("datetime", ts) if ts is not None else received_at
