"""BinanceWsClient: two-route split, per-connection ``connection_states()``,
``BOOK_DEPTH``, and the connect timeout.

Split out of ``test_ws_client.py`` to stay under the 350-line budget; shared
fakes live in ``ws_test_helpers.py``.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest

from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance import streams
from hunter_exchanges.binance.ws import (
    BOOK_DEPTH,
    MARKET_WS_BASE_URL,
    PUBLIC_WS_BASE_URL,
    BinanceWsClient,
)

from .ws_test_helpers import (
    FakeConnectCM,
    FakeConnection,
    RoutedConnector,
    ScriptedConnector,
    ThenSignalConnection,
    WaitThenConnection,
    agg_trade_raw,
    book_ticker_raw,
    collect,
    depth20_raw,
    envelope,
)

pytestmark = pytest.mark.unit


async def test_book_ticker_alone_is_deferred_forever_without_a_known_last_price() -> None:
    """BOOK_TICKER always routes to /public/stream; with no TRADES channel
    requested at all, a bookTicker frame is still a *received* data event
    (timestamped), just never turned into a NormalizedEvent."""
    conn = FakeConnection([envelope("btcusdt@bookTicker", book_ticker_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    # Not `collect`/`wait_for` on `__anext__`: this frame never becomes an
    # event, and cancelling a pending `__anext__` would tear down (and clear
    # the state of) every connection via the generator's own `aclose()`.
    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.BOOK_TICKER]).__aiter__()
    await asyncio.sleep(0.01)  # let the connection task consume the deferred frame

    state = client.connection_states()["public:0"]
    assert state.route == "public"
    assert state.last_data_event_ts is not None
    await agen.aclose()


async def test_book_ticker_uses_last_price_established_on_the_other_route() -> None:
    """TRADES lives on /market/stream, BOOK_TICKER on /public/stream — two
    separate connections/tasks — but they must still share one ``last_price``
    per :meth:`BinanceWsClient.stream` call."""
    gate = asyncio.Event()
    trade_conn = ThenSignalConnection(
        [envelope("btcusdt@aggTrade", agg_trade_raw(price="100"))], done=gate
    )
    ticker_conn = WaitThenConnection([envelope("btcusdt@bookTicker", book_ticker_raw())], gate=gate)
    connector = RoutedConnector({MARKET_WS_BASE_URL: trade_conn, PUBLIC_WS_BASE_URL: ticker_conn})
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(
        client, ["BTCUSDT"], [StreamChannel.TRADES, StreamChannel.BOOK_TICKER], count=2
    )

    by_kind = {e.kind: e for e in events}
    assert by_kind["trade"].price == Decimal("100")
    assert by_kind["ticker"].last == Decimal("100")
    await client.aclose()


async def test_older_trade_does_not_regress_the_cached_last_price() -> None:
    """A trade with an earlier ``ts`` than the one already cached (a
    duplicate delivered late, e.g. across a reconnect overlap) must not
    replace the newer price a subsequent bookTicker (on the other route)
    republishes."""
    gate = asyncio.Event()
    trade_conn = ThenSignalConnection(
        [
            envelope("btcusdt@aggTrade", agg_trade_raw(price="200", ts_ms=2000)),
            envelope("btcusdt@aggTrade", agg_trade_raw(price="100", ts_ms=1000)),  # older, late
        ],
        done=gate,
    )
    ticker_conn = WaitThenConnection([envelope("btcusdt@bookTicker", book_ticker_raw())], gate=gate)
    connector = RoutedConnector({MARKET_WS_BASE_URL: trade_conn, PUBLIC_WS_BASE_URL: ticker_conn})
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(
        client, ["BTCUSDT"], [StreamChannel.TRADES, StreamChannel.BOOK_TICKER], count=3
    )

    ticker = next(e for e in events if e.kind == "ticker")
    assert ticker.last == Decimal("200")  # never regressed to the older trade's 100
    await client.aclose()


async def test_same_millisecond_trades_tie_break_on_the_aggregate_trade_id() -> None:
    """F10: aggTrade id 2 @ 200 then id 1 @ 100 with the *same* ``T`` — ``ts``
    alone can't order them; the lower id arriving second must not regress
    the cached last price a subsequent bookTicker republishes."""
    gate = asyncio.Event()
    trade_conn = ThenSignalConnection(
        [
            envelope("btcusdt@aggTrade", agg_trade_raw(price="200", ts_ms=1000, agg_id=2)),
            envelope("btcusdt@aggTrade", agg_trade_raw(price="100", ts_ms=1000, agg_id=1)),
        ],
        done=gate,
    )
    ticker_conn = WaitThenConnection([envelope("btcusdt@bookTicker", book_ticker_raw())], gate=gate)
    connector = RoutedConnector({MARKET_WS_BASE_URL: trade_conn, PUBLIC_WS_BASE_URL: ticker_conn})
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(
        client, ["BTCUSDT"], [StreamChannel.TRADES, StreamChannel.BOOK_TICKER], count=3
    )

    ticker = next(e for e in events if e.kind == "ticker")
    assert ticker.last == Decimal("200")  # never regressed to id=1's 100
    await client.aclose()


async def test_book_depth_constant_is_20() -> None:
    assert BOOK_DEPTH == 20


async def test_connection_states_reports_route_and_subscriptions() -> None:
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    await agen.__anext__()

    states = client.connection_states()
    assert list(states.keys()) == ["market:0"]
    state = states["market:0"]
    assert state.route == "market"
    assert state.ws_state == "connected"
    assert state.subscriptions == ("btcusdt@aggTrade",)
    assert state.last_data_event_monotonic is not None
    assert state.last_data_event_ts is not None
    assert state.reconnects == 0
    await agen.aclose()


async def test_connection_states_counts_reconnects() -> None:
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([ConnectionError("boom"), good_conn])
    client = BinanceWsClient(
        connect_fn=connector, sleep=lambda _s: asyncio.sleep(0), rand=lambda: 0.0
    )

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    await agen.__anext__()

    assert client.connection_states()["market:0"].reconnects == 1
    await agen.aclose()


async def test_connection_generation_ignores_a_keys_very_first_connect() -> None:
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert client.connection_generation() == 0
    await client.aclose()


async def test_connection_generation_counts_an_internal_reconnect() -> None:
    """T2.5-adapter: a connection this client repairs on its own, without
    ever ending :meth:`~hunter_exchanges.binance.ws.BinanceWsClient.stream`'s
    generator, still bumps the generation counter — the fact
    ``hunter_market_worker.coverage.CoverageTracker`` logs next to a break it
    detects through ``connection_state()`` instead (see that module's
    docstring for why generation itself is not the break signal)."""
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([ConnectionError("boom"), good_conn])
    client = BinanceWsClient(
        connect_fn=connector, sleep=lambda _s: asyncio.sleep(0), rand=lambda: 0.0
    )

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert client.connection_generation() == 1
    await client.aclose()


async def test_connection_generation_counts_a_forced_single_key_restart() -> None:
    """F8's ``restart_connection`` starts a brand new ``ConnectionRunner.run``
    task whose own first connect never passes through the internal
    ``on_reconnect`` callback — counted instead where a key gets reused."""
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))
    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    await agen.__anext__()
    assert client.connection_generation() == 0

    await client.restart_connection("market:0")

    assert client.connection_generation() == 1
    await agen.aclose()


async def test_queue_progress_reports_zero_before_any_stream_call() -> None:
    client = BinanceWsClient(connect_fn=ScriptedConnector([FakeConnection([])]))
    assert client.queue_progress() == (0, 0, 0)
    await client.aclose()


async def test_queue_progress_tracks_delivery_through_the_real_pipeline() -> None:
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    enqueued, delivered, evicted = client.queue_progress()
    assert enqueued == delivered == 1
    assert evicted == 0
    await client.aclose()


# ---- T2.5e: queue_oldest_pending_ts (CoverageTracker's bounded-delay check) --


async def test_queue_oldest_pending_ts_is_none_before_any_stream_call() -> None:
    client = BinanceWsClient(connect_fn=ScriptedConnector([FakeConnection([])]))
    assert client.queue_oldest_pending_ts() is None
    await client.aclose()


async def test_queue_oldest_pending_ts_is_none_once_the_real_pipeline_catches_up() -> None:
    """Additive pass-through to ``StreamConsumer.oldest_pending_ts`` (see
    ``event_queue.py`` for the mechanics, unit-tested there in isolation):
    with nothing backlogged, there is nothing pending to report."""
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert client.queue_oldest_pending_ts() is None
    await client.aclose()


async def test_ws_state_flips_to_reconnecting_before_the_slow_close_completes() -> None:
    """T2.5-adapter (Astra review, second round, finding 1): a reader
    polling ``connection_state()`` during a slow ``__aexit__`` must already
    see ``"reconnecting"`` — marking the break *after* the close await would
    let that reader believe the connection was healthy for however long the
    close takes."""

    class DyingConnection:
        async def recv(self) -> str:
            raise ConnectionError("boom")

        async def send(self, message: str) -> None:
            return None

        async def close(self) -> None:
            return None

    class SlowCloseConnectCM:
        def __init__(self, connection: object, gate: asyncio.Event) -> None:
            self._connection = connection
            self._gate = gate

        async def __aenter__(self) -> Any:
            return self._connection

        async def __aexit__(self, *exc_info: object) -> None:
            await self._gate.wait()

    gate = asyncio.Event()
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    calls = {"count": 0}

    def connect_fn(url: str) -> Any:
        calls["count"] += 1
        if calls["count"] == 1:
            return SlowCloseConnectCM(DyingConnection(), gate)
        return FakeConnectCM(good_conn)

    client = BinanceWsClient(connect_fn=connect_fn, sleep=lambda _s: asyncio.sleep(0))
    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    await asyncio.sleep(0.02)  # let the first connection fail and enter its slow close

    assert client.connection_states()["market:0"].ws_state == "reconnecting"

    gate.set()  # unblock the close; the reconnect can now proceed
    event = await agen.__anext__()

    assert event.kind == "trade"
    await agen.aclose()


async def test_malformed_only_connection_never_records_a_data_event() -> None:
    conn = FakeConnection(["not json at all"])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    await asyncio.sleep(0.01)  # let the connection task consume the malformed frame

    state = client.connection_states()["market:0"]
    assert state.ws_state == "connected"
    assert state.last_data_event_monotonic is None  # ACK/malformed never count
    assert client.malformed_count == 1
    await agen.aclose()


async def test_connect_timeout_backs_off_without_a_real_wait() -> None:
    """A connect attempt stuck open longer than ``connect_timeout_s`` is
    abandoned (never hangs the whole client on one bad attempt)."""

    class _HangingConnectCM:
        async def __aenter__(self) -> FakeConnection:
            await asyncio.Event().wait()  # never resolves without the timeout
            raise AssertionError("unreachable")  # pragma: no cover

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    calls = {"count": 0}

    def connect_fn(url: str) -> Any:
        calls["count"] += 1
        return _HangingConnectCM() if calls["count"] == 1 else FakeConnectCM(good_conn)

    client = BinanceWsClient(
        connect_fn=connect_fn,
        sleep=lambda _s: asyncio.sleep(0),
        rand=lambda: 0.0,
        connect_timeout_s=0.01,
    )

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert calls["count"] == 2
    await client.aclose()


async def test_more_than_200_symbols_split_into_multiple_connections_per_route() -> None:
    symbols = [f"SYM{i}USDT" for i in range(250)]
    connector = ScriptedConnector([FakeConnection([])])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    agen: Any = client.stream(symbols, [StreamChannel.TRADES]).__aiter__()
    await asyncio.sleep(0.01)

    assert set(client.connection_states().keys()) == {"market:0", "market:1"}
    await agen.aclose()


# ---- T1.6b-A: configurable book cadence, wired end-to-end (A5) ---------------


@pytest.fixture(autouse=True)
def _restore_default_book_cadence() -> Any:  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    yield
    streams.set_book_cadence_ms(streams.DEFAULT_BOOK_CADENCE_MS)


async def test_book_channel_subscribes_and_parses_at_the_default_500ms_cadence() -> None:
    conn = FakeConnection([envelope("btcusdt@depth20@500ms", depth20_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.BOOK], count=1)

    assert events[0].kind == "book"
    assert connector.urls[0].endswith("btcusdt@depth20@500ms")
    await client.aclose()


async def test_book_cadence_ms_constructor_param_overrides_the_default() -> None:
    conn = FakeConnection([envelope("btcusdt@depth20@100ms", depth20_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(
        connect_fn=connector, sleep=lambda _s: asyncio.sleep(0), book_cadence_ms=100
    )

    events = await collect(client, ["BTCUSDT"], [StreamChannel.BOOK], count=1)

    assert events[0].kind == "book"
    assert connector.urls[0].endswith("btcusdt@depth20@100ms")
    await client.aclose()
