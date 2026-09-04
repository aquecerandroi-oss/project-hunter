"""``/ready`` against real Postgres and Redis (testcontainers). Docker required."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr

from hunter_api.app import create_app
from hunter_api.settings import ApiSettings

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

pytestmark = pytest.mark.integration


@asynccontextmanager
async def _client_for(settings: ApiSettings) -> AsyncGenerator[httpx.AsyncClient, None]:
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


async def test_ready_returns_200_when_database_and_redis_are_up(
    postgres_container: PostgresContainer, redis_container: RedisContainer
) -> None:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    settings = ApiSettings(
        hunter_env="test",
        database_url=SecretStr(postgres_container.get_connection_url()),
        redis_url=SecretStr(f"redis://{host}:{port}/0"),
    )

    async with _client_for(settings) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"database": True, "redis": True}


async def test_ready_returns_503_when_redis_is_unreachable(
    postgres_container: PostgresContainer,
) -> None:
    settings = ApiSettings(
        hunter_env="test",
        database_url=SecretStr(postgres_container.get_connection_url()),
        redis_url=SecretStr("redis://localhost:1/0"),
    )

    async with _client_for(settings) as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["database"] is True
    assert body["redis"] is False
