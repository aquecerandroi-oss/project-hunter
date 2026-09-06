"""Binance WS connection lifecycle: connect, rotate, idle-timeout, backoff.

Extracted from ``ws.py`` (T1.2/T1.2b fix pass F6/F7/F8) to keep that module
under the 350-line budget while giving the connect/reconnect loop for one
``(route, symbol-group)`` connection a single, well-tested home.
``BinanceWsClient`` owns everything about *what* to do with a frame
(``handle_raw_message``); this module owns *when* a connection opens,
rotates, or backs off and retries.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from hunter_core.logging import get_logger
from hunter_exchanges.base import ConnectionState, ExchangeUnavailable
from hunter_exchanges.binance.streams import combined_stream_url, stream_name
from hunter_exchanges.binance.subscriptions import SubscriptionController

logger = get_logger(__name__)

CONNECT_TIMEOUT_S = 15.0
MAX_CONNECTION_AGE_S = 23.5 * 3600  # proactively reconnect before Binance's 24h limit
#: F7: a connection whose symbols go quiet (or a half-open socket with no
#: FIN) must be detected and reconnected instead of hanging until Binance's
#: own 24h cut, or forever in the half-open case.
IDLE_TIMEOUT_S = 60.0
BACKOFF_BASE_S = 1.0
BACKOFF_MAX_S = 60.0
MAX_RECONNECT_FAILURES = 5


class WsConnection(Protocol):
    async def recv(self) -> str | bytes: ...
    async def send(self, message: str) -> None: ...
    async def close(self) -> None: ...


ConnectFn = Callable[[str], AbstractAsyncContextManager[WsConnection]]


def default_connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
    import websockets

    return websockets.connect(url)  # type: ignore[return-value]


def sync_monotonic() -> float:
    return asyncio.get_running_loop().time()


class ConnectionRunner:
    """Owns the connect -> stream -> rotate/backoff loop for one connection key."""

    def __init__(
        self,
        *,
        base_urls: dict[str, str],
        subs: SubscriptionController,
        states: dict[str, ConnectionState],
        handle_raw_message: Callable[[str | bytes, str], Awaitable[bool]],
        connect_fn: ConnectFn | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
        max_connection_age_s: float = MAX_CONNECTION_AGE_S,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        connect_timeout_s: float = CONNECT_TIMEOUT_S,
        max_reconnect_failures: int = MAX_RECONNECT_FAILURES,
        on_reconnect: Callable[[], None] | None = None,
    ) -> None:
        self._base_urls = base_urls
        self._subs = subs
        self._states = states
        self._handle_raw_message = handle_raw_message
        self._connect_fn = connect_fn or default_connect
        self._clock = clock or sync_monotonic
        self._sleep = sleep
        self._rand = rand
        self._max_connection_age_s = max_connection_age_s
        self._idle_timeout_s = idle_timeout_s
        self._connect_timeout_s = connect_timeout_s
        #: T2.5-adapter: observability only (``BinanceWsClient.connection_generation``)
        #: — never consulted by this class itself. Fired at the exact instant
        #: ``state.reconnects`` already advances (every pass through the loop
        #: beyond the first: real failure or proactive 24h rotation alike).
        self._on_reconnect = on_reconnect
        self._max_reconnect_failures = max_reconnect_failures

    def clock(self) -> float:
        """The same monotonic clock the connect/rotate loop uses — exposed so
        ``ws.py`` timestamps a data event with the identical clock instead of
        carrying a second, independently-injectable one."""
        return self._clock()

    async def _open(
        self, url: str
    ) -> tuple[AbstractAsyncContextManager[WsConnection], WsConnection]:
        cm = self._connect_fn(url)
        connection = await asyncio.wait_for(cm.__aenter__(), timeout=self._connect_timeout_s)
        return cm, connection

    async def _close_quietly(
        self,
        cm: AbstractAsyncContextManager[WsConnection] | None,
        connection: WsConnection | None,
    ) -> None:
        if cm is None:
            return
        try:
            await cm.__aexit__(None, None, None)
        except Exception as exc:
            logger.warning("binance_ws_close_error", error=str(exc))

    async def _backoff_or_raise(self, key: str, attempt: int, exc: Exception, verb: str) -> int:
        delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2**attempt)) + self._rand()
        attempt += 1
        if attempt >= self._max_reconnect_failures:
            raise ExchangeUnavailable(
                f"binance ws {key} {verb} {attempt} times in a row: {exc}", exchange="binance"
            ) from exc
        await self._sleep(delay)
        return attempt

    async def run(self, key: str, route: str) -> None:
        state = self._states[key]
        attempt = 0
        first_iteration = True
        cm: AbstractAsyncContextManager[WsConnection] | None = None
        connection: WsConnection | None = None
        try:
            while True:
                group = self._subs.groups[key]
                names = [stream_name(s, c) for s in group.symbols for c in group.channels]
                state.subscriptions = tuple(names)
                url = combined_stream_url(self._base_urls[route], names)
                # "reconnects" counts every pass through this loop beyond the
                # very first — a failed retry and a proactive rotation both
                # count, each exactly once, the moment the attempt starts.
                state.ws_state = "connecting" if first_iteration else "reconnecting"
                if not first_iteration:
                    state.reconnects += 1
                    if self._on_reconnect is not None:
                        self._on_reconnect()
                first_iteration = False
                state.connect_attempt_started_monotonic = self._clock()
                try:
                    cm, connection = await self._open(url)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning("binance_ws_connect_error", key=key, route=route, error=str(exc))
                    attempt = await self._backoff_or_raise(key, attempt, exc, "failed to connect")
                    continue

                state.ws_state = "connected"
                state.connect_attempt_started_monotonic = None
                self._subs.live_ws[key] = connection
                # Jitter only ever pulls the deadline earlier than the base
                # (23.5h), never past Binance's real 24h limit; it also
                # staggers connections opened at the same instant.
                max_age = self._max_connection_age_s * (1 - self._rand() * 0.1)
                connected_at = self._clock()
                try:
                    # `names`/`url` may be stale (a diff arrived mid-
                    # handshake) — reconcile inside this same error boundary
                    # so a failed catch-up send backs off like any other.
                    await self._subs.catch_up(key, names, self._states)
                    while True:
                        remaining = max_age - (self._clock() - connected_at)
                        if remaining <= 0:
                            break  # proactive rotation: clean, no backoff (F7)
                        timeout = min(remaining, self._idle_timeout_s)
                        # Decide *before* awaiting which deadline is binding
                        # — re-reading the clock only after a TimeoutError to
                        # tell them apart is a race at a tight boundary (the
                        # two clock reads can land a hair either side of
                        # ``max_age``). Ties favour a clean rotation.
                        is_rotation_bound = timeout >= remaining
                        try:
                            raw = await asyncio.wait_for(connection.recv(), timeout=timeout)
                        except TimeoutError:
                            # F7: distinguish "hit the rotation deadline"
                            # (clean) from "genuinely idle before it" (a
                            # connection failure — half-open socket, dead
                            # symbols — treated like any other and backed off).
                            if is_rotation_bound:
                                break
                            raise ConnectionError(
                                f"binance ws {key} idle for {self._idle_timeout_s:.1f}s, "
                                "no frames received (possible half-open socket)"
                            ) from None
                        # Reset only on a genuine frame, never a bare recv().
                        if await self._handle_raw_message(raw, key):
                            attempt = 0
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "binance_ws_connection_error", key=key, route=route, error=str(exc)
                    )
                    # T2.5-adapter (Astra review, second round, finding 1):
                    # mark the break *before* the close await, not after —
                    # ``__aexit__`` can take real time, and a reader polling
                    # ``ws_state`` during that close must not still see
                    # "connected".
                    state.ws_state = "reconnecting"
                    self._subs.live_ws.pop(key, None)
                    await self._close_quietly(cm, connection)
                    cm, connection = None, None
                    attempt = await self._backoff_or_raise(key, attempt, exc, "failed")
                    continue
                # Aged out with no error: a clean lifetime is healthy too
                # (even an empty group) — reconnect now, no backoff/count.
                # Still marked "reconnecting" before the close await (same
                # reasoning as above): no data can flow while the old socket
                # is closing and the new one is not yet open, clean rotation
                # or not.
                state.ws_state = "reconnecting"
                attempt = 0
                self._subs.live_ws.pop(key, None)
                await self._close_quietly(cm, connection)
                cm, connection = None, None
        finally:
            state.ws_state = "disconnected"
            self._subs.live_ws.pop(key, None)
            await self._close_quietly(cm, connection)


__all__ = [
    "IDLE_TIMEOUT_S",
    "MAX_CONNECTION_AGE_S",
    "MAX_RECONNECT_FAILURES",
    "ConnectFn",
    "ConnectionRunner",
    "WsConnection",
    "default_connect",
    "sync_monotonic",
]
