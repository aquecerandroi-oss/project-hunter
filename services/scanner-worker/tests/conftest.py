"""Testcontainers fixtures for market-worker tests — mirrors
``packages/core/tests/conftest.py`` and ``packages/core/tests/integration/conftest.py``.

Skips cleanly (reason printed) when Docker is unreachable.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()  # type: ignore[reportUnknownMemberType]
    except Exception as exc:
        from hunter_core.logging import get_logger

        get_logger(__name__).warning("docker_unreachable", error=str(exc))
        return False
    return True


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_reachable()


async def _create_app_roles(url: str, login_role: str) -> None:
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


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


async def _create_database(admin_url: str, name: str) -> str:
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()
    return admin_url.rsplit("/", 1)[0] + "/" + name


@pytest.fixture(scope="session")
def migrated_db_url(postgres_container: PostgresContainer) -> Iterator[str]:
    """A database in the shared container with ``0001_initial_schema`` applied."""
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_scanner_worker")
    )
    command.upgrade(_alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def db_engine(migrated_db_url: str) -> AsyncIterator[AsyncEngine]:
    """The engine itself — the baseline cache and the hourly refresh take an
    ``AsyncConnection``, not a session, because ``SqlBaselineStore`` does."""
    from pydantic import SecretStr

    from hunter_core.db.session import create_engine
    from hunter_core.settings import Settings

    engine = create_engine(Settings(database_url=SecretStr(migrated_db_url)))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(
    db_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    from hunter_core.db.session import create_session_factory

    yield create_session_factory(db_engine)


@pytest_asyncio.fixture
async def redis_client(redis_container: RedisContainer) -> AsyncIterator[redis_asyncio.Redis]:
    from pydantic import SecretStr

    from hunter_core.redis import create_redis
    from hunter_core.settings import Settings

    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    settings = Settings(
        redis_url=SecretStr(f"redis://{host}:{port}/0?socket_timeout=15&socket_connect_timeout=15")
    )
    client = create_redis(settings)
    try:
        await cast(Any, client).flushdb()
        yield client
    finally:
        await client.aclose()
