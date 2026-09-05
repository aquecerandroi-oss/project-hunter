"""Shared fakes for ``test_ws_client*.py`` — not collected by pytest itself
(no ``test_`` prefix), so it is a plain import, not a test module.
"""

from __future__ import annotations

import asyncio
import json
from collections import deque
from typing import Any

from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance.ws import BinanceWsClient


def envelope(stream: str, data: dict[str, Any]) -> str:
    return json.dumps({"stream": stream, "data": data})


def agg_trade_raw(price: str = "100", ts_ms: int = 1, agg_id: int = 1) -> dict[str, Any]:
    return {
        "e": "aggTrade",
        "E": 1,
        "a": agg_id,
        "s": "BTCUSDT",
        "p": price,
        "q": "1",
        "f": 1,
        "l": 1,
        "T": ts_ms,
        "m": False,
    }


def book_ticker_raw() -> dict[str, Any]:
    return {
        "e": "bookTicker",
        "u": 1,
        "s": "BTCUSDT",
        "b": "99",
        "B": "1",
        "a": "101",
        "A": "1",
        "T": 1,
        "E": 1,
    }


class FakeConnection:
    """Yields queued messages from ``recv()``; blocks once exhausted until cancelled."""

    def __init__(self, messages: list[str]) -> None:
        self._messages = list(messages)
        self.closed = False

    async def recv(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")  # pragma: no cover

    async def close(self) -> None:
        self.closed = True


class FakeConnectCM:
    def __init__(self, connection: object) -> None:
        self._connection = connection

    async def __aenter__(self) -> Any:
        if isinstance(self._connection, Exception):
            raise self._connection
        return self._connection

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class ScriptedConnector:
    """Each call to ``connect_fn(url)`` pops the next scripted outcome, holding
    on the last one once the script is exhausted (a test may reconnect more
    times than it explicitly scripted, e.g. while winding down)."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self._last: object = outcomes[-1] if outcomes else None
        self.urls: list[str] = []

    def __call__(self, url: str) -> FakeConnectCM:
        self.urls.append(url)
        if self.outcomes:
            self._last = self.outcomes.pop(0)
        assert self._last is not None
        return FakeConnectCM(self._last)


class RoutedConnector:
    """Dispatches to a different scripted connection per URL prefix.

    Exercises the two-route split (docs/plans/M1.md "Decisão conjunta"):
    depth20/bookTicker on ``/public/stream``, everything else on
    ``/market/stream`` — each route gets its own connection/task.
    """

    def __init__(self, by_prefix: dict[str, object]) -> None:
        self._by_prefix = by_prefix
        self.urls: list[str] = []

    def __call__(self, url: str) -> FakeConnectCM:
        self.urls.append(url)
        for prefix, connection in self._by_prefix.items():
            if url.startswith(prefix):
                return FakeConnectCM(connection)
        raise AssertionError(f"unscripted url {url!r}")


class ThenSignalConnection:
    """Yields queued messages, then sets ``done`` and blocks forever."""

    def __init__(self, messages: list[str], *, done: asyncio.Event) -> None:
        self._messages = list(messages)
        self._done = done

    async def recv(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        self._done.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")  # pragma: no cover

    async def close(self) -> None:
        pass


class RecordingConnection:
    """``recv()`` properly waits for a message (unlike :class:`FakeConnection`,
    which blocks forever once its scripted list is exhausted) so a message
    appended *after* ``recv()`` is already pending — e.g. an ack enqueued by
    ``send()`` — is still delivered. ``send`` records every frame and
    (unless ``auto_ack`` is ``False``) enqueues a matching JSON-RPC ack."""

    def __init__(self, messages: list[str] | None = None, *, auto_ack: bool = True) -> None:
        self._messages: deque[str] = deque(messages or [])
        self._has_message = asyncio.Event()
        if self._messages:
            self._has_message.set()
        self.sent: list[str] = []
        self._auto_ack = auto_ack

    async def recv(self) -> str:
        while not self._messages:
            self._has_message.clear()
            await self._has_message.wait()
        return self._messages.popleft()

    async def send(self, message: str) -> None:
        self.sent.append(message)
        if self._auto_ack:
            rpc_id = json.loads(message)["id"]
            self._messages.append(json.dumps({"result": None, "id": rpc_id}))
            self._has_message.set()

    async def close(self) -> None:
        pass


class WaitThenConnection:
    """Blocks until ``gate`` is set, then yields queued messages."""

    def __init__(self, messages: list[str], *, gate: asyncio.Event) -> None:
        self._messages = list(messages)
        self._gate = gate

    async def recv(self) -> str:
        await self._gate.wait()
        if self._messages:
            return self._messages.pop(0)
        await asyncio.Event().wait()
        raise AssertionError("unreachable")  # pragma: no cover

    async def close(self) -> None:
        pass


async def collect(
    client: BinanceWsClient, symbols: list[str], channels: list[StreamChannel], count: int
) -> list[Any]:
    """Pull exactly ``count`` events, then cleanly tear down the generator
    (which cancels the client's background connection tasks via its own
    ``finally: await self.aclose()``) instead of leaving it to the GC.
    """
    # `AsyncIterator` (the Protocol's declared return type) has no `aclose`;
    # the concrete implementation is always an async generator, which does.
    agen: Any = client.stream(symbols, channels).__aiter__()
    events: list[Any] = []
    try:
        for _ in range(count):
            events.append(await agen.__anext__())
    finally:
        await agen.aclose()
    return events
