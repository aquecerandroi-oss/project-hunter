"""T1.7 item 4: supervision, against real infra and the real
``hunter_core.runtime.WorkerRuntime``/``hunter_market_worker.main.run_market``
-- ``services/market-worker/tests/test_supervision.py`` already proves the
same rules unit-by-unit (monkeypatched tasks, a bare ``FakeAdapter``); this
file proves the wiring end-to-end: a REAL ``run_market`` TaskGroup, a REAL
``/ready`` HTTP endpoint served by ``WorkerRuntime``, and the T1.2 public
``FakeExchangeAdapter`` contract for the connection-watchdog scenario.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from hunter_core.runtime import WorkerRuntime
from hunter_exchanges.base import ConnectionState
from hunter_exchanges.testing.fake_adapter import FakeExchangeAdapter
from hunter_market_worker import main as market_main
from hunter_market_worker.persist import PersistQueues
from hunter_market_worker.supervision import IngestionHealth, Watchdog

from . import pipeline_builders as b

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from hunter_core.settings import Settings

pytestmark = pytest.mark.integration

EXCHANGE = b.EXCHANGE


# ---------------------------------------------------------------------------
# Child task dies -> the whole run_market TaskGroup dies (process exits
# non-zero: WorkerRuntime.run() re-raises whatever run_market raises, and
# `python -m hunter_market_worker`'s asyncio.run propagates that past main()).
# ---------------------------------------------------------------------------


async def test_a_child_task_dying_takes_down_run_market_and_closes_the_adapter(
    worker_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real ``WorkerRuntime`` (real engine, real Redis), real
    ``FakeExchangeAdapter``, real ``run_market`` -- only ``coalesce_loop`` is
    swapped for an immediate failure (the standard fault-injection point;
    ``create_redis``'s self-healing retry policy (``hunter_core/redis.py``
    HIGH-4) means merely closing the shared connection out from under a task
    reconnects silently instead of dying, so that is not a usable failure
    trigger here)."""
    symbol = "SUPERVUSDT"
    adapter = FakeExchangeAdapter(
        code=EXCHANGE, markets=[b.market(symbol, "SUPERV")], ticker=b.ticker(symbol, "1")
    )

    def _build_adapter(*_a: object, **_k: object) -> FakeExchangeAdapter:
        return adapter

    monkeypatch.setattr(market_main, "build_adapter", _build_adapter)

    async def broken_coalescer(*_args: object, **_kwargs: object) -> None:
        raise ValueError("coalescer failed")

    monkeypatch.setattr(market_main, "coalesce_loop", broken_coalescer)

    runtime = WorkerRuntime("market", worker_settings, instance=EXCHANGE)
    try:
        with pytest.raises(ExceptionGroup) as exc_info:
            await market_main.run_market(runtime)
        assert any(isinstance(child, ValueError) for child in exc_info.value.exceptions)
    finally:
        await runtime.redis.aclose()
        await runtime.engine.dispose()

    assert adapter.closed  # `finally: await adapter.aclose()` still ran
    assert runtime.readiness_checks == []  # registered checks were torn down too


# ---------------------------------------------------------------------------
# Per-connection silence -> restart of THAT connection (not the others, not
# fatal until the 3rd consecutive restart makes no progress).
# ---------------------------------------------------------------------------


async def test_watchdog_restarts_only_the_silent_connection_via_the_real_adapter_contract() -> None:
    now = [0.0]
    clock = lambda: now[0]  # noqa: E731 -- short, test-local, matches the module's own style

    adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        per_connection_states={
            "public:0": ConnectionState("public", "connected", ("btcusdt@depth20",)),
            "market:0": ConnectionState(
                "market", "connected", ("btcusdt@aggTrade",), last_data_event_monotonic=0.0
            ),
        },
    )

    warnings: list[str] = []

    async def warning(message: str) -> None:
        warnings.append(message)

    watchdog = Watchdog(adapter, warning, clock=clock)
    await watchdog.check(active=True)
    now[0] = 31  # "public" never had a data event -> silent past the 30s threshold
    # "market:0" keeps making real progress between checks (a fresh token
    # each time, exactly what a live connection produces) -- only "public:0"
    # is frozen at its original token.
    adapter._per_connection_states["market:0"] = ConnectionState(  # pyright: ignore[reportPrivateUsage]
        "market", "connected", ("btcusdt@aggTrade",), last_data_event_monotonic=now[0]
    )
    await watchdog.check(active=True)

    assert adapter.restarted_connections == ["public:0"]
    assert len(warnings) == 1 and "public:0" in warnings[0]
    # "market:0" made progress (its own last_data_event_monotonic), so it was
    # never touched -- silence is per-connection, not whole-adapter.
    assert "market:0" not in adapter.restarted_connections


