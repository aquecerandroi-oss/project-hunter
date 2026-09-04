"""Redis sliding-window rate limiting: 429 past the limit, exempt paths,
fail-open when Redis errors.

Uses tiny in-memory fakes for the handful of Redis commands the middleware
calls (no ``fakeredis`` dependency declared for this package) rather than a
real Redis — this suite never needs Docker.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import pytest

from hunter_api.app import create_app
from hunter_api.middleware.rate_limit import EXEMPT_PATHS

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    import httpx
    from fastapi import FastAPI

    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.unit


class _FakeRedis:
    """In-memory sorted sets — just enough of the Redis API for the sliding window."""

    def __init__(self) -> None:
        self._sets: dict[str, dict[str, float]] = defaultdict(dict)

    async def zremrangebyscore(self, name: str, min_: float, max_: float) -> None:
        self._sets[name] = {
            member: score
            for member, score in self._sets[name].items()
            if not (min_ <= score <= max_)
        }

    async def zadd(self, name: str, mapping: dict[str, float]) -> None:
        self._sets[name].update(mapping)

    async def zcard(self, name: str) -> int:
        return len(self._sets[name])

    async def expire(self, name: str, seconds: int) -> bool:
        return True


class _BrokenRedis:
    """Every command raises — simulates Redis being unreachable."""

    async def zremrangebyscore(self, *args: object, **kwargs: object) -> None:
        raise ConnectionError("redis unreachable")

    async def zadd(self, *args: object, **kwargs: object) -> None:
        raise ConnectionError("redis unreachable")

    async def zcard(self, *args: object, **kwargs: object) -> int:
        raise ConnectionError("redis unreachable")

    async def expire(self, *args: object, **kwargs: object) -> bool:
        raise ConnectionError("redis unreachable")


def test_ready_and_metrics_are_declared_exempt() -> None:
    assert {"/health", "/ready", "/metrics"} == set(EXEMPT_PATHS)


async def test_returns_429_after_the_configured_limit(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 3})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        for _ in range(3):
            assert (await test_client.get("/api/v1/system/info")).status_code == 200
        response = await test_client.get("/api/v1/system/info")

    assert response.status_code == 429
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "Retry-After" in response.headers


async def test_exempts_health_and_metrics_from_the_limit(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 1})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _FakeRedis()
        assert (await test_client.get("/health")).status_code == 200
        assert (await test_client.get("/health")).status_code == 200
        # Starlette's Mount 307-redirects "/metrics" -> "/metrics/"; the
        # exemption is checked against the pre-redirect path either way.
        assert (await test_client.get("/metrics/")).status_code == 200


async def test_fails_open_when_redis_is_unavailable(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    limited = api_settings.model_copy(update={"rate_limit_per_minute": 1})
    app = create_app(limited)

    async with client_factory(app) as test_client:
        app.state.redis = _BrokenRedis()
        for _ in range(5):
            assert (await test_client.get("/api/v1/system/info")).status_code == 200
