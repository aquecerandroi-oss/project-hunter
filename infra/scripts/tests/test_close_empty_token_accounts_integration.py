"""``close_empty_token_accounts`` SQL against the real migrated schema
(testcontainers Postgres 16, ``alembic upgrade head``): the in-flight count,
the executor's recognized-set query on the session this tool opens, and the
``audit_logs`` row written under RLS. Skips cleanly without Docker.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import close_empty_token_accounts_rules as rules  # noqa: E402

WALLET = "ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4"


async def test_the_reads_run_and_the_audit_row_lands_under_rls(migrated_db_url: str) -> None:
    engine = create_async_engine(migrated_db_url, connect_args={"statement_cache_size": 0})
    try:
        async with AsyncSession(engine) as session:
            assert await rules.in_flight_buys(session) == {"meme": 0, "spot": 0}
            assert await rules.open_positions(session) == {"meme": 0, "spot": 0}
            since = datetime(2026, 9, 28, 11, 59, tzinfo=UTC)
            assert await rules.read_recognized(session, since=since) == frozenset()
            await session.commit()
            # hunter_app has no BYPASSRLS: the NULL-org row must pass audit_system_scope
            await session.execute(text("SET LOCAL ROLE hunter_app"))
            await rules.write_audit(
                session,
                action=rules.ACTION_RUN,
                after={"wallet": WALLET, "outcome": "done", "signatures": ["sig1"]},
                actor="everton",
                reason="teste de integração",
                proof=None,
            )
            row = (
                await session.execute(
                    text(
                        "SELECT organization_id, actor_type, actor_id, entity_type, "
                        "after->>'wallet' AS wallet, metadata->>'actor_input' AS actor "
                        "FROM audit_logs WHERE action = :action"
                    ),
                    {"action": rules.ACTION_RUN},
                )
            ).one()
            assert tuple(row) == (None, "system", None, "wallet", WALLET, "everton")
    finally:
        await engine.dispose()


async def test_after_a_failed_insert_only_a_rollback_lets_the_run_row_land(
    migrated_db_url: str,
) -> None:
    """Security review (28/09): a failed ``.batch`` INSERT aborts the
    transaction; the ``finally`` ``.run`` row needs ``rollback_quietly`` first."""
    from close_empty_token_accounts_reads import rollback_quietly
    from sqlalchemy.exc import DBAPIError

    engine = create_async_engine(migrated_db_url, connect_args={"statement_cache_size": 0})

    async def audit(session: AsyncSession) -> None:
        await rules.write_audit(
            session,
            action=rules.ACTION_RUN,
            after={"wallet": WALLET, "outcome": "after_abort"},
            actor="everton",
            reason="teste de integração",
            proof=None,
        )

    try:
        async with AsyncSession(engine) as session:
            with pytest.raises(DBAPIError):  # e.g. the .batch INSERT, broken
                await session.execute(text("INSERT INTO audit_logs (id) VALUES ('not-a-uuid')"))
            with pytest.raises(DBAPIError, match="InFailedSQLTransaction|aborted"):
                await audit(session)  # what the finally did before the fix
            await rollback_quietly(session)
            await audit(session)  # the fix
            landed = await session.scalar(
                text("SELECT count(*) FROM audit_logs WHERE after->>'outcome' = 'after_abort'")
            )
            assert landed == 1
    finally:
        await engine.dispose()
