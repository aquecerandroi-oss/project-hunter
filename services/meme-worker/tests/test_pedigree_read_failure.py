"""A failed pedigree read says *why*, against a real Postgres.

The 24/09/2026 incident: ``meme_pedigree_read_failed`` logged
``error="Error"`` and nothing else — SQLAlchemy's asyncpg adapter folds every
``asyncpg.PostgresError`` without a closer mapping (the statement timeout's
``QueryCanceledError`` included) into its generic ``Error``, so a timeout, a
lock wait and a deadlock all read the same. The SQLSTATE the adapter copies
onto the wrapper is what tells them apart. A real failure here: another
connection holds ``ACCESS EXCLUSIVE`` on ``meme_tokens`` and the reader's
``lock_timeout`` is short, so the read dies with ``55P03`` — the same field
carries ``57014`` for the production timeout. Then the lock is released and
the **same transaction** reads again: the savepoint rolled back, nothing else.

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sqlalchemy import text
from structlog.testing import capture_logs

from hunter_core.db.session import role_session
from hunter_meme_worker.lab_repo_fast import pedigree_for

from .test_lab_fast import CREATED, WORKER, _plant_token  # pyright: ignore[reportPrivateUsage]

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


async def test_a_failed_read_logs_the_sqlstate_and_the_savepoint_lets_the_tick_go_on(
    db_engine: AsyncEngine, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    mint = f"LOCKED_{uuid4().hex[:8]}"
    await _plant_token(
        db_session_factory, mint, created_at=CREATED, creator=f"C_{mint}", symbol="L1"
    )
    async with db_engine.connect() as locker:
        # Taken before the reader touches the table, so the reader is the one who waits.
        await locker.execute(text("LOCK TABLE meme_tokens IN ACCESS EXCLUSIVE MODE"))
        async with role_session(db_session_factory, db_role=WORKER) as session:
            await session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            with capture_logs() as logs:
                assert await pedigree_for(session, [mint]) == {}
            await locker.rollback()
            recovered = await pedigree_for(session, [mint])
    failures = [line for line in logs if line["event"] == "meme_pedigree_read_failed"]
    assert len(failures) == 1, logs
    failure = failures[0]
    assert failure["mints"] == 1 and failure["error"] == "Error"
    assert failure["sqlstate"] == "55P03", "lock_not_available, the real code — not the class name"
    assert "LockNotAvailableError" in failure["detail"] and "lock timeout" in failure["detail"]
    assert len(failure["detail"]) <= 300
    assert recovered[mint].creator_prior_mints_1h == 0, "same transaction, read again after it"
