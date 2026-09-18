"""``SolanaWsClient`` — frame parsing over recorded live fixtures, id matching,
and reconnect (T4.52b-1)."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import websockets

from hunter_exchanges.base import MalformedMessage
from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID, decode_bonding_curve_account
from hunter_exchanges.pumpfun.rpc_ws import SolanaWsClient
from hunter_exchanges.pumpfun.rpc_ws_models import (
    AccountNotification,
    LogsNotification,
    Notification,
    SlotNotification,
)
from hunter_exchanges.pumpfun.trade_event import normalized_curve_trade, trade_events_from_logs

FIXTURES = Path(__file__).parents[1] / "fixtures/pumpfun"


def _lines(name: str) -> list[str]:
    return (FIXTURES / name).read_text().splitlines()


LOGS_LINES = _lines("t452b_ws_logs_notifications_raw.jsonl")
ACCOUNT_LINES = _lines("t452b_ws_account_notifications_raw.jsonl")
SLOT_LINES = _lines("t452b_ws_slot_notifications_raw.jsonl")


def _client() -> SolanaWsClient:
    """A client with no live connection — only its pure ``_parse_frame`` is
    under test here; every fixture line's ``subscription`` id is pre-bound to
    logical id ``1`` so parsing proceeds past the id-mapping step."""
    client = SolanaWsClient()
    for line in LOGS_LINES + ACCOUNT_LINES + SLOT_LINES:
        server_id = json.loads(line)["params"]["subscription"]
        client._logical_of_server[server_id] = 1
    return client


def test_logs_fixture_line_with_a_trade_builds_a_decimal_normalized_curve_trade() -> None:
    client = _client()
    built = 0
    for line in LOGS_LINES:
        notif = client._parse_frame(line)
        assert isinstance(notif, LogsNotification | type(None))
        if notif is None or notif.err is not None:
            continue
        (event,) = trade_events_from_logs(notif.logs)[:1] or (None,)
        if event is None:
            continue
        trade = normalized_curve_trade(event, slot=notif.slot, signature=notif.signature)
        assert trade.mint == event.mint
        assert trade.slot == notif.slot and trade.signature == notif.signature
        for field_name in (
            "lamports",
            "virtual_sol_reserves",
            "virtual_token_reserves",
            "real_sol_reserves",
            "real_token_reserves",
        ):
            assert isinstance(getattr(trade, field_name), Decimal)
        built += 1
    assert built > 0, "no fixture line decoded a trade — the live capture is expected to have one"


def test_account_fixture_lines_decode_the_bonding_curve_account() -> None:
    client = _client()
    decoded = 0
    for line in ACCOUNT_LINES:
        notif = client._parse_frame(line)
        assert isinstance(notif, AccountNotification)
        account = decode_bonding_curve_account(notif.data_base64, owner=notif.owner)
        assert notif.owner == PUMP_PROGRAM_ID
        assert account.virtual_token_reserves >= 0
        decoded += 1
    assert decoded == len(ACCOUNT_LINES)


def test_slot_fixture_lines_parse() -> None:
    client = _client()
    for line in SLOT_LINES:
        notif = client._parse_frame(line)
        assert isinstance(notif, SlotNotification)
        assert notif.slot >= notif.parent >= 0


def test_notification_for_an_unknown_subscription_is_dropped_and_counted() -> None:
    client = SolanaWsClient()  # no server id pre-bound
    line = LOGS_LINES[0]
    assert client._parse_frame(line) is None
    assert client.state.dropped == 1


@pytest.mark.parametrize(
    "frame",
    [
        b"\xff",
        "not json",
        "[]",
        '{"method": "logsNotification", "params": "not-an-object"}',
        '{"method": "logsNotification", "params": {"subscription": "not-an-int", "result": {}}}',
        '{"method": "weirdNotification", "params": {"subscription": 424242, "result": {}}}',
    ],
)
def test_malformed_frames_raise(frame: str | bytes) -> None:
    client = _client()
    client._logical_of_server[424242] = 1  # so an unknown *method* is what's under test here
    with pytest.raises(MalformedMessage):
        client._parse_frame(frame)


class _FakeConnection:
    """Echoes a unique subscription id back for every request it sees —
    enough to prove request/response ``id`` matching across three concurrent
    ``subscribe_*`` calls sharing one connection."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._next_sub_id = 9000

    async def recv(self) -> str:
        return await self._queue.get()

    async def send(self, message: str) -> None:
        request = json.loads(message)
        self.sent.append(request)
        self._next_sub_id += 1
        await self._queue.put(
            json.dumps({"jsonrpc": "2.0", "result": self._next_sub_id, "id": request["id"]})
        )

    async def close(self) -> None:
        pass


