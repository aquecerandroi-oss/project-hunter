"""Testcontainers fixtures shared by packages/core's integration tests.

Skips cleanly, with the reason printed, when Docker is unreachable — a
sandbox or CI runner without a Docker daemon must not fail the whole suite
(M0 T03 brief: "Keep the integration module skipping cleanly ... with the
reason printed").
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

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


async def _create_app_roles(url: str, login_role: str) -> None:
    """Create the two roles ``hunter_core.db.session`` assumes into a transaction.

    A migrated database gets ``hunter_app``/``hunter_worker`` from
    ``infra/migrations/ddl/security.py``'s ``create_roles()`` (run once, in
    ``0001_initial_schema``). This session's ``postgres_container`` is shared
    by tests that exercise ``hunter_core.db.session`` directly against a bare,
    unmigrated database — no migration ever runs there. ``tenant_session``
    unconditionally issues ``SET LOCAL ROLE hunter_app`` before anything else
    (T06), so without this, that statement fails with "role does not exist"
    before RLS is ever reached, for every test that opens a tenant session
    here.

    Mirrors the real migration's statements: ``NOLOGIN`` roles (nothing ever
    connects as them directly), ``hunter_worker`` carrying ``BYPASSRLS``
    (workers scan every organization), both granted to the container's login
    role so it may ``SET ROLE`` into either one exactly as a deployed login
    role would, with baseline privileges on ``public`` for tests that create
    their own tables under these roles.
    """
    engine = create_async_engine(
        url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            for role, extra_attributes in (("hunter_app", ""), ("hunter_worker", " BYPASSRLS")):
                exists = await connection.scalar(
                    text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": role}
                )
                if not exists:
                    await connection.execute(text(f"CREATE ROLE {role} NOLOGIN{extra_attributes}"))
            await connection.execute(text(f'GRANT hunter_app, hunter_worker TO "{login_role}"'))
            await connection.execute(
                text("GRANT ALL ON SCHEMA public TO hunter_app, hunter_worker")
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def postgres_container(docker_available: bool) -> Iterator[PostgresContainer]:
    if not docker_available:
        pytest.skip("Docker is not reachable; skipping Postgres-backed integration tests")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        asyncio.run(_create_app_roles(container.get_connection_url(), container.username))
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
