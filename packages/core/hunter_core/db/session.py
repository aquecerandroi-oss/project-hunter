"""Async engine, session factory and RLS-aware tenant sessions.

DATABASE.md §1.2: the application opens a transaction and runs
``SET LOCAL app.current_org = '<uuid>'`` before any tenant query; without it
every RLS policy returns zero rows. ``connect_args``/``execution_options``
below disable both asyncpg's statement cache and SQLAlchemy's own prepared
statement cache — required because Neon/PgBouncer run in transaction pooling
mode, where a server-prepared statement from one transaction can leak into an
unrelated one on the next checkout.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

if TYPE_CHECKING:
    from hunter_core.settings import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the async engine for ``DATABASE_URL``.

    ``statement_cache_size=0`` (asyncpg) and ``prepared_statement_cache_size=0``
    turn off both layers of prepared-statement caching so the pool is safe
    behind a transaction-mode pooler.
    """
    database_url = settings.database_url
    if database_url is None:
        raise ValueError("DATABASE_URL is not configured")
    return create_async_engine(
        database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """A session factory bound to ``engine`` (no autoflush/autocommit surprises)."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """A plain (non-tenant) session — for global tables, migrations, or workers
    that bypass RLS (``hunter_worker`` role; DATABASE.md §1.2).

    ``session_factory`` is passed explicitly (built once at process startup via
    ``create_session_factory(create_engine(settings))``) rather than kept as a
    hidden module-level singleton, so callers (FastAPI deps, worker runtimes,
    tests) control its lifetime and unit tests can inject a fake.
    """
    async with session_factory() as session:
        yield session


@asynccontextmanager
async def tenant_session(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
) -> AsyncGenerator[AsyncSession, None]:
    """A session whose transaction has ``app.current_org`` set for RLS.

    Uses ``set_config(..., true)`` (transaction-local, per DATABASE.md §1.2's
    ``SET LOCAL``) with the org id passed as a bound parameter — never
    string-interpolated — so no query here is vulnerable to injection.
    """
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.current_org', :org_id, true)"),
                {"org_id": str(org_id)},
            )
            yield session


async def check_database(engine: AsyncEngine) -> bool:
    """``SELECT 1`` — true if Postgres answers, false on any error."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
