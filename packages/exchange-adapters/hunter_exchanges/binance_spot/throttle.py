"""Outgoing-message throttle for one Binance **SPOT** WebSocket connection.

Binance spot documents a hard limit of **5 incoming messages per second**
per connection - and it counts *every* message we send, including the PONG
frames the websockets library answers Binance's pings with, not only our
``SUBSCRIBE``/``UNSUBSCRIBE``. Going over it gets the connection
disconnected, and repeated offenders get the IP banned.

The subscription controller sends its frames as soon as a universe diff
arrives, so three quick diffs can produce six frames in a burst. This module
wraps the connection instead of changing that controller: every ``send``
waits for a slot in a sliding one-second window, so a burst is *delayed*,
never dropped and never silently over the limit.

One slot of the five is left for the library's own PONG traffic
(``CONTROL_SEND_BUDGET_PER_S`` in :mod:`hunter_exchanges.binance_spot.ws`),
because that traffic is not ours to schedule.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

from hunter_exchanges.binance.connection import ConnectFn, WsConnection

__all__ = ["ThrottledConnection", "spot_connect", "throttled_connect"]


class ThrottledConnection:
    """A :class:`~hunter_exchanges.binance.connection.WsConnection` whose
    ``send`` never exceeds ``max_per_s`` messages in any one-second window.

    ``recv``/``close`` pass straight through; ``clock`` is monotonic and
    ``sleep`` is injectable, so tests measure the wait instead of taking it.
    """

    def __init__(
        self,
        inner: WsConnection,
        *,
        max_per_s: int,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._inner = inner
        self._max_per_s = max_per_s
        self._clock = clock
        self._sleep = sleep
        self._sent_at: deque[float] = deque()

    async def _reserve(self) -> None:
        while True:
            now = self._clock()
            while self._sent_at and now - self._sent_at[0] >= 1.0:
                self._sent_at.popleft()
            if len(self._sent_at) < self._max_per_s:
                self._sent_at.append(now)
                return
            await self._sleep(max(0.0, 1.0 - (now - self._sent_at[0])))

    async def send(self, message: str) -> None:
        await self._reserve()
        await self._inner.send(message)

    async def recv(self) -> str | bytes:
        return await self._inner.recv()

    async def close(self) -> None:
        await self._inner.close()


class _ThrottledCM:
    def __init__(
        self,
        inner_cm: AbstractAsyncContextManager[WsConnection],
        *,
        max_per_s: int,
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        self._inner_cm = inner_cm
        self._max_per_s = max_per_s
        self._clock = clock
        self._sleep = sleep

    async def __aenter__(self) -> WsConnection:
        connection = await self._inner_cm.__aenter__()
        return ThrottledConnection(
            connection, max_per_s=self._max_per_s, clock=self._clock, sleep=self._sleep
        )

    async def __aexit__(self, *exc_info: Any) -> None:
        await self._inner_cm.__aexit__(*exc_info)


def throttled_connect(
    connect_fn: ConnectFn,
    *,
    max_per_s: int,
    clock: Callable[[], float],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> ConnectFn:
    """Wrap ``connect_fn`` so every connection it opens is throttled."""

    def connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
        return _ThrottledCM(connect_fn(url), max_per_s=max_per_s, clock=clock, sleep=sleep)

    return connect


def spot_connect(url: str) -> AbstractAsyncContextManager[WsConnection]:
    """Open a real spot socket with the library's own keepalive PING **off**.

    ``websockets.connect`` defaults to ``ping_interval=20``: it sends a PING
    of its own every 20s. Binance counts that PING - and the PONG it answers
    Binance's own pings with - inside the same 5 messages/s budget as our
    ``SUBSCRIBE``/``UNSUBSCRIBE`` frames (Astra diff review, T3.0a
    must-fix 1: 4 control frames + library PING + PONG = 6 in one window,
    over the limit and a disconnect).

    Turning our keepalive off does not blind us: Binance pings every ~20s and
    ``websockets`` still answers those automatically, and a socket that stops
    delivering frames is caught by ``ConnectionRunner``'s idle timeout (60s),
    which is the check that actually protects against a half-open socket.
    """
    import websockets

    return websockets.connect(url, ping_interval=None)  # type: ignore[return-value]
