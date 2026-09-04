"""``ConnectionManager`` subscribe/unsubscribe and fan-out."""

from __future__ import annotations

import pytest

from hunter_api.realtime.ws_manager import ConnectionManager

pytestmark = pytest.mark.unit


class _FakeConnection:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(data)


async def test_broadcast_reaches_every_subscriber_of_a_channel() -> None:
    manager = ConnectionManager()
    a, b, other = _FakeConnection(), _FakeConnection(), _FakeConnection()
    manager.subscribe(a, "rt:radar")
    manager.subscribe(b, "rt:radar")
    manager.subscribe(other, "rt:system")

    await manager.broadcast("rt:radar", "update")

    assert a.sent == ["update"]
    assert b.sent == ["update"]
    assert other.sent == []


async def test_unsubscribe_stops_delivery_and_cleans_up_empty_channels() -> None:
    manager = ConnectionManager()
    conn = _FakeConnection()
    manager.subscribe(conn, "rt:radar")

    manager.unsubscribe(conn, "rt:radar")
    await manager.broadcast("rt:radar", "update")

    assert conn.sent == []
    assert "rt:radar" not in manager.channels()


async def test_unsubscribe_all_removes_every_subscription() -> None:
    manager = ConnectionManager()
    conn = _FakeConnection()
    manager.subscribe(conn, "rt:radar")
    manager.subscribe(conn, "rt:system")

    manager.unsubscribe_all(conn)

    assert manager.channels() == []


def test_subscriber_count_reflects_active_subscriptions() -> None:
    manager = ConnectionManager()
    a, b = _FakeConnection(), _FakeConnection()

    assert manager.subscriber_count("rt:radar") == 0
    manager.subscribe(a, "rt:radar")
    manager.subscribe(b, "rt:radar")
    assert manager.subscriber_count("rt:radar") == 2
