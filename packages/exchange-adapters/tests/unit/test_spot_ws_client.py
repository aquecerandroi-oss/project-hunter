"""BinanceSpotWsClient: one route, book sequence guard, reconnect, throttle.

No socket is ever opened: ``connect_fn`` is scripted with the helper fakes
from ``ws_test_helpers`` and the frames are the ones recorded from the real
spot combined stream (``testing/fixtures/spot_ws_*.json``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from hunter_core.domain.market import NormalizedEvent
from hunter_exchanges.base import StreamChannel
from hunter_exchanges.binance_spot.streams import MAX_CONTROL_MESSAGES_PER_S
from hunter_exchanges.binance_spot.throttle import ThrottledConnection, spot_connect
from hunter_exchanges.binance_spot.ws import CONTROL_SEND_BUDGET_PER_S, BinanceSpotWsClient

from .ws_test_helpers import FakeConnectCM, FakeConnection, ScriptedConnector

pytestmark = pytest.mark.unit

FIXTURES = (
    Path(__file__).parents[1] / ".." / "hunter_exchanges" / "testing" / "fixtures"
).resolve()
NOW = datetime(2026, 9, 6, 23, 47, tzinfo=UTC)


def _fixture(name: str) -> tuple[str, dict[str, Any]]:
    raw = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return raw["stream"], raw["data"]


def _frame(name: str) -> str:
    stream, data = _fixture(name)
    return json.dumps({"stream": stream, "data": data})


def _depth_frame(last_update_id: int, best_bid: str = "80482.56") -> str:
    return json.dumps(
        {
            "stream": "btcusdt@depth20@100ms",
            "data": {
                "lastUpdateId": last_update_id,
                "bids": [[best_bid, "1"]],
                "asks": [["80482.57", "1"]],
            },
        }
    )


def _kline_frame(open_time_s: int, *, final: bool = True) -> str:
    return json.dumps(
        {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline",
                "E": open_time_s * 1000 + 59_000,
                "s": "BTCUSDT",
                "k": {
                    "t": open_time_s * 1000,
                    "T": open_time_s * 1000 + 59_999,
                    "s": "BTCUSDT",
                    "i": "1m",
                    "o": "80000.00",
                    "c": "80010.00",
                    "h": "80020.00",
                    "l": "79990.00",
                    "v": "1.5",
                    "n": 10,
                    "x": final,
                    "q": "120000.0",
                    "V": "0.5",
                },
            },
        }
    )


async def _collect(client: BinanceSpotWsClient, symbols: list[str], channels: Any, count: int):
    agen: Any = client.stream(symbols, channels).__aiter__()
    events: list[NormalizedEvent] = []
    try:
        async with asyncio.timeout(5):
            for _ in range(count):
                events.append(await agen.__anext__())
    finally:
        await agen.aclose()
        await client.aclose()
    return events


def _client(connector: Any, **kwargs: Any) -> BinanceSpotWsClient:
    return BinanceSpotWsClient(
        connect_fn=connector,
        received_at_fn=lambda: NOW,
        sleep=_instant_sleep,
        **kwargs,
    )


async def _instant_sleep(seconds: float) -> None:
    await asyncio.sleep(0)


async def test_one_connection_carries_every_spot_channel_on_one_url() -> None:
    connector = ScriptedConnector(
        [FakeConnection([_frame("spot_ws_agg_trade.json"), _frame("spot_ws_kline_1m.json")])]
    )
    client = _client(connector)

    events = await _collect(client, ["BTCUSDT"], [StreamChannel.TRADES, StreamChannel.KLINE_1M], 2)

    assert [e.kind for e in events] == ["trade", "candle"]
    assert len(connector.urls) == 1
    url = connector.urls[0]
    assert url.startswith("wss://stream.binance.com:9443/stream?streams=")
    assert "btcusdt@aggTrade" in url and "btcusdt@kline_1m" in url


async def test_book_ticker_is_emitted_only_after_a_trade_sets_the_last_price() -> None:
    connector = ScriptedConnector(
        [
            FakeConnection(
                [
                    _frame("spot_ws_book_ticker.json"),  # deferred: no last price yet
                    _frame("spot_ws_agg_trade.json"),
                    _frame("spot_ws_book_ticker.json"),
                ]
            )
        ]
    )
    client = _client(connector)

    events = await _collect(
        client, ["BTCUSDT"], [StreamChannel.TRADES, StreamChannel.BOOK_TICKER], 2
    )

    assert [e.kind for e in events] == ["trade", "ticker"]
    ticker = events[1]
    assert ticker.last == Decimal("80482.56000000")  # type: ignore[union-attr]
    assert ticker.bid == Decimal("80482.56000000")  # type: ignore[union-attr]
    assert ticker.ts == NOW  # type: ignore[union-attr]


async def test_an_out_of_sequence_book_frame_is_dropped_not_delivered() -> None:
    """Mandatory case: a partial-depth snapshot whose ``lastUpdateId`` went
    backwards is stale - delivering it would overwrite a newer book."""
    connector = ScriptedConnector(
        [
            FakeConnection(
                [
                    _depth_frame(100, best_bid="80482.56"),
                    _depth_frame(99, best_bid="1.00"),  # stale, must never arrive
                    _depth_frame(101, best_bid="80482.55"),
                ]
            )
        ]
    )
    client = _client(connector)

    events = await _collect(client, ["BTCUSDT"], [StreamChannel.BOOK], 2)

    assert [e.sequence for e in events] == [100, 101]  # type: ignore[union-attr]
    assert client.out_of_sequence_count == 1
    assert client.duplicate_book_count == 0


async def test_a_repeated_book_frame_is_a_duplicate_not_a_regression() -> None:
    """An unchanged book republishing the same ``lastUpdateId`` carries
    nothing new, but it is not a book going backwards either - the two are
    counted apart so a real regression is never buried under repeats."""
    connector = ScriptedConnector(
        [FakeConnection([_depth_frame(100), _depth_frame(100), _depth_frame(102)])]
    )
    client = _client(connector)

    events = await _collect(client, ["BTCUSDT"], [StreamChannel.BOOK], 2)

    assert [e.sequence for e in events] == [100, 102]  # type: ignore[union-attr]
    assert client.duplicate_book_count == 1
    assert client.out_of_sequence_count == 0


async def test_the_sequence_guard_is_per_symbol() -> None:
    frames = [
        _depth_frame(500),
        json.dumps(
            {
                "stream": "ethusdt@depth20@100ms",
                "data": {"lastUpdateId": 7, "bids": [["4000", "1"]], "asks": [["4001", "1"]]},
            }
        ),
    ]
    connector = ScriptedConnector([FakeConnection(frames)])
    client = _client(connector)

    events = await _collect(client, ["BTCUSDT", "ETHUSDT"], [StreamChannel.BOOK], 2)

    assert [e.symbol for e in events] == ["BTCUSDT", "ETHUSDT"]  # type: ignore[union-attr]
    assert client.out_of_sequence_count == 0
    assert client.duplicate_book_count == 0


async def test_a_malformed_frame_is_counted_and_skipped_never_raised() -> None:
    connector = ScriptedConnector(
        [
            FakeConnection(
                [
                    "{not json",
                    json.dumps({"stream": "btcusdt@aggTrade", "data": {"a": 1}}),
                    json.dumps({"stream": "btcusdt@unknownStream", "data": {}}),
                    _frame("spot_ws_agg_trade.json"),
                ]
            )
        ]
    )
    client = _client(connector)

    events = await _collect(client, ["BTCUSDT"], [StreamChannel.TRADES], 1)

    assert events[0].kind == "trade"
    assert client.malformed_count == 3


async def test_a_reconnect_leaves_a_visible_gap_and_bumps_the_generation() -> None:
    """Mandatory case "reconnect with gap": the socket dies mid-stream; the
    client reconnects on its own, and the candle for the minute in between
    never arrives. The worker learns about it from ``connection_generation``
    (T2.5's coverage break), which is what opens an ``ingestion_gaps`` row -
    the adapter never invents the missing minute.
    """
    first = FakeConnection([_kline_frame(1_788_738_000), "boom"])
    second = FakeConnection([_kline_frame(1_788_738_120)])  # 1788738060 is missing
    connector = ScriptedConnector([first, second])

    client = BinanceSpotWsClient(
        connect_fn=_flaky_connector(connector),
        received_at_fn=lambda: NOW,
        sleep=_instant_sleep,
        rand=lambda: 0.0,
    )

    events = await _collect(client, ["BTCUSDT"], [StreamChannel.KLINE_1M], 2)

    open_times = [int(e.open_time.timestamp()) for e in events]  # type: ignore[union-attr]
    assert open_times == [1_788_738_000, 1_788_738_120]
    assert open_times[1] - open_times[0] == 120  # one whole minute is missing
    assert client.connection_generation() >= 1


def _flaky_connector(connector: ScriptedConnector) -> Any:
    """``recv()`` raises on the sentinel ``"boom"`` frame, like a dropped socket."""

    def connect(url: str) -> Any:
        cm = connector(url)
        inner: Any = cm._connection  # pyright: ignore[reportPrivateUsage]

        class _Boom:
            async def recv(self) -> str | bytes:
                raw = await inner.recv()
                if raw == "boom":
                    raise ConnectionError("socket dropped")
                return raw

            async def send(self, message: str) -> None:
                pass

            async def close(self) -> None:
                await inner.close()

        return FakeConnectCM(_Boom())

    return connect


def _connect_to(connection: object) -> Any:
    """A ``connect_fn`` that always hands out the same fake socket."""

    def connect(url: str) -> FakeConnectCM:
        return FakeConnectCM(connection)

    return connect


class _Recorder:
    """A live socket that only records what we send it."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def recv(self) -> str | bytes:
        await asyncio.Event().wait()
        raise AssertionError("unreachable")  # pragma: no cover

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        pass


async def test_the_throttle_delays_the_frame_over_the_spot_budget() -> None:
    """Binance spot allows 5 incoming messages/s per connection, PONG
    included; our own budget is one below that. The frame over it waits -
    it is never dropped, and never sent over the limit."""
    inner = _Recorder()
    now = 0.0
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        nonlocal now
        waits.append(seconds)
        now += seconds

    connection = ThrottledConnection(
        inner, max_per_s=CONTROL_SEND_BUDGET_PER_S, clock=lambda: now, sleep=sleep
    )

    for i in range(CONTROL_SEND_BUDGET_PER_S + 1):
        await connection.send(f"frame-{i}")

    assert len(inner.sent) == CONTROL_SEND_BUDGET_PER_S + 1
    assert waits == [1.0]  # exactly one wait, for the frame over the budget
    assert CONTROL_SEND_BUDGET_PER_S < MAX_CONTROL_MESSAGES_PER_S


async def test_every_spot_connection_is_throttled() -> None:
    inner = _Recorder()
    client = _client(_connect_to(inner))
    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()
    task = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    live = client._subs.live_ws["spot:0"]  # pyright: ignore[reportPrivateUsage]

    assert isinstance(live, ThrottledConnection)

    await _shutdown(task, agen, client)


async def test_update_subscriptions_sends_only_the_diff() -> None:
    inner = _Recorder()
    client = _client(_connect_to(inner))
    agen: Any = client.stream(["BTCUSDT", "ETHUSDT"], [StreamChannel.TRADES]).__aiter__()
    task = asyncio.ensure_future(agen.__anext__())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await client.update_subscriptions(["SOLUSDT"], ["ETHUSDT"], [StreamChannel.TRADES])
    frames = [json.loads(m) for m in inner.sent]

    await _shutdown(task, agen, client)

    methods = [(f["method"], f["params"]) for f in frames]
    assert ("UNSUBSCRIBE", ["ethusdt@aggTrade"]) in methods
    assert ("SUBSCRIBE", ["solusdt@aggTrade"]) in methods
    assert all("btcusdt@aggTrade" not in params for _, params in methods)


async def _shutdown(task: Any, agen: Any, client: BinanceSpotWsClient) -> None:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    await agen.aclose()
    await client.aclose()


async def test_connection_state_and_queue_progress_are_reported() -> None:
    connector = ScriptedConnector([FakeConnection([_frame("spot_ws_agg_trade.json")])])
    client = _client(connector)
    agen: Any = client.stream(["BTCUSDT"], [StreamChannel.TRADES]).__aiter__()

    async with asyncio.timeout(5):
        await agen.__anext__()

    assert client.connection_state() == "connected"
    states = client.connection_states()
    assert list(states) == ["spot:0"]
    assert states["spot:0"].subscriptions == ("btcusdt@aggTrade",)
    assert states["spot:0"].last_data_event_ts is not None
    enqueued, delivered, evicted = client.queue_progress()
    assert enqueued == delivered + evicted == 1

    await agen.aclose()
    await client.aclose()


def test_the_real_connector_turns_the_library_keepalive_ping_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Astra diff review, must-fix 1: ``websockets`` defaults to a PING every
    20s, and Binance counts PING/PONG inside the same 5 messages/s budget as
    our control frames - 4 control frames + PING + PONG would be 6."""
    captured: dict[str, Any] = {}

    class _FakeWebsockets:
        @staticmethod
        def connect(url: str, **kwargs: Any) -> object:
            captured["url"] = url
            captured.update(kwargs)
            return object()

    monkeypatch.setitem(sys.modules, "websockets", _FakeWebsockets)

    spot_connect("wss://stream.binance.com:9443/stream?streams=btcusdt@aggTrade")

    assert captured["ping_interval"] is None
