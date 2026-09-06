"""BinanceWsClient: reconnect + resubscribe, backoff, malformed messages.

``connect_fn`` is a fake async context manager instead of a real socket, so
every test controls exactly what "the network" does and never waits real
time (backoff sleep is captured, not awaited). Route-splitting, per-connection
``connection_states()``, and the connect timeout live in
``test_ws_client_states.py`` (kept separate to stay under the 350-line budget).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance.ws import BinanceWsClient

from .ws_test_helpers import (
    FakeConnection,
    ScriptedConnector,
    agg_trade_raw,
    collect,
    envelope,
)

pytestmark = pytest.mark.unit


async def test_stream_yields_normalized_events_from_a_connection() -> None:
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert events[0].price == Decimal("100")
    await client.aclose()


async def test_reconnects_after_a_connection_failure_and_resubscribes_same_url() -> None:
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([ConnectionError("boom"), good_conn])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = BinanceWsClient(connect_fn=connector, sleep=fake_sleep, rand=lambda: 0.0)

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert len(connector.urls) == 2
    assert connector.urls[0] == connector.urls[1]  # same streams re-requested: "resubscribe"
    assert sleeps == [1.0]  # first backoff attempt, no jitter (rand=0)
    await client.aclose()


async def test_backoff_grows_exponentially_up_to_the_cap() -> None:
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector(
        [ConnectionError("1"), ConnectionError("2"), ConnectionError("3"), good_conn]
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = BinanceWsClient(connect_fn=connector, sleep=fake_sleep, rand=lambda: 0.0)

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert sleeps == [1.0, 2.0, 4.0]
    await client.aclose()


async def test_malformed_envelope_is_counted_and_never_raised() -> None:
    conn = FakeConnection(["not json at all", envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert len(events) == 1  # the malformed message never reached the queue
    assert client.malformed_count == 1
    await client.aclose()


async def test_malformed_envelope_as_raw_bytes_is_counted_and_never_raised() -> None:
    """T1.6b-A (orjson): a real socket frame often arrives as ``bytes``, not
    ``str``. ``orjson.loads`` takes bytes directly (no ``.decode()`` needed);
    ``orjson.JSONDecodeError`` (a ``ValueError`` subclass, not
    ``json.JSONDecodeError``) must still be caught here, or a malformed byte
    frame propagates out of ``_handle_raw_message`` instead of being counted."""
    conn = FakeConnection([b"not json at all", envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert len(events) == 1
    assert client.malformed_count == 1
    await client.aclose()


async def test_well_formed_envelope_as_raw_bytes_parses_normally() -> None:
    """A good frame delivered as ``bytes`` (the common real-socket case) must
    parse identically to the same frame delivered as ``str``."""
    conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw()).encode("utf-8")])
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert events[0].price == Decimal("100")
    await client.aclose()


async def test_malformed_message_body_is_counted_and_never_raised() -> None:
    bad_trade = agg_trade_raw()
    del bad_trade["p"]  # missing required field -> MalformedMessage from normalize
    conn = FakeConnection(
        [envelope("btcusdt@aggTrade", bad_trade), envelope("btcusdt@aggTrade", agg_trade_raw())]
    )
    connector = ScriptedConnector([conn])
    client = BinanceWsClient(connect_fn=connector, sleep=lambda _s: asyncio.sleep(0))

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert len(events) == 1
    assert client.malformed_count == 1
    await client.aclose()


async def test_connection_state_reflects_no_connection_before_streaming_starts() -> None:
    client = BinanceWsClient(connect_fn=ScriptedConnector([FakeConnection([])]))

    assert client.connection_state() == "disconnected"
    await client.aclose()


async def test_quiet_socket_rotates_cleanly_at_the_rotation_deadline() -> None:
    """F7: ``recv()`` must have a deadline — a connection whose symbols go
    quiet must still rotate at ``max_connection_age_s`` instead of hanging
    until Binance's own 24h cut (or forever, in a half-open-socket case).

    T2.5-adapter: this test used the real event-loop clock (no ``clock=``
    injected) to compute ``remaining = max_age - (clock() - connected_at)``
    against a 20ms budget. Real scheduling jitter between reading
    ``connected_at`` and the loop's first read of ``remaining`` silently ate
    into that budget, so the *actual* timeout handed to
    ``asyncio.wait_for(connection.recv(), ...)`` varied with how busy the
    machine was instead of always being ``max_age`` — flaky under load.
    Pinning ``clock()`` to a fixed instant for every read makes the computed
    timeout deterministic; ``asyncio.wait_for`` still waits a real (but now
    fixed and known) 20ms for the quiet connection's deadline to fire, which
    is what actually exercises the rotation."""
    quiet_conn = FakeConnection([])  # recv() blocks forever: a quiet/half-open socket
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([quiet_conn, good_conn])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    def fake_clock() -> float:
        return 0.0  # every read is the same instant: no real-time budget erosion

    client = BinanceWsClient(
        connect_fn=connector,
        clock=fake_clock,
        sleep=fake_sleep,
        rand=lambda: 0.0,
        max_connection_age_s=0.05,  # tiny, but now a fixed real wait_for timeout
        idle_timeout_s=10.0,  # much larger: the rotation deadline fires first
    )

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert len(connector.urls) == 2
    assert sleeps == []  # a clean rotation never backs off
    await client.aclose()


async def test_idle_socket_reconnects_with_backoff_before_the_rotation_deadline() -> None:
    """F7: an idle timeout reached *before* the rotation deadline is a
    connection failure (half-open socket, dead symbols) — backoff and
    reconnect, never silently wait for the 24h cut."""
    quiet_conn = FakeConnection([])
    good_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([quiet_conn, good_conn])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    client = BinanceWsClient(
        connect_fn=connector,
        sleep=fake_sleep,
        rand=lambda: 0.0,
        max_connection_age_s=100.0,  # far away
        idle_timeout_s=0.02,  # tiny real deadline: fires first
    )

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert len(connector.urls) == 2
    assert sleeps == [1.0]  # a genuine connection failure backs off like any other
    await client.aclose()


async def test_proactive_reconnect_before_max_connection_age() -> None:
    """A connection older than ``max_connection_age_s`` is dropped and re-opened,
    even with no error — Binance's own 24h limit is never hit."""
    first_conn = FakeConnection([])  # never yields real data; ages out immediately
    second_conn = FakeConnection([envelope("btcusdt@aggTrade", agg_trade_raw())])
    connector = ScriptedConnector([first_conn, second_conn])
    # 1st call: connect_attempt_started_monotonic (0.0). 2nd: connected_at
    # (0.0, same instant). 3rd: the age check, which already reads 100 — past
    # max_connection_age_s=1.0 — so it reconnects without ever calling recv()
    # on the first (aged-out) connection.
    clock_values = iter([0.0, 0.0, 100.0])

    def fake_clock() -> float:
        return next(clock_values, 100.0)

    client = BinanceWsClient(
        connect_fn=connector,
        clock=fake_clock,
        sleep=lambda _s: asyncio.sleep(0),
        max_connection_age_s=1.0,
    )

    events = await collect(client, ["BTCUSDT"], [StreamChannel.TRADES], count=1)

    assert events[0].kind == "trade"
    assert len(connector.urls) == 2
    await client.aclose()
