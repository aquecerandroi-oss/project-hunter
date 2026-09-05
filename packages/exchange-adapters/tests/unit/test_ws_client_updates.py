"""BinanceWsClient: update_subscriptions, bounded queue overflow, reader
failure propagation — the T1.2b additions market-worker's ``streaming.py``
relies on. Split out of ``test_ws_client*.py`` to stay under the 350-line
budget; shared fakes live in ``ws_test_helpers.py``.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.base import ExchangeUnavailable, StreamChannel
from hunter_exchanges.binance.ws import MARKET_WS_BASE_URL, PUBLIC_WS_BASE_URL, BinanceWsClient

from .ws_test_helpers import (
    FakeConnectCM,
    FakeConnection,
    RecordingConnection,
    RoutedConnector,
    ScriptedConnector,
    agg_trade_raw,
    book_ticker_raw,
    envelope,
)

pytestmark = pytest.mark.unit


async def test_update_subscriptions_sends_only_the_diff_and_keeps_the_connection() -> None:
    conn = RecordingConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(["BTCUSDT", "ETHUSDT"], [StreamChannel.TRADES]).__aiter__()
    first = await agen.__anext__()
    assert first.kind == "trade"

    await client.update_subscriptions(["XRPUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])
    await asyncio.sleep(0.01)  # let the connection task read back the ack frames

    methods = [json.loads(frame)["method"] for frame in conn.sent]
    assert methods == ["UNSUBSCRIBE", "SUBSCRIBE"]
    states = client.connection_states()
    assert set(states.keys()) == {"market:0"}  # free capacity: no new connection
    assert len(connector.urls) == 1  # existing symbols' connection was never reopened
    assert "ethusdt@aggTrade" not in states["market:0"].subscriptions
    assert "xrpusdt@aggTrade" in states["market:0"].subscriptions
    assert "btcusdt@aggTrade" in states["market:0"].subscriptions  # untouched symbol stays
    await agen.aclose()


async def test_update_subscriptions_overflow_opens_a_second_connection() -> None:
    symbols = [f"SYM{i}USDT" for i in range(200)]
    conn = RecordingConnection([envelope("sym0usdt@aggTrade", agg_trade_raw(price="1"))])
    second_conn = FakeConnection([envelope("newusdt@aggTrade", agg_trade_raw(price="2"))])
    connector = ScriptedConnector([conn, second_conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(symbols, [StreamChannel.TRADES]).__aiter__()
    await agen.__anext__()

    await client.update_subscriptions(["NEWUSDT"], [], [StreamChannel.TRADES])
    await asyncio.sleep(0.01)

    assert set(client.connection_states().keys()) == {"market:0", "market:1"}
    await agen.aclose()


async def test_reconnect_failure_past_the_limit_propagates_to_the_consumer() -> None:
    connector = ScriptedConnector(
        [ConnectionError("1"), ConnectionError("2"), ConnectionError("3")]
    )
    client = BinanceWsClient(
        connect_fn=connector,
        sleep=lambda _s: asyncio.sleep(0),
        rand=lambda: 0.0,
        max_reconnect_failures=3,
    )

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    # Let the connection task exhaust its retries and die *before* the
    # generator's own `finally: await self.aclose()` (triggered only once
    # something actually awaits `__anext__()`) clears every state again —
    # this is the window the worker's watchdog would observe.
    for _ in range(100):
        if client.connection_states().get("market:0") is None:
            await asyncio.sleep(0)
            continue
        if client.connection_states()["market:0"].ws_state == "disconnected":
            break
        await asyncio.sleep(0)
    assert client.connection_states()["market:0"].ws_state == "disconnected"

    with pytest.raises(ExchangeUnavailable):
        await agen.__anext__()


async def test_reconnect_failure_below_the_limit_keeps_retrying() -> None:
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([ConnectionError("1"), ConnectionError("2"), good_conn])
    client = BinanceWsClient(
        connect_fn=connector,
        sleep=lambda _s: asyncio.sleep(0),
        rand=lambda: 0.0,
        max_reconnect_failures=5,
    )

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    event = await agen.__anext__()

    assert event.kind == "trade"
    await agen.aclose()


class _RecvFailsImmediately:
    """A handshake that always succeeds, but whose first ``recv()`` always
    raises — a connection that never proves itself alive."""

    async def recv(self) -> str:
        raise ConnectionResetError("closed immediately after handshake")

    async def close(self) -> None:
        pass


async def test_handshake_success_without_data_does_not_reset_the_failure_count() -> None:
    """Astra review, T1.2b resume finding 6: a connection that keeps
    handshaking fine but whose first ``recv()`` always fails must still hit
    the reconnect-failure limit — a reset on connect alone would let a
    flapping endpoint retry forever at the minimum backoff."""
    connector = ScriptedConnector(
        [_RecvFailsImmediately(), _RecvFailsImmediately(), _RecvFailsImmediately()]
    )
    client = BinanceWsClient(
        connect_fn=connector,
        sleep=lambda _s: asyncio.sleep(0),
        rand=lambda: 0.0,
        max_reconnect_failures=3,
    )

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    with pytest.raises(ExchangeUnavailable):
        await agen.__anext__()


class _GatedConnectCM:
    """Blocks ``__aenter__`` on ``gate`` — simulates a handshake still in
    flight while the test drives ``update_subscriptions`` concurrently."""

    def __init__(self, connection: Any, gate: asyncio.Event) -> None:
        self._connection = connection
        self._gate = gate

    async def __aenter__(self) -> Any:
        await self._gate.wait()
        return self._connection

    async def __aexit__(self, *exc_info: object) -> None:
        return None


async def test_symbol_added_during_handshake_is_caught_up_once_connected() -> None:
    """Astra review, T1.2b resume round 2, finding 3: a universe diff that
    lands while the connection is mid-handshake (no live socket to send
    over yet) must not wait for the next rotation (up to 23.5h) — the
    newly-live connection reconciles against the group's *current* state."""
    gate = asyncio.Event()
    conn = RecordingConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    client = BinanceWsClient(
        connect_fn=lambda _url: _GatedConnectCM(conn, gate), sleep=lambda _s: asyncio.sleep(0)
    )

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    next_event = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)  # let the task reach _open() and block on the gate

    await client.update_subscriptions(["ETHUSDT"], [], [StreamChannel.TRADES])

    gate.set()
    first = await next_event

    assert first.kind == "trade"
    methods = [json.loads(frame)["method"] for frame in conn.sent]
    assert methods == ["SUBSCRIBE"]  # catch-up sent once the socket became live
    assert "ethusdt@aggTrade" in client.connection_states()["market:0"].subscriptions
    await agen.aclose()


