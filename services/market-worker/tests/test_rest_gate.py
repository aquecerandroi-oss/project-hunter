"""The REST admission gate as the worker reports it (T2.9).

When the shared rate-limit coordination (Redis) is unreachable, the exchange
adapter suspends REST admissions instead of falling back to a per-process
budget — see ``packages/exchange-adapters/hunter_exchanges/rate_limit_suspension.py``.
For the worker that is a **degradation**: the WebSocket keeps ingesting, so
readiness stays green and the state is published as ``rest_gate`` in
``hb:market:{exchange}`` and on ``rt:system``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import orjson
import pytest

from hunter_core.domain.types import utcnow
from hunter_market_worker import heartbeat
from hunter_market_worker.heartbeat import HeartbeatState
from hunter_market_worker.supervision import rest_gate_status
from hunter_market_worker.universe import MonitoredUniverse

from .fakes import FakeAdapter, FakeRuntime
from .universe_test_helpers import unique_code

pytestmark = pytest.mark.integration


class _GatedAdapter(FakeAdapter):
    """A ``FakeAdapter`` that also reports the REST admission gate."""

    def __init__(self, code: str, status: str = "ok") -> None:
        super().__init__(code=code)
        self.gate_status = status

    def rest_gate_status(self) -> str:
        return self.gate_status


@pytest.mark.unit
def test_an_adapter_without_the_method_is_reported_as_admitting() -> None:
    """Every other ``FakeAdapter`` in this suite predates the method, and so
    does any adapter written before T2.9."""
    assert rest_gate_status(FakeAdapter(code="fake")) == "ok"
    assert rest_gate_status(_GatedAdapter("fake", "suspended")) == "suspended"


async def test_a_suspended_rest_gate_is_reported_without_failing_the_worker(
    db_session_factory: Any, redis_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    exchange_code = unique_code()
    adapter = _GatedAdapter(exchange_code, "suspended")
    adapter.set_connection_state("connected")
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    runtime: Any = FakeRuntime(redis=redis_client)

    task = asyncio.ensure_future(
        heartbeat.run_heartbeat(runtime, adapter, universe, HeartbeatState(), db_session_factory)
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
    assert hb[b"rest_gate"] == b"suspended"
    assert hb[b"ws_state"] == b"connected", "ingestion is unaffected"
    assert runtime.error_count == 0, "a suspended REST gate is not a worker error"


async def test_an_adapter_with_no_rest_gate_reports_ok(redis_client: Any) -> None:
    exchange_code = unique_code()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])

    await heartbeat._write_hash(  # pyright: ignore[reportPrivateUsage]
        redis_client, exchange_code, universe, HeartbeatState(), "connected", utcnow()
    )

    fields = await redis_client.hgetall(heartbeat.hb_key(exchange_code))
    assert fields[b"rest_gate"] == b"ok"


async def test_rt_system_carries_the_gate_state_too(redis_client: Any) -> None:
    """The live-status widget reads ``rt:system``, not the hash."""
    exchange_code = unique_code()
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])

    pubsub = redis_client.pubsub()
    await pubsub.subscribe("rt:system")
    try:
        await heartbeat._publish_status(  # pyright: ignore[reportPrivateUsage]
            redis_client,
            exchange_code,
            universe,
            HeartbeatState(),
            "connected",
            utcnow(),
            rest_gate="suspended",
        )
        message = None
        for _ in range(10):
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if message is not None:
                break
        assert message is not None
        payload = orjson.loads(message["data"])
        assert payload["rest_gate"] == "suspended"
    finally:
        await pubsub.aclose()


@pytest.mark.unit
async def test_run_market_publishes_the_gate_on_ready_without_failing_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``/ready`` answers 200 with ``rest_gate: suspended``.

    Readiness is about "should traffic reach me"; a suspended REST gate is a
    degradation of one path while the WebSocket keeps ingesting, so it is
    published as a status detail (``WorkerRuntime.status_details``) and never
    as a check. Registered for the lifetime of ``run_market`` only.
    """
    from hunter_core.settings import Settings
    from hunter_market_worker import main

    adapter = _GatedAdapter("fake", "suspended")
    seen: list[str] = []

    async def waiting(*_args: Any) -> None:
        await asyncio.Event().wait()

    async def probe(*_args: Any) -> None:
        seen.append(runtime.status_details["rest_gate"]())
        raise ValueError("stop the worker")

    def build(*_args: Any) -> _GatedAdapter:
        return adapter

    def factory(*_args: Any) -> object:
        return object()

    monkeypatch.setattr(main, "build_adapter", build)
    monkeypatch.setattr(main, "create_session_factory", factory)
    for name in (
        "run_universe",
        "run_ingest",
        "drain_loop",
        "run_outbox",
        "snapshot_loop",
        "oi_poll_loop",
        "run_recovery",
        "run_heartbeat",
        "run_watchdog",
        "run_funding",
    ):
        monkeypatch.setattr(main, name, waiting)
    monkeypatch.setattr(main, "coalesce_loop", probe)

    class _Runtime:
        settings = Settings()
        engine = redis = object()
        instance = "test"
        readiness_checks: list[Any] = []
        status_details: dict[str, Any] = {}

    runtime: Any = _Runtime()
    with pytest.raises(ExceptionGroup):
        await main.run_market(runtime)

    assert seen == ["suspended"], "the gate state reaches /ready as a string, not a verdict"
    assert runtime.status_details == {}, "and is unregistered with the rest of the worker"


class _DeadRedis:
    """Redis is gone — every write raises, which is the whole point."""

    def __init__(self) -> None:
        self.attempts = 0

    async def hset(self, *_args: Any, **_kwargs: Any) -> object:
        self.attempts += 1
        raise ConnectionError("redis is down")

    async def expire(self, *_args: Any, **_kwargs: Any) -> object:
        raise ConnectionError("redis is down")

    async def publish(self, *_args: Any, **_kwargs: Any) -> object:
        raise ConnectionError("redis is down")


@pytest.mark.unit
async def test_the_heartbeat_survives_redis_being_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Astra, T2.9 round 3: suspending REST admissions only keeps ingestion
    alive if nothing *else* dies of the same outage.

    ``run_heartbeat`` is a ``forever()`` task in the market TaskGroup, so an
    exception out of its Redis writes cancels every sibling — including the
    WebSocket ingestion the fail-closed policy exists to protect. The outage
    has to degrade this loop to "no heartbeat published", exactly like a
    Postgres outage already degrades it to "no system_events written".
    """
    monkeypatch.setattr(heartbeat, "HEARTBEAT_INTERVAL_S", 0.01)
    redis = _DeadRedis()
    adapter = _GatedAdapter("fake", "suspended")
    adapter.set_connection_state("connected")
    universe = MonitoredUniverse()
    universe.set(["BTCUSDT"])
    runtime: Any = FakeRuntime(redis=redis)

    no_database: Any = None  # nothing in this test reaches system_events
    task = asyncio.ensure_future(
        heartbeat.run_heartbeat(runtime, adapter, universe, HeartbeatState(), no_database)
    )
    try:
        # Polled, not slept: each failed tick renders a traceback, which is
        # far slower than HEARTBEAT_INTERVAL_S and made a fixed sleep flaky.
        async with asyncio.timeout(5):
            while redis.attempts < 2:
                assert not task.done(), "a Redis outage may not take the whole TaskGroup down"
                await asyncio.sleep(0.01)
        assert not task.done(), "it keeps trying, so it recovers on its own"
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
