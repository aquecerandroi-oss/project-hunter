"""``0067_meme_token_state_history`` (EXP-M26 J, Astra's must-fix 2) — its own database.

What is proved: the table is global (no RLS, no tenant column) and **read-only for
both roles** — only the (``SECURITY DEFINER``) trigger writes it; the trigger records a
``completed_at``/``migrated_at`` change **through the worker's real upsert**
(``UPSERT_TOKEN``: ``LEAST``/``COALESCE`` on every observation) and never a no-op; a
token born with a state records its birth; the row is written **at commit**, with the
clock of the commit, not of the statement nor of the transaction's start; the history
leaves with its token under the declared retention although the worker holds no
``DELETE`` on it; several changes in one transaction land in order; a token changed and
pruned in one transaction does not fail the commit; the downgrade refuses while a row
exists and otherwise removes table, triggers and function; ``alembic check`` at head.
The H-022 export against this schema, and the visibility proof at L, are
``test_migration_0067_visibility.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_meme_worker.repo_rows import TokenRow
from hunter_meme_worker.repo_token_sql import UPSERT_TOKEN

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0067_meme_token_state_history"
PREVIOUS = "0066_meme_mature_opportunities"
TABLE = "meme_token_state_history"
T = datetime(2026, 10, 5, 12, tzinfo=UTC)
_REVISION = "SELECT version_num FROM alembic_version"
_HISTORY = (
    f"SELECT column_name, old_value, new_value, operation, db_role FROM {TABLE} "  # noqa: S608
    "WHERE mint = :mint ORDER BY id"
)
_FORGET = "SET LOCAL app.meme_retention = 'on'; DELETE FROM meme_tokens WHERE mint LIKE 'H67%'"


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0067"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head`` (the ``0057`` argument)."""
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        async with created.begin() as connection:
            for statement in _FORGET.split("; "):
                await connection.execute(text(statement))
        await created.dispose()


async def _once[R](url: str, step: Callable[[AsyncEngine], Awaitable[R]]) -> R:
    created = async_engine(url)
    try:
        return await step(created)
    finally:
        await created.dispose()


def _token(mint: str, **values: Any) -> TokenRow:
    return TokenRow(
        mint=mint, first_seen_source="pumpportal_ws", first_seen_at=T, last_seen_at=T, **values
    )


async def _upsert(engine: AsyncEngine, *rows: TokenRow) -> None:
    """The worker's own statement, as the worker, one transaction per row."""
    for row in rows:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE hunter_worker"))
            await connection.execute(UPSERT_TOKEN, asdict(row))


async def _history(engine: AsyncEngine, mint: str) -> list[tuple[Any, ...]]:
    async with engine.connect() as connection:
        return [tuple(r) for r in await connection.execute(text(_HISTORY), {"mint": mint})]


def test_the_revision_lands_on_0066_and_fits_the_version_column() -> None:
    source = REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py"
    assert f'down_revision: str | None = "{PREVIOUS}"' in source.read_text(encoding="utf-8")
    assert len(REVISION) <= 32
    assert migration_ddl("meme_token_state_history").TABLE == TABLE


