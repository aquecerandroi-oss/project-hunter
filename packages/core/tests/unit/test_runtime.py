"""Unit tests for hunter_core.runtime.WorkerRuntime (fakes only, no real IO)."""

import asyncio
import signal
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from hunter_core.runtime import RoleRegistry, WorkerRuntime
from hunter_core.settings import Settings

pytestmark = pytest.mark.unit


class _FakeEngine:
    def __init__(self, healthy: bool) -> None:
        self.healthy = healthy


class _FakeRedis:
    def __init__(self, healthy: bool) -> None:
        self.healthy = healthy
        self.hset_calls: list[tuple[str, dict[str, Any]]] = []
        self.expire_calls: list[tuple[str, int]] = []

    async def ping(self) -> bool:
        if not self.healthy:
            raise ConnectionError("down")
        return True

    async def hset(self, key: str, mapping: dict[str, Any]) -> None:
        self.hset_calls.append((key, mapping))

    async def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))


@pytest.fixture(autouse=True)
def _patch_check_database(  # pyright: ignore[reportUnusedFunction] - pytest autouse fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_check_database(engine: Any) -> bool:
        return bool(engine.healthy)

    monkeypatch.setattr("hunter_core.runtime.check_database", fake_check_database)


def _make_runtime(*, db_ok: bool = True, redis_ok: bool = True) -> WorkerRuntime:
    return WorkerRuntime(
        "scanner",
        Settings(),
        instance="host-1:123",
        engine=_FakeEngine(db_ok),  # type: ignore[arg-type]
        redis_client=_FakeRedis(redis_ok),  # type: ignore[arg-type]
    )


def test_mark_success_and_mark_error_update_state() -> None:
    runtime = _make_runtime()
    assert runtime.last_success is None
    runtime.mark_success()
    assert runtime.last_success is not None
    runtime.mark_error()
    assert runtime.error_count == 1


async def test_write_heartbeat_sets_hash_and_ttl() -> None:
    runtime = _make_runtime()
    runtime.mark_success()

    await runtime.write_heartbeat()

    fake_redis: _FakeRedis = runtime.redis  # type: ignore[assignment]
    assert len(fake_redis.hset_calls) == 1
    key, mapping = fake_redis.hset_calls[0]
    assert key == "hb:scanner:host-1:123"
    assert set(mapping) == {"ts", "last_success", "errors", "version"}
    assert mapping["errors"] == "0"
    assert fake_redis.expire_calls == [(key, 30)]


async def test_health_always_returns_200() -> None:
    runtime = _make_runtime(db_ok=False, redis_ok=False)
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200


async def test_ready_returns_200_when_both_healthy() -> None:
    runtime = _make_runtime(db_ok=True, redis_ok=True)
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"database": True, "redis": True}


async def test_ready_returns_503_when_redis_unhealthy() -> None:
    runtime = _make_runtime(db_ok=True, redis_ok=False)
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"database": True, "redis": False}


async def test_metrics_endpoint_is_mounted() -> None:
    runtime = _make_runtime()
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics/")
    assert response.status_code == 200
    assert b"hunter_" in response.content or response.content == b""


def test_role_registry_starts_empty_for_t03() -> None:
    assert RoleRegistry == {}


async def test_ready_returns_503_when_database_unhealthy() -> None:
    """Symmetric to test_ready_returns_503_when_redis_unhealthy above, with
    the failure on the other dependency.

    Mutation that breaks this: change the `/ready` status_code expression in
    runtime.py from `200 if db_ok and redis_ok else 503` to
    `200 if redis_ok else 503` (dropping `db_ok`) — this test would then see
    a 200 instead of a 503.
    """
    runtime = _make_runtime(db_ok=False, redis_ok=True)
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    # the body names which dependency failed, not just an opaque 503
    assert body == {"database": False, "redis": True}


