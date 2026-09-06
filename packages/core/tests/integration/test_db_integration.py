"""Integration tests for hunter_core.db.session against a real Postgres.

Uses the ``postgres:16-alpine`` testcontainer from ``tests/conftest.py``;
skips (with reason printed) if Docker is unreachable.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.db.session import (
    check_database,
    create_session_factory,
    get_session,
    role_session,
    tenant_session,
)
from hunter_core.settings import Settings

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration


async def test_check_database_true_against_real_postgres(db_engine: AsyncEngine) -> None:
    assert await check_database(db_engine) is True


async def test_tenant_session_sets_current_org_only_inside_its_own_transaction(
    db_engine: AsyncEngine,
) -> None:
    factory = create_session_factory(db_engine)
    org_id = uuid.uuid4()

    async with tenant_session(factory, org_id) as session:
        result = await session.execute(text("SELECT current_setting('app.current_org', true)"))
        assert result.scalar() == str(org_id)

    # a fresh (non-tenant) session/transaction must not see the setting —
    # SET LOCAL / set_config(..., true) is scoped to the transaction that set it.
    async with get_session(factory) as session:
        result = await session.execute(text("SELECT current_setting('app.current_org', true)"))
        assert result.scalar() in (None, "")


async def test_hunter_worker_session_has_a_statement_timeout(db_engine: AsyncEngine) -> None:
    """D3: a cancelled flush must not hang forever on a dead socket — the
    worker role gets a server-side deadline so a stuck statement is killed
    even if the client-side ``asyncio.wait_for`` backstop never gets to."""
    factory = create_session_factory(db_engine)

    async with role_session(factory, db_role="hunter_worker") as session:
        result = await session.execute(text("SHOW statement_timeout"))
        assert result.scalar() == "15s"


async def test_hunter_app_session_has_its_own_shorter_statement_timeout(
    db_engine: AsyncEngine,
) -> None:
    """S3a-MEDIUM: the API previously ran with the server default (no
    deadline). ``hunter_app`` now gets its own ``SET LOCAL statement_timeout``,
    distinct from (and shorter than) the worker's."""
    factory = create_session_factory(db_engine)

    async with role_session(factory, db_role="hunter_app") as session:
        result = await session.execute(text("SHOW statement_timeout"))
        assert result.scalar() == "10s"


async def test_hunter_app_statement_timeout_cancels_a_slow_query(
    postgres_container: PostgresContainer,
) -> None:
    """S3a-MEDIUM: an authenticated caller repeating an expensive/unindexed
    query (e.g. ``GET /api/v1/orgs/{org_id}/lab/shadow/summary?window=all``)
    must have every individual statement cut off server-side, not just bounded
    by the driver-level ``command_timeout`` backstop (D3)."""
    from pydantic import SecretStr

    from hunter_core.db.session import create_engine

    settings = Settings(
        database_url=SecretStr(postgres_container.get_connection_url()),
        db_statement_timeout_app_s=1,
    )
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        # asyncpg's ``QueryCanceledError`` has no dedicated PEP-249 mapping in
        # this dialect version, so it surfaces as the generic ``DBAPIError``
        # (``OperationalError``'s own parent) rather than ``OperationalError``
        # itself — either is the "server actually cut the query off" signal
        # this test exists to prove.
        with pytest.raises(DBAPIError, match="canceling statement due to statement timeout"):
            async with role_session(factory, settings=settings) as session:
                await session.execute(text("SELECT pg_sleep(2)"))
    finally:
        await engine.dispose()


async def test_statement_timeout_set_local_does_not_leak_to_the_next_transaction(
    postgres_container: PostgresContainer,
) -> None:
    """A transaction-pooling deployment (Neon/PgBouncer) hands the same
    physical connection to the next, unrelated transaction. ``SET LOCAL`` is
    transaction-scoped in Postgres itself (reset at COMMIT/ROLLBACK), so a
    short override used for one caller must not survive into the next one on
    a reused connection — proven here with an engine pinned to a single
    connection (``db_pool_size=1``) so both sessions are guaranteed to share
    the same socket.
    """
    from pydantic import SecretStr

    from hunter_core.db.session import create_engine

    base_url = SecretStr(postgres_container.get_connection_url())
    short_timeout = Settings(
        database_url=base_url, db_pool_size=1, db_max_overflow=0, db_statement_timeout_app_s=1
    )
    engine = create_engine(short_timeout)
    try:
        factory = create_session_factory(engine)

        async with role_session(factory, settings=short_timeout) as session:
            result = await session.execute(text("SHOW statement_timeout"))
            assert result.scalar() == "1s"

        # Same one-connection pool: this checkout reuses the physical
        # connection the previous transaction used. Its own SET LOCAL (the
        # process default, 10s) must be exactly what is in effect — not the
        # 1s from the transaction before it.
        default_timeout = Settings(database_url=base_url, db_pool_size=1, db_max_overflow=0)
        async with role_session(factory, settings=default_timeout) as session:
            result = await session.execute(text("SHOW statement_timeout"))
            assert result.scalar() == "10s"
    finally:
        await engine.dispose()