async def test_the_table_is_global_append_only_and_cascades_with_its_token(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        rls = await connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": TABLE}
        )
        policies = await connection.scalar(
            text("SELECT count(*) FROM pg_policies WHERE tablename = :t"), {"t": TABLE}
        )
        tenant = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = :t AND column_name = 'organization_id'"
            ),
            {"t": TABLE},
        )
        grants = {
            (row[0], row[1])
            for row in await connection.execute(
                text(
                    "SELECT grantee, privilege_type FROM information_schema.role_table_grants "
                    "WHERE table_name = :t AND grantee IN ('hunter_app', 'hunter_worker')"
                ),
                {"t": TABLE},
            )
        }
        indexes = {
            row[0]
            for row in await connection.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": TABLE}
            )
        }
        on_delete = await connection.scalar(
            text(
                "SELECT confdeltype::text FROM pg_constraint "
                "WHERE conrelid = CAST(:t AS regclass) AND contype = 'f'"
            ),
            {"t": TABLE},
        )
    assert (rls, policies, tenant) == (False, 0, 0)
    assert grants == {("hunter_app", "SELECT"), ("hunter_worker", "SELECT")}
    async with engine.connect() as connection:
        definer = (
            await connection.execute(
                text(
                    "SELECT prosecdef, proconfig, "
                    "has_function_privilege('hunter_worker', oid, 'EXECUTE'), "
                    "has_function_privilege('hunter_app', oid, 'EXECUTE') "
                    "FROM pg_proc WHERE proname = 'meme_token_state_history_record'"
                )
            )
        ).one()
        deferred = {
            tuple(row)
            for row in await connection.execute(
                text(
                    "SELECT tgname, tgdeferrable, tginitdeferred FROM pg_trigger "
                    "WHERE tgname LIKE 'meme_tokens_state_history%'"
                )
            )
        }
    assert tuple(definer) == (True, ["search_path=pg_catalog, pg_temp"], False, False)
    assert deferred == {
        ("meme_tokens_state_history_on_insert", True, True),
        ("meme_tokens_state_history_on_update", True, True),
    }
    assert indexes == {f"pk_{TABLE}", f"ix_{TABLE}_mint_recorded_at"}
    assert on_delete == "c"


async def test_a_token_born_with_a_state_records_its_birth_and_one_without_records_nothing(
    engine: AsyncEngine,
) -> None:
    await _upsert(engine, _token("H67bare"))
    born = _token(
        "H67born", completed_at=T, migrated_at=T + timedelta(minutes=1), migrated_pool="P"
    )
    await _upsert(engine, born)
    assert await _history(engine, "H67bare") == []
    assert await _history(engine, "H67born") == [
        ("completed_at", None, T, "insert", "hunter_worker"),
        ("migrated_at", None, T + timedelta(minutes=1), "insert", "hunter_worker"),
    ]


async def test_the_real_upsert_records_every_change_and_never_a_no_op(engine: AsyncEngine) -> None:
    mint = "H67moves"
    ten, twenty, five = (T + timedelta(minutes=m) for m in (10, 20, 5))
    await _upsert(engine, _token(mint))
    await _upsert(engine, _token(mint, completed_at=ten))
    await _upsert(engine, _token(mint, completed_at=ten))  # the same answer again
    await _upsert(engine, _token(mint, completed_at=twenty))  # LEAST keeps ten: no change
    await _upsert(engine, _token(mint))  # an observation that knows nothing
    assert await _history(engine, mint) == [("completed_at", None, ten, "update", "hunter_worker")]
    await _upsert(engine, _token(mint, completed_at=five))  # the indexer's retrospective gd
    await _upsert(engine, _token(mint, migrated_at=twenty, migrated_pool="POOL"))
    await _upsert(engine, _token(mint, migrated_at=T + timedelta(hours=1), migrated_pool="X"))
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(
            text("UPDATE meme_tokens SET last_seen_at = now(), name = 'late' WHERE mint = :m"),
            {"m": mint},
        )
    assert await _history(engine, mint) == [
        ("completed_at", None, ten, "update", "hunter_worker"),
        ("completed_at", ten, five, "update", "hunter_worker"),
        ("migrated_at", None, twenty, "update", "hunter_worker"),
    ]


async def test_the_row_is_written_at_commit_with_the_clock_of_the_commit(
    engine: AsyncEngine,
) -> None:
    """The batch path (``wiring.run_board``: many upserts, one transaction) must not
    stamp a change with the instant of its statement: the row appears only at commit,
    stamped then."""
    await _upsert(engine, _token("H67clock"))
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(UPSERT_TOKEN, asdict(_token("H67clock", completed_at=T)))
        written = await connection.scalar(text("SELECT clock_timestamp()"))
        inside = await connection.scalar(
            text(f"SELECT count(*) FROM {TABLE} WHERE mint = 'H67clock'")  # noqa: S608
        )
        await connection.execute(text("SELECT pg_sleep(0.3)"))
    async with engine.connect() as connection:
        recorded = await connection.scalar(
            text(f"SELECT recorded_at FROM {TABLE} WHERE mint = 'H67clock'")  # noqa: S608
        )
    assert inside == 0, "the change is not in the history before the commit"
    assert recorded - written >= timedelta(seconds=0.3)