def _patch_fake_uvicorn_server(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Stub ``uvicorn.Server`` so ``run()`` never binds a real socket — this
    module is marked ``unit: fast, no IO``. Returns the list of fake server
    instances ``run()`` constructs (one per call).
    """
    instances: list[Any] = []

    class _FakeServer:
        def __init__(self, config: object) -> None:
            self.config = config
            self._exit_event = asyncio.Event()
            instances.append(self)

        @property
        def should_exit(self) -> bool:
            return self._exit_event.is_set()

        @should_exit.setter
        def should_exit(self, value: bool) -> None:
            if value:
                self._exit_event.set()
            else:
                self._exit_event.clear()

        async def serve(self) -> None:
            await self._exit_event.wait()

    monkeypatch.setattr("hunter_core.runtime.uvicorn.Server", _FakeServer)
    return instances


def _patch_heartbeat_cancellation_spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Wrap ``WorkerRuntime._heartbeat_loop`` so ``result["cancelled"]`` proves
    the loop actually received (and re-raised) ``CancelledError`` — i.e. that
    ``run()`` awaited the cancelled heartbeat task instead of leaving it
    pending.
    """
    result = {"cancelled": False}
    original = WorkerRuntime._heartbeat_loop  # pyright: ignore[reportPrivateUsage]

    async def spy(self: WorkerRuntime) -> None:
        try:
            await original(self)
        except asyncio.CancelledError:
            result["cancelled"] = True
            raise

    monkeypatch.setattr(WorkerRuntime, "_heartbeat_loop", spy)
    return result


async def test_run_cancels_main_awaits_heartbeat_and_stops_health_server_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercises WorkerRuntime.run()'s cleanup ordering on shutdown.

    ``run()`` reacts to SIGTERM/SIGINT by registering
    ``loop.add_signal_handler(sig, stop_event.set)``. Rather than sending a
    real OS signal (unreliable here: ``add_signal_handler`` raises
    ``NotImplementedError`` on Windows and ``run()`` silently swallows that),
    this test patches the *running loop's* ``add_signal_handler`` to capture
    the callback ``run()`` registers, then calls it directly — which sets the
    real ``stop_event`` and drives exactly the same code path a delivered
    SIGTERM would.

    Mutation that breaks this: in run()'s `finally` block, drop the
    `with contextlib.suppress(asyncio.CancelledError): await heartbeat_task`
    line (cancel the heartbeat task but never await it) — `heartbeat.cancelled`
    would still read `False` when this test's assertions run.
    """
    server_instances = _patch_fake_uvicorn_server(monkeypatch)
    heartbeat = _patch_heartbeat_cancellation_spy(monkeypatch)

    signal_handlers: dict[int, Callable[[], None]] = {}

    def fake_add_signal_handler(sig: int, cb: Callable[[], None]) -> None:
        signal_handlers[sig] = cb

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", fake_add_signal_handler, raising=False)

    runtime = _make_runtime()
    hang_forever = asyncio.Event()
    main_cancelled = False

    async def main(_rt: WorkerRuntime) -> None:
        nonlocal main_cancelled
        try:
            await hang_forever.wait()
        except asyncio.CancelledError:
            main_cancelled = True
            raise

    run_task = asyncio.ensure_future(runtime.run(main))
    for _ in range(10):
        await asyncio.sleep(0)
    assert signal.SIGTERM in signal_handlers, "run() must register a SIGTERM handler"

    signal_handlers[signal.SIGTERM]()  # exactly what a delivered SIGTERM does: stop_event.set()

    await asyncio.wait_for(run_task, timeout=2)

    assert run_task.done()
    assert not run_task.cancelled()
    assert main_cancelled is True
    assert heartbeat["cancelled"] is True
    assert server_instances[0].should_exit is True


async def test_run_awaits_heartbeat_and_stops_health_server_when_main_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same cleanup guarantee as the shutdown-signal test above, but with no
    signal at all: main() fails on its own, and the original exception must
    still propagate out of run() unchanged.

    Mutation that breaks this: drop `server.should_exit = True` from run()'s
    `finally` block — `server_instances[0].should_exit` would stay `False`.
    """
    server_instances = _patch_fake_uvicorn_server(monkeypatch)
    heartbeat = _patch_heartbeat_cancellation_spy(monkeypatch)

    runtime = _make_runtime()

    class _Boom(Exception):
        pass

    async def main(_rt: WorkerRuntime) -> None:
        raise _Boom("main blew up")

    with pytest.raises(_Boom, match="main blew up"):
        await runtime.run(main)

    assert heartbeat["cancelled"] is True
    assert server_instances[0].should_exit is True
