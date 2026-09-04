"""Shared plumbing for the T04 schema tests: Alembic wiring and per-test databases.

Builds on the session-scoped ``postgres_container`` fixture from
``packages/core/tests/conftest.py``. Each schema test group gets its own
*database* inside that one container so a ``downgrade base`` in one test cannot
pull the schema out from under another. Roles are cluster-wide and shared, which
is exactly how a real deployment looks.
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = REPO_ROOT / "infra" / "scripts"


def async_engine(url: str) -> AsyncEngine:
    """An engine safe behind a transaction pooler (no prepared statement cache)."""
    return create_async_engine(url, connect_args={"statement_cache_size": 0})


def alembic_config(url: str) -> Config:
    """An Alembic ``Config`` pointed at ``url``.

    ``env.py`` reads the URL from ``Settings().database_url_migrations``, so the
    environment variable is what actually selects the database; setting it here
    keeps the two in one place.
    """
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


async def create_database(admin_url: str, name: str) -> str:
    """Create ``name`` in the same cluster as ``admin_url`` and return its URL."""
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


def migration_ddl(name: str) -> ModuleType:
    """Import ``infra/migrations/ddl/<name>.py``.

    Only importable once :func:`alembic_config` has put ``infra/migrations`` on
    ``sys.path`` — the same way Alembic itself reaches these modules.
    """
    return importlib.import_module(f"ddl.{name}")


@pytest.fixture(scope="session")
def container_url(postgres_container: PostgresContainer) -> str:
    """The asyncpg URL of the session's Postgres container."""
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_schema_db(container_url: str) -> Iterator[str]:
    """A database with ``0001_initial_schema`` applied, for the RLS/constraint tests.

    Sync on purpose: ``env.py`` calls ``asyncio.run``, which cannot run inside an
    already-running event loop, and a module/session scoped async fixture would
    need its own loop scope for no benefit.
    """
    url = asyncio.run(create_database(container_url, "hunter_schema"))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def schema_engine(migrated_schema_db: str) -> AsyncIterator[AsyncEngine]:
    """An engine on the migrated schema database, connected as the container owner."""
    engine = async_engine(migrated_schema_db)
    try:
        yield engine
    finally:
        await engine.dispose()