async def _drain(client: SolanaWsClient) -> None:
    async for _ in client.listen():
        pass  # pragma: no cover — this fake never sends a notification


async def test_subscribe_logs_account_slot_get_distinct_ids_matched_by_request_id() -> None:
    connection = _FakeConnection()

    @asynccontextmanager
    async def connect(_: str) -> AsyncGenerator[_FakeConnection]:
        yield connection

    client = SolanaWsClient(connect_fn=connect)
    task = asyncio.create_task(_drain(client))
    try:
        logs_id = await client.subscribe_logs(mentions=["curve-pda"])
        account_id = await client.subscribe_account("curve-pda")
        slot_id = await client.subscribe_slot()
    finally:
        await client.aclose()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert {logs_id, account_id, slot_id} == {1, 2, 3}
    methods = [request["method"] for request in connection.sent]
    assert methods == ["logsSubscribe", "accountSubscribe", "slotSubscribe"]
    ids = [request["id"] for request in connection.sent]
    assert ids == sorted(set(ids)) and len(set(ids)) == 3  # every request got its own id
    assert client._server_id_of[logs_id] != client._server_id_of[account_id]


async def _fast_sleep(_delay: float) -> None:
    await asyncio.sleep(0)


async def _serve_drop_once(connections: list[int]) -> Any:
    async def handler(ws: Any) -> None:
        connections.append(1)
        is_first = len(connections) == 1
        async for raw in ws:
            request = json.loads(raw)
            sub_id = 5000 + len(connections)
            await ws.send(json.dumps({"jsonrpc": "2.0", "result": sub_id, "id": request["id"]}))
            slot = 1 if is_first else 2
            await ws.send(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "slotNotification",
                        "params": {
                            "result": {"slot": slot, "parent": slot - 1, "root": 0},
                            "subscription": sub_id,
                        },
                    }
                )
            )
            if is_first:
                await asyncio.sleep(0.05)
                return  # drop the connection right after the first notification

    return await websockets.serve(handler, "127.0.0.1", 0)


async def test_reconnect_resubscribes_the_whole_set_with_a_stable_logical_id() -> None:
    connections: list[int] = []
    server = await _serve_drop_once(connections)
    try:
        port = server.sockets[0].getsockname()[1]
        client = SolanaWsClient(
            url=f"ws://127.0.0.1:{port}",
            sleep=_fast_sleep,
            rand=lambda: 0.0,
            connect_timeout_s=5.0,
        )
        received: list[Notification] = []

        async def consume() -> None:
            async for notif in client.listen():
                received.append(notif)
                if len(received) >= 2:
                    return

        consumer = asyncio.create_task(consume())
        logical_id = await client.subscribe_slot()
        await asyncio.wait_for(consumer, timeout=10)
        await client.aclose()
    finally:
        server.close()
        await server.wait_closed()

    assert client.state.reconnects == 1
    assert len(connections) == 2
    assert [notif.subscription_id for notif in received] == [logical_id, logical_id]
    assert isinstance(received[0], SlotNotification) and received[0].slot == 1
    assert isinstance(received[1], SlotNotification) and received[1].slot == 2
