"""Unit tests for hunter_core.runtime.WorkerRuntime (fakes only, no real IO)."""

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
