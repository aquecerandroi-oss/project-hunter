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


DB_ROLES = frozenset({"hunter_app", "hunter_worker"})
"""The only roles a session may assume — the two the migration creates
(``infra/migrations/ddl/security.py``). ``SET ROLE`` takes an *identifier*,
not a value, so it cannot be a bound parameter; this allowlist is what keeps
the only interpolated fragment in this module a constant chosen from a closed
set, never something a caller (let alone a request) can shape."""

_SET_CONFIG = "SELECT set_config('{name}', :value, true)"


def _set_role(db_role: str) -> str:
    if db_role not in DB_ROLES:
        raise ValueError(f"unknown database role {db_role!r}; expected one of {sorted(DB_ROLES)}")
    return f"SET LOCAL ROLE {db_role}"


async def _apply_context(
    session: AsyncSession,
    db_role: str,
    org_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> None:
    """``SET LOCAL ROLE`` first, then the two RLS settings, in that order.

    The role comes first so every later statement in the transaction — the
    ``set_config`` calls included — already runs as the unprivileged role.
    That is the point of the downgrade: in dev (and in the test containers)
    the connection user is the database owner, and ``FORCE ROW LEVEL
    SECURITY`` still exempts a *superuser*. Assuming ``hunter_app`` makes the
    policies and the per-table grants bite for real, so a missing
    ``app.current_org`` is zero rows here exactly as it is in production.
    """
    await session.execute(text(_set_role(db_role)))
    if org_id is not None:
        await session.execute(
            text(_SET_CONFIG.format(name="app.current_org")), {"value": str(org_id)}
        )
    if user_id is not None:
        await session.execute(
            text(_SET_CONFIG.format(name="app.current_user")), {"value": str(user_id)}
        )


@asynccontextmanager
async def role_session(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    db_role: str = "hunter_app",
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """One transaction, opened as ``db_role``, with whichever RLS settings are given.

    The three named helpers below are this function with the combination each
    call site is allowed to use; prefer them, so a reader can tell from the
    name which rows the transaction can reach.
    """
    async with session_factory() as session, session.begin():
        await _apply_context(session, db_role, org_id, user_id)
        yield session


@asynccontextmanager
async def tenant_session(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
    *,
    db_role: str = "hunter_app",
) -> AsyncGenerator[AsyncSession, None]:
    """A session whose transaction has ``app.current_org`` set for RLS.

    Uses ``set_config(..., true)`` (transaction-local, per DATABASE.md §1.2's
    ``SET LOCAL``) with the id passed as a bound parameter — never
    string-interpolated — so no query here is vulnerable to injection.
    ``user_id`` additionally sets ``app.current_user``, which the ``users``
    policies read (DATABASE.md §15.4); pass it whenever a real person is
    behind the request.
    """
    async with role_session(
        session_factory, db_role=db_role, org_id=org_id, user_id=user_id
    ) as session:
        yield session


@asynccontextmanager
async def user_session(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    *,
    db_role: str = "hunter_app",
) -> AsyncGenerator[AsyncSession, None]:
    """User-scoped but organization-less: only ``app.current_user`` is set.

    Reaches exactly the caller's own ``users`` row (policy ``user_reads_own_row``).
    Every *tenant* table stays empty in this transaction, because
    ``tenant_isolation`` compares against an unset ``app.current_org`` — that is
    the intended behaviour, not a limitation to work around.
    """
    async with role_session(session_factory, db_role=db_role, user_id=user_id) as session:
        yield session


@asynccontextmanager
async def bootstrap_session(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    db_role: str = "hunter_app",
) -> AsyncGenerator[AsyncSession, None]:
    """For the two writes that create the very rows the settings point at.

    DATABASE.md §15.4: with ``FORCE ROW LEVEL SECURITY`` on ``organizations``
    and ``users``, inserting either one requires the corresponding setting to
    already name the id being inserted — so the application generates the UUID
    v7 *before* the insert and opens the transaction with it. Sign-up and the
    Clerk webhook are the only callers; the name is what makes that obvious in
    a diff.
    """
    async with role_session(
        session_factory, db_role=db_role, org_id=org_id, user_id=user_id
    ) as session:
        yield session


async def check_database(engine: AsyncEngine) -> bool:
    """``SELECT 1`` — true if Postgres answers, false on any error."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
