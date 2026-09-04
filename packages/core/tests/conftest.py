"""Testcontainers fixtures shared by packages/core's integration tests.

Skips cleanly, with the reason printed, when Docker is unreachable — a
sandbox or CI runner without a Docker daemon must not fail the whole suite
(M0 T03 brief: "Keep the integration module skipping cleanly ... with the
reason printed").
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()  # type: ignore[reportUnknownMemberType]
    except Exception as exc:
        print(f"Docker is not reachable, skipping integration tests: {exc}")
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


@pytest_asyncio.fixture
async def db_engine(postgres_container: PostgresContainer) -> AsyncIterator[AsyncEngine]:
    from pydantic import SecretStr

    from hunter_core.db.session import create_engine
    from hunter_core.settings import Settings

    settings = Settings(database_url=SecretStr(postgres_container.get_connection_url()))
    engine = create_engine(settings)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncIterator[redis_asyncio.Redis]:
    from pydantic import SecretStr

    from hunter_core.redis import create_redis
    from hunter_core.settings import Settings

    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    settings = Settings(redis_url=SecretStr(f"redis://{host}:{port}/0"))
    client = create_redis(settings)
    try:
        yield client
    finally:
        await client.aclose()