async def test_watchdog_escalates_to_fatal_after_three_restarts_with_no_progress() -> None:
    now = [0.0]
    adapter = FakeExchangeAdapter(
        code=EXCHANGE,
        per_connection_states={"public:0": ConnectionState("public", "connected", ("x",))},
    )

    async def warning(_message: str) -> None:
        return None

    watchdog = Watchdog(adapter, warning, clock=lambda: now[0])
    await watchdog.check(active=True)
    now[0] = 31
    await watchdog.check(active=True)
    now[0] = 62
    await watchdog.check(active=True)
    now[0] = 93
    with pytest.raises(RuntimeError, match="public:0"):
        await watchdog.check(active=True)
    assert adapter.restarted_connections == ["public:0", "public:0", "public:0"]


# ---------------------------------------------------------------------------
# Readiness: initializing false; connecting tolerated <= 120s monotonic then
# 503; persistence stuck (no flush for 30s) -> 503. Through the REAL /ready
# HTTP endpoint WorkerRuntime serves, not a bare unit call.
# ---------------------------------------------------------------------------


@pytest.fixture
async def ready_runtime(worker_settings: Settings) -> AsyncIterator[WorkerRuntime]:
    runtime = WorkerRuntime("market", worker_settings, instance="ready-it")
    try:
        yield runtime
    finally:
        await runtime.redis.aclose()
        await runtime.engine.dispose()


async def _ready(runtime: WorkerRuntime) -> httpx.Response:
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ready.test") as client:
        return await client.get("/ready")


async def test_initializing_is_not_ready(ready_runtime: WorkerRuntime) -> None:
    now = [0.0]
    health = IngestionHealth(clock=lambda: now[0])
    ready_runtime.readiness_checks.append(health.ingestion)

    response = await _ready(ready_runtime)
    assert response.status_code == 503
    assert response.json()["ingestion"] is False


async def test_connecting_is_tolerated_for_120_monotonic_seconds_then_503(
    ready_runtime: WorkerRuntime,
) -> None:
    now = [0.0]
    health = IngestionHealth(clock=lambda: now[0])
    ready_runtime.readiness_checks.append(health.ingestion)

    health.update("connected", active=True)
    health.data_event()  # bootstrap: at least one accepted event ever
    health.update("reconnecting", active=True)  # now genuinely connecting/unhealthy
    now[0] = 1

    response = await _ready(ready_runtime)
    assert response.status_code == 200
    assert response.json()["ingestion"] is True  # inside the 120s grace

    now[0] = 121
    response_after = await _ready(ready_runtime)
    assert response_after.status_code == 503
    assert response_after.json()["ingestion"] is False


async def test_persistence_stuck_without_a_flush_for_30s_is_503(
    ready_runtime: WorkerRuntime,
) -> None:
    now = [0.0]
    queues = PersistQueues(clock=lambda: now[0])
    ready_runtime.readiness_checks.append(queues.persistence)
    queues.events.put_nowait(b.candle("STUCKUSDT"))  # something pending, never flushed

    response = await _ready(ready_runtime)
    assert response.status_code == 200  # pending but young
    assert response.json()["persistence"] is True

    now[0] = 31
    response_after = await _ready(ready_runtime)
    assert response_after.status_code == 503
    assert response_after.json()["persistence"] is False