async def test_no_role_writes_the_history_only_the_trigger_does(engine: AsyncEngine) -> None:
    await _upsert(engine, _token("H67locked", completed_at=T))
    for role, statement in (
        ("hunter_worker", f"UPDATE {TABLE} SET new_value = now()"),  # noqa: S608
        ("hunter_worker", f"DELETE FROM {TABLE}"),  # noqa: S608
        ("hunter_worker", f"INSERT INTO {TABLE} (mint, column_name, new_value, operation, "  # noqa: S608
         "db_role, recorded_at) VALUES ('H67locked', 'completed_at', now(), 'update', 'x', "
         "now() - interval '1 day')"),
        ("hunter_app", f"INSERT INTO {TABLE} (mint, column_name, new_value, operation, "  # noqa: S608
         "db_role) VALUES ('H67locked', 'completed_at', now(), 'update', 'x')"),
    ):  # fmt: skip
        with pytest.raises(DBAPIError, match="permission denied"):
            async with engine.begin() as connection:
                await connection.execute(text(f"SET LOCAL ROLE {role}"))
                await connection.execute(text(statement))
    assert len(await _history(engine, "H67locked")) == 1


async def test_the_history_leaves_with_its_token_under_the_declared_retention(
    engine: AsyncEngine,
) -> None:
    await _upsert(engine, _token("H67pruned", completed_at=T))
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(text("SET LOCAL app.meme_retention = 'on'"))
        await connection.execute(text("DELETE FROM meme_tokens WHERE mint = 'H67pruned'"))
    assert await _history(engine, "H67pruned") == []


async def test_several_changes_in_one_transaction_land_in_the_order_they_happened(
    engine: AsyncEngine,
) -> None:
    """Deferred events fire in event order: birth and two ``LEAST`` steps of the same mint
    inside one batch are three rows, in that order (Astra, J round 4)."""
    thirty, twenty, ten = (T + timedelta(minutes=m) for m in (30, 20, 10))
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        for at in (thirty, twenty, ten):
            await connection.execute(UPSERT_TOKEN, asdict(_token("H67batch", completed_at=at)))
    assert await _history(engine, "H67batch") == [
        ("completed_at", None, thirty, "insert", "hunter_worker"),
        ("completed_at", thirty, twenty, "update", "hunter_worker"),
        ("completed_at", twenty, ten, "update", "hunter_worker"),
    ]


async def test_a_token_changed_and_pruned_in_one_transaction_does_not_fail_the_commit(
    engine: AsyncEngine,
) -> None:
    """At commit the deferred event of a deleted token has no parent: it leaves with the
    token instead of tripping the foreign key and failing the writer's commit."""
    async with engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(text("SET LOCAL app.meme_retention = 'on'"))
        await connection.execute(UPSERT_TOKEN, asdict(_token("H67gone", completed_at=T)))
        await connection.execute(text("DELETE FROM meme_tokens WHERE mint = 'H67gone'"))
    assert await _history(engine, "H67gone") == []


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken to ``head``."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0067_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


async def _scalar(engine: AsyncEngine, statement: str) -> object:
    async with engine.connect() as connection:
        return await connection.scalar(text(statement))


async def _plant(engine: AsyncEngine) -> None:
    await _upsert(engine, _token("H67kept", completed_at=T))


async def _forget(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        for statement in _FORGET.split("; "):
            await connection.execute(text(statement))


def test_the_downgrade_refuses_while_a_row_exists_and_otherwise_removes_everything(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    asyncio.run(_once(upgraded, _plant))
    try:
        with pytest.raises(DBAPIError, match=f"1 {TABLE} rows exist"):
            command.downgrade(config, PREVIOUS)
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION
    finally:
        asyncio.run(_once(upgraded, _forget))
    command.downgrade(config, PREVIOUS)
    try:
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == PREVIOUS
        leftovers = (
            f"SELECT (to_regclass('public.{TABLE}') IS NULL) "  # noqa: S608
            "AND NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname LIKE 'meme_tokens_state_history%') "
            "AND NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'meme_token_state_history_record')"
        )
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, leftovers))) is True
    finally:
        command.upgrade(config, REVISION)
    assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION
