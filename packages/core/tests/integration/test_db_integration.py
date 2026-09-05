"""Integration tests for hunter_core.db.session against a real Postgres.

Uses the ``postgres:16-alpine`` testcontainer from ``tests/conftest.py``;
skips (with reason printed) if Docker is unreachable.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.db.session import (
    check_database,
    create_session_factory,
    get_session,
    role_session,
    tenant_session,
)

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


async def test_hunter_app_session_keeps_the_default_statement_timeout(
    db_engine: AsyncEngine,
) -> None:
    """D3 is scoped to ``hunter_worker`` only — the API's transactions must
    keep their current (server-default) behaviour."""
    factory = create_session_factory(db_engine)

    async with role_session(factory, db_role="hunter_app") as session:
        result = await session.execute(text("SHOW statement_timeout"))
        assert result.scalar() != "15s"
