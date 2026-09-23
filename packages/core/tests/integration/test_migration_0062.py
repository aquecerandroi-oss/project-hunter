"""``0062_meme_decision_tapes`` (T4.89): the chain and the slug; the table is
global (no RLS), append-only for the worker (no ``UPDATE`` grant), read-only
for the app; the checks refuse a tape that is not an array, a slice bigger
than its declared window or than the hard ceiling, a blank mint; one tape per
``(mint, as_of)``; the downgrade refuses while a tape exists (§17.7) and
otherwise drops the table; ``alembic check`` at head.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0062_meme_decision_tapes"
PREVIOUS = "0061_spot_desk_r71"
TABLE = "meme_decision_tapes"
_REVISION = "SELECT version_num FROM alembic_version"
_INSERT = (
    "INSERT INTO meme_decision_tapes "
    "  (mint, as_of, series, proposal_ids, trades, trades_in_window, derived) "
    "VALUES (:mint, :as_of, 'meme_event_gate_v1', "
    "  CAST(:ids AS uuid[]), CAST(:trades AS jsonb), :n, CAST(:derived AS jsonb))"
)
_TRADE = {
    "block_time": "2026-09-23T20:03:18+00:00",
    "received_at": "2026-09-23T20:03:18.4+00:00",
    "side": "buy",
    "sol": "0.5",
    "tokens": "1000",
    "trader": "W",
}


def _params(**overrides: object) -> dict[str, object]:
    params: dict[str, object] = {
        "mint": "AIRAAmint",
        "as_of": datetime(2026, 9, 23, 20, 3, 18, 790000, tzinfo=UTC),
        "ids": [],
        "trades": json.dumps([_TRADE]),
        "n": 31,
        "derived": json.dumps({"version": 1}),
    }
    params.update(overrides)
    return params


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0062"))


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
        await created.dispose()


async def _once[T](url: str, step: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    created = async_engine(url)
    try:
        return await step(created)
    finally:
        await created.dispose()


async def _execute(engine: AsyncEngine, statement: str, params: dict[str, object]) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(statement), params)


async def _scalar(engine: AsyncEngine, statement: str) -> object:
    async with engine.connect() as connection:
        return await connection.scalar(text(statement))


def test_the_revision_lands_on_0061_and_fits_the_version_column() -> None:
    source = REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py"
    assert f'down_revision: str | None = "{PREVIOUS}"' in source.read_text(encoding="utf-8")
    assert len(REVISION) <= 32
    assert migration_ddl("meme_decision_tapes").TABLE == TABLE


async def test_the_table_is_global_append_only_read_only_for_the_app_and_vacuumed_early(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        rls = await connection.scalar(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = :t"), {"t": TABLE}
        )
        reloptions, toast_options = (
            await connection.execute(
                text(
                    "SELECT c.reloptions, t.reloptions FROM pg_class c "
                    "LEFT JOIN pg_class t ON t.oid = c.reltoastrelid WHERE c.relname = :t"
                ),
                {"t": TABLE},
            )
        ).one()
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
    assert rls is False
    assert set(reloptions or []) >= {"autovacuum_vacuum_scale_factor=0.05"}
    assert set(toast_options or []) >= {"autovacuum_vacuum_scale_factor=0.05"}
    assert grants == {
        ("hunter_app", "SELECT"),
        ("hunter_worker", "SELECT"),
        ("hunter_worker", "INSERT"),
        ("hunter_worker", "DELETE"),
    }
    assert indexes == {f"pk_{TABLE}", f"uq_{TABLE}_mint_as_of", f"ix_{TABLE}_as_of"}


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"mint": ""}, "mint_not_blank"),
        ({"trades": json.dumps({"not": "an array"})}, "trades_is_an_array"),
        ({"n": 0}, "slice_within_window"),
        ({"trades": json.dumps([_TRADE] * 201), "n": 500}, "slice_is_bounded"),
        ({"derived": json.dumps([1])}, "derived_is_an_object"),
    ],
)
async def test_the_checks_refuse_a_malformed_tape(
    engine: AsyncEngine, overrides: dict[str, object], constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await _execute(engine, _INSERT, _params(**overrides))


async def test_one_tape_per_mint_and_instant(engine: AsyncEngine) -> None:
    params = _params(mint="DUPmint")
    try:
        await _execute(engine, _INSERT, params)
        with pytest.raises(IntegrityError, match=f"uq_{TABLE}_mint_as_of"):
            await _execute(engine, _INSERT, params)
    finally:
        await _execute(engine, f"DELETE FROM {TABLE} WHERE mint = 'DUPmint'", {})  # noqa: S608


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken to ``head``."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0062_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_tape_exists_and_otherwise_drops_the_table(
    upgraded: str,
) -> None:
    config = alembic_config(upgraded)
    asyncio.run(_once(upgraded, lambda e: _execute(e, _INSERT, _params(mint="KEEPmint"))))
    try:
        with pytest.raises(DBAPIError, match=f"1 {TABLE} rows exist"):
            command.downgrade(config, "-1")
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == REVISION
    finally:
        asyncio.run(_once(upgraded, lambda e: _execute(e, f"DELETE FROM {TABLE}", {})))  # noqa: S608
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, _REVISION))) == PREVIOUS
        gone = f"SELECT to_regclass('public.{TABLE}') IS NULL"
        assert asyncio.run(_once(upgraded, lambda e: _scalar(e, gone))) is True
    finally:
        command.upgrade(config, REVISION)
