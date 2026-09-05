"""Task exits, cancellation, readiness grace and connection-specific watchdogs."""

import asyncio
from typing import Any

import pytest

from hunter_market_worker.queues import PersistQueues
from hunter_market_worker.supervision import IngestionHealth, forever

from . import builders

pytestmark = pytest.mark.unit


async def test_return_is_fatal_and_exception_propagates() -> None:
    async def returned() -> None:
        return

    async def raised() -> None:
        raise ValueError("child failed")

    with pytest.raises(RuntimeError, match="task ingest exited unexpectedly"):
        await forever("ingest", returned())
    with pytest.raises(ExceptionGroup) as error:
        async with asyncio.TaskGroup() as group:
            group.create_task(forever("reader", raised()))
    assert isinstance(error.value.exceptions[0], ValueError)


async def test_shutdown_cancellation_is_normal() -> None:
    async def waiting() -> None:
        await asyncio.Event().wait()

    task = asyncio.create_task(forever("reader", waiting()))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_readiness_grace_is_monotonic_and_not_reset_by_flapping() -> None:
    now = [0.0]
    health = IngestionHealth(clock=lambda: now[0])
    assert not await health.ingestion()
    health.update("connected", active=True)
    health.data_event()
    assert await health.ingestion()
    now[0] = 1
    health.update("reconnecting", active=True)
    now[0] = 110
    assert await health.ingestion()
    health.update("connected", active=True)
    health.update("reconnecting", active=True)
    now[0] = 122
    assert not await health.ingestion()


async def test_queue_bounds_and_persistence_readiness() -> None:
    now = [0.0]
    queues = PersistQueues(max_items=1, max_bytes=2048, max_age=60, clock=lambda: now[0])
    queues.events.put_nowait(builders.candle("BTCUSDT"))
    queues.events.put_nowait(builders.liquidation("BTCUSDT"))
    assert queues.events.qsize() == 1
    assert queues.losses and queues.losses[0].item.kind == "liquidation"
    now[0] = 31
    assert not await queues.persistence()
    queues.events.get_nowait()
    queues.losses.clear()
    assert await queues.persistence()


async def test_watchdog_restarts_only_silent_connection() -> None:
    from hunter_market_worker.supervision import Watchdog

    now = [0.0]
    restarted: list[str] = []

    class Adapter:
        def connection_states(self) -> dict[str, dict[str, Any]]:
            return {
                "public": {"subscriptions": 2, "last_event_at": None},
                "market": {"subscriptions": 4, "last_event_at": now[0]},
            }

        async def restart_connection(self, name: str) -> None:
            restarted.append(name)

    async def warning(message: str) -> None:
        assert "public" in message

    watchdog = Watchdog(Adapter(), warning, clock=lambda: now[0])
    await watchdog.check(active=True)
    now[0] = 31
    await watchdog.check(active=True)
    assert restarted == ["public"]
    now[0] = 62
    await watchdog.check(active=True)
    now[0] = 93
    with pytest.raises(RuntimeError, match="public"):
        await watchdog.check(active=True)


async def test_main_supervises_coalescer_and_closes_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_core.settings import Settings
    from hunter_market_worker import main

    from .fakes import FakeAdapter

    adapter = FakeAdapter()

    async def waiting(*args: Any) -> None:
        await asyncio.Event().wait()

    async def broken(*args: Any) -> None:
        raise ValueError("coalescer failed")

    def build(*args: Any) -> FakeAdapter:
        return adapter

    def factory(*args: Any) -> object:
        return object()

    monkeypatch.setattr(main, "build_adapter", build)
    monkeypatch.setattr(main, "create_session_factory", factory)
    for name in (
        "run_universe",
        "run_ingest",
        "drain_loop",
        "snapshot_loop",
        "oi_poll_loop",
        "run_recovery",
        "run_heartbeat",
        "run_watchdog",
        "run_funding",
    ):
        monkeypatch.setattr(main, name, waiting)
    monkeypatch.setattr(main, "coalesce_loop", broken)

    class Runtime:
        settings = Settings()
        engine = redis = object()
        instance = "test"
        readiness_checks: list[Any] = []

    runtime: Any = Runtime()
    with pytest.raises(ExceptionGroup) as exc:
        await main.run_market(runtime)
    assert any(isinstance(child, ValueError) for child in exc.value.exceptions)
    assert adapter.closed and runtime.readiness_checks == []


async def test_readiness_false_with_zero_data_then_true_after_first_event() -> None:
    """H3: bootstrap must expose readiness false until the first accepted
    data event, even though ``connecting`` alone would previously fall
    through to the (bogus) 120s unhealthy-since grace."""
    now = [0.0]
    health = IngestionHealth(clock=lambda: now[0])
    health.update("connecting", active=True)
    now[0] = 1
    assert not await health.ingestion()
    health.data_event()
    assert await health.ingestion()


async def test_idle_and_connect_timeout() -> None:
    now = [0.0]
    health = IngestionHealth(clock=lambda: now[0])
    health.update("connecting", active=True)
    now[0] = 16
    assert not await health.ingestion()
    health.update("idle", active=False)
    assert await health.ingestion()


def test_snapshot_replacement_bytes_and_age_bounds() -> None:
    from hunter_market_worker.queues import Snapshot

    now = [0.0]
    queues = PersistQueues(max_items=4, max_bytes=1000, max_age=10, clock=lambda: now[0])
    queues.events.put_nowait(Snapshot("BTCUSDT", {"price": "1"}))
    queues.events.put_nowait(Snapshot("BTCUSDT", {"price": "2"}))
    assert queues.events.qsize() == 1 and queues.losses[0].reason == "replaced"
    queues.events.put_nowait(Snapshot("ETHUSDT", {"price": "x" * 2000}))
    assert queues.events.qsize() == 1 and queues.losses[-1].reason == "capacity"
    now[0] = 11
    queues.events.put_nowait(builders.candle("BTCUSDT"))
    assert queues.events.qsize() == 1 and queues.losses[-1].reason == "age"


async def test_watchdog_accepts_adapter_connection_state_dataclass() -> None:
    from hunter_exchanges.base import ConnectionState
    from hunter_market_worker.supervision import Watchdog

    now = [0.0]
    warnings: list[str] = []

    class Adapter:
        def connection_states(self) -> dict[str, ConnectionState]:
            return {
                "public:0": ConnectionState("public", "connected", ("btcusdt@depth20",)),
                "market:0": ConnectionState(
                    "market", "connected", ("btcusdt@aggTrade",), last_data_event_monotonic=now[0]
                ),
            }

    async def warn(message: str) -> None:
        warnings.append(message)

    watchdog = Watchdog(Adapter(), warn, clock=lambda: now[0])
    await watchdog.check(active=True)
    now[0] = 31
    await watchdog.check(active=True)
    assert watchdog.restart_stream and len(warnings) == 1 and "public:0" in warnings[0]


def test_heartbeat_counts_adapter_reconnects_and_actual_subscriptions() -> None:
    from hunter_exchanges.base import ConnectionState
    from hunter_market_worker.heartbeat import connection_summary

    state = ConnectionState("public", "connected", ("depth", "ticker"), reconnects=2)

    class Adapter:
        def connection_states(self) -> dict[str, ConnectionState]:
            return {"public:0": state}

    previous: dict[str, int] = {}
    adapter = Adapter()
    assert connection_summary(adapter, previous) == (2, 2)
    assert connection_summary(adapter, previous) == (2, 0)
    state.reconnects = 3
    assert connection_summary(adapter, previous) == (2, 1)
