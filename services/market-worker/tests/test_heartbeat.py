"""``hb:market:{exchange}``, ``rt:system`` and ``system_events`` — docs/plans/M1.md T1.3 item 5."""

from __future__ import annotations

import asyncio
from typing import Any, cast

import orjson
import pytest
from sqlalchemy import select

from hunter_core.db.models.system import SystemEvent
from hunter_core.db.session import role_session
from hunter_core.domain.types import utcnow
from hunter_core.observability import (
    market_dropped_events_total,
    market_system_event_record_failures_total,
)
from hunter_exchanges.base import ConnectionState
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


class _BrokenFactory:
    """A ``session_factory`` that always fails to open a transaction --
    stands in for a Postgres outage without needing a real broken database."""

    def __call__(self) -> Any:
        raise ConnectionError("db unreachable")


async def test_run_heartbeat_survives_a_broken_system_event_write(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HIGH-2 reproduction: with Postgres down, ``record_system_event`` raises
    on every attempt. The heartbeat loop must not die -- it keeps writing the
    Redis heartbeat (the actual liveness signal) and counts the failure
    instead of letting it escape into the caller's ``TaskGroup``."""
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    exchange_code = unique_code()
    adapter = FakeAdapter(code=exchange_code)
    adapter.set_connection_state("reconnecting")
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    state = HeartbeatState()
    runtime: Any = FakeRuntime(redis=redis_client)
    metric = cast(Any, market_system_event_record_failures_total.labels(event="ws_reconnected"))
    before = metric._value.get()  # pyright: ignore[reportPrivateUsage]

    task = asyncio.ensure_future(
        heartbeat.run_heartbeat(
            runtime,
            adapter,
            universe,
            state,
            _BrokenFactory(),  # type: ignore[arg-type]
        )
    )
    try:
        async with asyncio.timeout(5):
            await runtime.success.wait()
            runtime.success.clear()
            # A ws_state transition triggers a ``record_system_event`` call
            # that would raise ``ConnectionError`` against the broken factory.
            adapter.set_connection_state("connected")
            await runtime.success.wait()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # The Redis heartbeat kept being written despite every DB call failing.
    hb = await redis_client.hgetall(heartbeat.hb_key(exchange_code))
    assert hb[b"ws_state"] == b"connected"
    assert runtime.success_count > 0
    # The failed recording was counted, not silently lost.
    assert metric._value.get() == before + 1  # pyright: ignore[reportPrivateUsage]


async def test_run_heartbeat_writes_dropped_events_to_the_hash_and_the_counter(
    redis_client: Any, monkeypatch: pytest.MonkeyPatch, db_session_factory: Any
) -> None:
    """HIGH-1b: ``ConnectionState.dropped_events`` must reach an operator --
    the ``hb:market:{exchange}`` hash and the Prometheus counter."""
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    exchange_code = unique_code()
    connection = ConnectionState("public", "connected", ("btcusdt@aggTrade",), dropped_events=9)
    adapter = FakeAdapter(code=exchange_code)
    adapter.connection_states = lambda: {"public:0": connection}  # type: ignore[attr-defined]
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    state = HeartbeatState()
    runtime: Any = FakeRuntime(redis=redis_client)
    metric = cast(Any, market_dropped_events_total.labels(exchange=exchange_code))
    before = metric._value.get()  # pyright: ignore[reportPrivateUsage]

    task = asyncio.ensure_future(
        heartbeat.run_heartbeat(runtime, adapter, universe, state, db_session_factory)
    )
    try:
        async with asyncio.timeout(5):
            await runtime.success.wait()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    hb = await redis_client.hgetall(heartbeat.hb_key(exchange_code))
    assert hb[b"dropped_events"] == b"9"
    assert metric._value.get() == before + 9  # pyright: ignore[reportPrivateUsage]


class _BrokenRedis:
    """Stands in for the connection HIGH-4 fixes: with bounded socket
    timeouts, a Redis restart now raises (``TimeoutError``/``ConnectionError``)
    instead of the pre-fix behaviour of hanging the awaiting task forever."""

    async def hset(self, *args: Any, **kwargs: Any) -> None:
        raise TimeoutError("Timeout reading from socket")

    async def expire(self, *args: Any, **kwargs: Any) -> None:
        raise TimeoutError("Timeout reading from socket")

    async def publish(self, *args: Any, **kwargs: Any) -> None:
        raise TimeoutError("Timeout reading from socket")


async def test_run_heartbeat_surfaces_a_redis_error_instead_of_hanging(
    db_session_factory: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HIGH-4 consequence: a Redis error while writing the heartbeat (the
    liveness signal this loop exists to produce) must reach the caller --
    eventually ``forever()``/the ``TaskGroup`` in ``main.py`` -- so the
    process exits non-zero and ``restart: unless-stopped`` brings it back,
    instead of the pre-fix live zombie (0% CPU, ``/ready`` 503 forever, no
    log line ever again). Unlike a Postgres failure while recording a
    ``system_events`` row (HIGH-2, made survivable in
    :func:`safe_record_system_event` because losing an audit row is
    acceptable), losing the Redis heartbeat write itself means the loop has
    nothing left to do -- so it is made fatal, not survivable. The two rules
    do not contradict: they are deliberately different failure domains
    (observability record vs. the liveness signal itself), and the DB path
    is never involved in this scenario.

    A bounded ``asyncio.timeout`` proves this is a fast, real exception, not
    the pre-fix hang.
    """
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    exchange_code = unique_code()
    adapter = FakeAdapter(code=exchange_code)
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    state = HeartbeatState()
    runtime: Any = FakeRuntime(redis=_BrokenRedis())

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(5):
            await heartbeat.run_heartbeat(runtime, adapter, universe, state, db_session_factory)