async def test_catch_up_failure_goes_through_the_normal_reconnect_backoff() -> None:
    """Astra review, T1.2b resume round 3, finding 2: a catch-up frame that
    fails to send must not bypass the reconnect-attempt/backoff machinery —
    it is a connection failure like any other."""

    class _FailsOnSend(RecordingConnection):
        async def send(self, message: str) -> None:
            raise ConnectionResetError("dropped while sending the catch-up frame")

    gate = asyncio.Event()
    first_bad = _FailsOnSend([])
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    calls = {"count": 0}

    def connect_fn(url: str) -> Any:
        calls["count"] += 1
        return _GatedConnectCM(first_bad, gate) if calls["count"] == 1 else FakeConnectCM(good_conn)

    client = BinanceWsClient(connect_fn=connect_fn, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    next_event = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)  # let the first connection attempt reach _open() and block on the gate

    # A diff mid-handshake means catch_up() must actually send once this
    # (about-to-fail) connection becomes live.
    await client.update_subscriptions(["ETHUSDT"], [], [StreamChannel.TRADES])
    gate.set()

    event = await next_event
    assert event.kind == "trade"  # recovered via the normal reconnect path, not an uncaught crash
    assert client.connection_states()["market:0"].reconnects >= 1
    await agen.aclose()


async def test_update_subscriptions_evicts_the_removed_symbols_last_trade_cache() -> None:
    """F11: ``_last_trade`` must not grow forever as the 15-minute universe
    refresh churns symbols for weeks — a removed symbol's cached price is
    dropped immediately, not kept for the life of the process."""
    conn = RecordingConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(["BTCUSDT", "ETHUSDT"], [StreamChannel.TRADES]).__aiter__()
    first = await agen.__anext__()
    assert first.kind == "trade"
    client._last_trade["ETHUSDT"] = (Decimal("100"), first.ts)  # type: ignore[attr-defined]

    await client.update_subscriptions([], ["ETHUSDT"], [StreamChannel.TRADES])
    await asyncio.sleep(0.01)

    assert "ETHUSDT" not in client._last_trade  # type: ignore[attr-defined]
    assert "BTCUSDT" in client._last_trade  # type: ignore[attr-defined] # untouched symbol stays
    await agen.aclose()


async def test_restart_connection_leaves_other_connections_untouched() -> None:
    """F8: restarting one connection's task (e.g. after F6's rejected-ack
    recovery) must never tear down a healthy sibling connection — the
    market-worker's blanket ``restart_stream=True`` fallback (``aclose()``
    then reopen everything) is exactly the avoidable book/ticker hole this
    exists to prevent."""
    market_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    public_conn = FakeConnection([envelope("btcusdt@bookTicker", book_ticker_raw())])
    connector = RoutedConnector({MARKET_WS_BASE_URL: market_conn, PUBLIC_WS_BASE_URL: public_conn})
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(
        ["BTCUSDT"], [StreamChannel.TRADES, StreamChannel.BOOK_TICKER]
    ).__aiter__()
    await asyncio.sleep(0.01)  # let both connections prove themselves live

    before = client.connection_states()
    assert before["public:0"].ws_state == "connected"
    assert before["market:0"].ws_state == "connected"
    public_event_before = before["public:0"].last_data_event_monotonic

    await client.restart_connection("market:0")
    await asyncio.sleep(0.01)  # let the restarted task reconnect

    after = client.connection_states()
    assert after["public:0"].ws_state == "connected"
    assert after["public:0"].reconnects == 0  # never touched
    assert after["public:0"].last_data_event_monotonic == public_event_before  # untouched
    assert after["market:0"].ws_state == "connected"  # restarted, and live again
    await agen.aclose()


async def test_bounded_queue_overflow_is_observable_via_connection_states() -> None:
    """A tiny ``queue_maxsize`` with a consumer that never drains lets the
    drop policy trigger deterministically without needing thousands of
    events."""
    messages = [envelope("btcusdt@aggTrade", agg_trade_raw(price=str(i))) for i in range(5)]
    conn = FakeConnection(messages)
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(
        connect_fn=connector, sleep=lambda _s: asyncio.sleep(0), queue_maxsize=2
    )

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    await asyncio.sleep(0.01)  # let every message be produced before anything is consumed

    state = client.connection_states()["market:0"]
    assert state.dropped_events > 0
    await agen.aclose()
