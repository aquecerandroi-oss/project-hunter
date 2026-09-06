"""Testcontainers plumbing for the partition-job integration test.

Mirrors ``services/market-worker/tests/conftest.py`` and
``packages/core/tests/integration/conftest.py``: one session-scoped Postgres 16
container, a database of its own, and ``alembic upgrade head`` applied to it.
Skips cleanly (reason printed) when Docker is unreachable.

The two application roles are created before the migration runs. ``0001`` can
create them itself, but only where the migrating role may — creating them here
is what the deployed clusters do and keeps the migration on its normal path.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from collections.abc import Iterator

    from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = REPO_ROOT / "infra" / "scripts"


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()  # type: ignore[reportUnknownMemberType]
    except Exception as exc:  # any failure at all means "no Docker here"
        print(f"docker unreachable: {exc}")
        return False
    return True


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


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    if not _docker_reachable():
        pytest.skip("Docker is not reachable; skipping Postgres-backed integration tests")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        asyncio.run(_create_app_roles(container.get_connection_url(), container.username))
        yield container


@pytest.fixture(scope="session")
def migrated_db_url(postgres_container: PostgresContainer) -> Iterator[str]:
    """A clean database with every revision applied — nothing else has run on it."""
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_partitions")
    )
    command.upgrade(_alembic_config(url), "head")
    yield url
