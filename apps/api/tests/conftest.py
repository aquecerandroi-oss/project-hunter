"""Shared fixtures for apps/api's test suite.

``api_settings``/``app``/``client`` use dummy (unreachable) Postgres/Redis
URLs: ``create_async_engine`` and ``redis.asyncio.from_url`` are both lazy
(no socket touched until a query/command runs), so the app boots and every
endpoint that doesn't need real IO (``/health``, security headers, errors,
CORS, request-id) is fully unit-testable without Docker. ``/ready`` and
rate-limit tests that need a real Redis are marked ``integration`` and use
the testcontainers fixtures below (following the pattern in
``packages/core/tests/conftest.py``).

``client``/``client_factory`` use ``httpx.AsyncClient`` over
``httpx.ASGITransport`` (the pattern already established in
``packages/core/tests/unit/test_runtime.py``) rather than
``starlette.testclient.TestClient``: the latter's ``httpx``-backed sync
wrapper resolves to a cascade of ``Unknown`` types under pyright strict.
``ASGITransport`` doesn't drive ASGI lifespan events on its own, so these
fixtures invoke ``app.router.lifespan_context`` explicitly — the WebSocket
handshake test is the one exception, since httpx has no WS support at all;
it builds its own ``TestClient`` locally.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

import httpx
import pytest
import pytest_asyncio
from pydantic import SecretStr

from hunter_api.app import create_app
from hunter_api.settings import ApiSettings
from hunter_core.logging import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

DUMMY_DATABASE_URL = "postgresql+asyncpg://hunter:hunter@localhost:59999/hunter_test_unreachable"
DUMMY_REDIS_URL = "redis://localhost:59998/0"


@pytest.fixture
def api_settings() -> ApiSettings:
    return ApiSettings(
        hunter_env="test",
        database_url=SecretStr(DUMMY_DATABASE_URL),
        redis_url=SecretStr(DUMMY_REDIS_URL),
        web_origin="http://localhost:3000",
        cors_allowed_origins=["http://localhost:3000"],
        rate_limit_per_minute=120,
    )


@pytest.fixture
def app(api_settings: ApiSettings) -> FastAPI:
    return create_app(api_settings)


@asynccontextmanager
async def _lifespan_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture
def client_factory() -> Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]]:
    """For tests that build their own ``ApiSettings``/``FastAPI`` app."""
    return _lifespan_client


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _lifespan_client(app) as test_client:
        yield test_client


# ---- Integration fixtures (Docker via testcontainers) ----


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()  # type: ignore[reportUnknownMemberType]
    except Exception as exc:
        logger.warning("docker_not_reachable_skipping_integration_tests", error=str(exc))
        return False
    return True


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_reachable()


@pytest.fixture(scope="session")
def postgres_container(docker_available: bool) -> Iterator[PostgresContainer]:
    if not docker_available:
        pytest.skip("Docker is not reachable; skipping Postgres-backed integration tests")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container(docker_available: bool) -> Iterator[RedisContainer]:
    if not docker_available:
        pytest.skip("Docker is not reachable; skipping Redis-backed integration tests")
    from testcontainers.community.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container
