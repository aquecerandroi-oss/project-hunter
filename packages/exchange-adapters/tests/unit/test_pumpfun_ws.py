import json

# pyright: reportPrivateUsage=false
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import pytest

from hunter_exchanges.base import ExchangeUnavailable, MalformedMessage
from hunter_exchanges.pumpfun.ws import PumpPortalWsClient

FRAMES = (
    (Path(__file__).parents[1] / "fixtures/pumpfun/pumpportal_ws_capture_raw.jsonl")
    .read_text()
    .splitlines()
)


def test_dedupe_and_decimal() -> None:
    client = PumpPortalWsClient()
    frame = FRAMES[4].replace(
        '"vSolInBondingCurve":30', '"vSolInBondingCurve":30.123456789123456789'
    )
    event = client._parse_frame(frame)
    assert event is not None
    assert event.model_dump()["initial_virtual_sol_reserves"] == Decimal("30.123456789123456789")
    assert client._parse_frame(frame) is None
    assert client.state.dropped_duplicates == 1


@pytest.mark.parametrize("frame", [b"\xff", "[]", "null", "{", '{"txType":"create","pool":"pump"}'])
def test_bad_frames(frame: str | bytes) -> None:
    with pytest.raises(MalformedMessage):
        PumpPortalWsClient()._parse_frame(frame)


def test_other_pool_migration_skipped() -> None:
    assert (
        PumpPortalWsClient()._parse_frame(
            json.dumps({"txType": "migrate", "mint": "m", "signature": "s", "pool": "bonk"})
        )
        is None
    )


class Socket:
    def __init__(self, frames: list[str]) -> None:
        self.frames = iter(frames)
        self.sent: list[str] = []
        self.closed = 0

    async def recv(self) -> str:
        frame = next(self.frames, None)
        if frame is None:
            raise ConnectionError("test disconnect")
        return frame

    async def send(self, message: str) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.closed += 1


async def test_ack_does_not_reset_backoff_and_close_once() -> None:
    sockets: list[Socket] = []
    delays: list[float] = []

    @asynccontextmanager
    async def connect(_: str) -> AsyncGenerator[Socket]:
        socket = Socket([FRAMES[0]])
        sockets.append(socket)
        try:
            yield socket
        finally:
            await socket.close()

    async def sleep(delay: float) -> None:
        delays.append(delay)
        if len(delays) > 4:
            raise RuntimeError("unbounded retries")

    client = PumpPortalWsClient(
        connect_fn=connect, sleep=sleep, rand=lambda: 0, max_reconnect_failures=3
    )
    with pytest.raises(ExchangeUnavailable):
        await anext(client.stream())
    assert delays == [1, 2]
    assert [socket.closed for socket in sockets] == [1, 1, 1]
    assert client.connection_state() == "disconnected"


async def test_close_stops_stream_and_subscribes_only_free() -> None:
    socket = Socket([FRAMES[4], FRAMES[4]])

    @asynccontextmanager
    async def connect(_: str) -> AsyncGenerator[Socket]:
        yield socket

    client = PumpPortalWsClient(connect_fn=connect)
    stream = client.stream()
    await anext(stream)
    await client.aclose()
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert socket.closed == 1
    assert [json.loads(s)["method"] for s in socket.sent] == [
        "subscribeNewToken",
        "subscribeMigration",
    ]


def test_new_live_capture_parses_without_float() -> None:
    path = Path(__file__).parents[1] / "fixtures/pumpfun/pumpportal_ws_a41_live.json"
    frames = json.loads(path.read_text())
    client = PumpPortalWsClient()
    events = [client._parse_frame(frame["raw"]) for frame in frames]
    assert any(event is not None for event in events)


def test_recorded_migration() -> None:
    client = PumpPortalWsClient()
    migrations = [frame for frame in FRAMES if json.loads(frame).get("txType") == "migrate"]
    assert migrations
    event = client._parse_frame(migrations[0])
    assert event is not None
    assert event.kind == "meme_migration"
