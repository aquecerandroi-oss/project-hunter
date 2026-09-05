"""``hb:market:{exchange}``, ``rt:system`` and ``system_events`` — docs/plans/M1.md T1.3 item 5."""

from __future__ import annotations

import asyncio
from typing import Any

import orjson
import pytest
from sqlalchemy import select

from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_market_worker import heartbeat
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.universe import MonitoredUniverse

from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


async def test_write_hash_has_every_documented_field_and_ttl(redis_client: Any) -> None:
    exchange_code = unique_code()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT", "ETHUSDT"])
    state = HeartbeatState(last_event_at=utcnow(), reconnects=3, open_gaps=1)

    await heartbeat._write_hash(  # pyright: ignore[reportPrivateUsage]
        redis_client, exchange_code, universe, state, "connected", utcnow()
    )

    key = heartbeat.hb_key(exchange_code)
    raw = await redis_client.hgetall(key)
    fields = {k.decode(): v.decode() for k, v in raw.items()}
    for name in (
        "last_event_at",
        "ws_state",
        "subscriptions",
        "reconnects",
        "markets_monitored",
        "open_gaps",
        "ts",
    ):
        assert name in fields
    assert fields["ws_state"] == "connected"
    assert fields["markets_monitored"] == "2"
    assert fields["reconnects"] == "3"
    assert fields["open_gaps"] == "1"
    ttl = await redis_client.ttl(key)
    assert 0 < ttl <= heartbeat.HB_TTL_S


async def test_publish_status_shape_on_rt_system(redis_client: Any) -> None:
    exchange_code = unique_code()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    state = HeartbeatState(open_gaps=2)

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("rt:system")
    try:
        await heartbeat._publish_status(  # pyright: ignore[reportPrivateUsage]
            redis_client, exchange_code, universe, state, "reconnecting", utcnow()
        )
        message = None
        for _ in range(10):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if message is not None:
                break
        assert message is not None
        payload = orjson.loads(message["data"])
        assert payload["type"] == "market_status"
        assert payload["exchange"] == exchange_code
        assert payload["ws_state"] == "reconnecting"
        assert payload["markets_monitored"] == 1
        assert payload["open_gaps"] == 2
    finally:
        await pubsub.aclose()


async def testrecord_system_event_inserts_a_row(db_session_factory: Any) -> None:
    from hunter_core.domain.enums import RiskEventSeverity

    await heartbeat.record_system_event(
        db_session_factory, "adapter_error", "boom", RiskEventSeverity.WARNING
    )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        row = await session.scalar(
            select(SystemEvent).where(
                SystemEvent.event == "adapter_error", SystemEvent.message == "boom"
            )
        )
    assert row is not None
    assert row.level == RiskEventSeverity.WARNING
    assert row.component == "market-worker"


async def test_run_heartbeat_logs_reconnect_and_marks_success(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    exchange_code = unique_code()
    adapter = FakeAdapter(code=exchange_code)
    adapter.set_connection_state("reconnecting")
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    state = HeartbeatState()
    runtime: Any = FakeRuntime(redis=redis_client)
    started_at = utcnow()

    task = asyncio.ensure_future(
        heartbeat.run_heartbeat(runtime, adapter, universe, state, db_session_factory)
    )
    try:
        async with asyncio.timeout(5):
            await runtime.success.wait()
            runtime.success.clear()
            adapter.set_connection_state("connected")
            await runtime.success.wait()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    hb = await redis_client.hgetall(heartbeat.hb_key(exchange_code))
    assert hb[b"ws_state"] == b"connected"
    assert runtime.success_count > 0

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        events = (
            await session.scalars(
                select(SystemEvent).where(
                    SystemEvent.created_at >= started_at,
                    SystemEvent.event == "ws_reconnected",
                    SystemEvent.message == "reconnecting -> connected",
                )
            )
        ).all()
    assert events
