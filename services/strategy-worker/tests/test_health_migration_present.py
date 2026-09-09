"""``hunter_strategy_worker.health.migration_present`` / ``_objects_exist`` —
proving the readiness gate actually reads the schema it claims to (T3.52c).

``_REQUIRED_COLUMNS`` is a literal tuple in ``health.py``; a typo in a table or
column name there would make the check pass forever (``information_schema``
just returns zero rows for a name that never existed, which reads exactly like
"caught up"). Parametrizing over the real tuple — imported, not retyped — is
what turns that typo into a failing test instead of a readiness probe that
never goes red.

Each column is dropped with a plain ``ALTER TABLE ... DROP COLUMN`` inside the
same session, checked, then rolled back: Postgres DDL is transactional, so the
rollback restores the column for the next parametrization and for every other
test sharing ``migrated_db_url`` in this container.

Run: ``uv run pytest services/strategy-worker/tests/test_health_migration_present.py -q``
(one testcontainers file, one invocation, per T3.52c).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from hunter_strategy_worker.health import (
    _REQUIRED_COLUMNS,  # pyright: ignore[reportPrivateUsage]
    _objects_exist,  # pyright: ignore[reportPrivateUsage]
    migration_present,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration


class TestObjectsExistReadsRealColumns:
    @pytest.mark.parametrize(("table", "column"), _REQUIRED_COLUMNS)
    async def test_a_missing_required_column_turns_it_false(
        self, db_session_factory: async_sessionmaker[AsyncSession], table: str, column: str
    ) -> None:
        async with db_session_factory() as session:
            await session.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            assert await _objects_exist(session) is False
            # DDL is transactional in Postgres: this undoes the drop rather than
            # leaving the shared container's database missing the column for
            # whatever test runs after this one.
            await session.rollback()

    async def test_at_head_every_required_object_and_column_is_present(
        self, db_session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        assert await migration_present(db_session_factory) is True
