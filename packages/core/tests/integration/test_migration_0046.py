"""``0046_meme_rule_set_history`` against a real Postgres (T4.35): the param
history table a ``--set-param`` writes into, and the sampled per-mint gate
refusal trail the fast lane writes into — both new, both refuse a downgrade
that would lose evidence.

A **new file** on purpose (the brief forbids editing ``test_migrations.py``
for this task): the fixture below upgrades to **this revision by name**
(``"0046_meme_rule_set_history"``), never ``"head"`` — so it stays correct
whether or not ``0044``/``0045`` are committed yet, and never contends with
``services/meme-worker/tests/conftest.py``'s own ``"head"`` resolution for a
concurrent agent's test run (see the migration's own docstring for the chain
note).

Run alone (``timeout 590``): it shares the container fixture of ``conftest.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .conftest import alembic_config, async_engine, create_database

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration

REVISION = "0046_meme_rule_set_history"
PARAM_HISTORY_TABLE = "meme_rule_set_param_history"
REFUSAL_TRAIL_TABLE = "meme_gate_refusals_by_mint"


async def _revision(url: str) -> str | None:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def cycle_db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_0046"))


@pytest.fixture(scope="module")
def upgraded(cycle_db_url: str) -> Iterator[str]:
    """``alembic upgrade 0046_meme_rule_set_history`` on a clean database."""
    command.upgrade(alembic_config(cycle_db_url), REVISION)
    yield cycle_db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _a_rule_set_id(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        row = await connection.scalar(text("SELECT id::text FROM meme_rule_sets LIMIT 1"))
    assert row is not None, "the earlier seeds must have left at least one rule set"
    return row


def test_upgrading_to_0046_does_not_raise(upgraded: str) -> None:
    assert asyncio.run(_revision(upgraded)) == REVISION


async def test_the_two_tables_exist_with_the_declared_columns(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        history_cols = (
            (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                    ),
                    {"t": PARAM_HISTORY_TABLE},
                )
            )
            .scalars()
            .all()
        )
        trail_cols = (
            (
                await connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                    ),
                    {"t": REFUSAL_TRAIL_TABLE},
                )
            )
            .scalars()
            .all()
        )
    assert set(history_cols) == {
        "id",
        "rule_set_id",
        "changed_at",
        "changed_by",
        "reason",
        "key",
        "old_value",
        "new_value",
        "system_event_id",
    }
    assert set(trail_cols) == {"id", "as_of", "rule_set_id", "mint", "refusal", "value", "limit"}


async def test_param_history_accepts_a_row_and_rejects_a_blank_reason(engine: AsyncEngine) -> None:
    rule_set_id = await _a_rule_set_id(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_rule_set_param_history "
                "(id, rule_set_id, changed_by, reason, key, old_value, new_value) "
                "VALUES (gen_random_uuid(), CAST(:rs AS uuid), 'meme_rule_set', "
                "'T4.35 test: sniper ceiling', 'max_snipers', '20'::jsonb, '1000'::jsonb)"
            ),
            {"rs": rule_set_id},
        )
    async with engine.connect() as connection:
        count = await connection.scalar(
            text(
                "SELECT count(*) FROM meme_rule_set_param_history WHERE rule_set_id = CAST(:rs AS uuid)"
            ),
            {"rs": rule_set_id},
        )
    assert count == 1
    with pytest.raises(DBAPIError, match="ck_meme_rule_set_param_history_reason_not_blank"):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO meme_rule_set_param_history "
                    "(id, rule_set_id, changed_by, reason, key, new_value) "
                    "VALUES (gen_random_uuid(), CAST(:rs AS uuid), 'x', '   ', 'k', 'true'::jsonb)"
                ),
                {"rs": rule_set_id},
            )


async def test_refusal_trail_accepts_a_proposal_row_and_a_near_miss_row(
    engine: AsyncEngine,
) -> None:
    rule_set_id = await _a_rule_set_id(engine)
    mint_a, mint_b = f"MintA{uuid.uuid4().hex[:8]}", f"MintB{uuid.uuid4().hex[:8]}"
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_gate_refusals_by_mint (id, as_of, rule_set_id, mint, refusal) "
                "VALUES (gen_random_uuid(), now(), CAST(:rs AS uuid), :mint, NULL)"
            ),
            {"rs": rule_set_id, "mint": mint_a},
        )
        await connection.execute(
            text(
                "INSERT INTO meme_gate_refusals_by_mint "
                '(id, as_of, rule_set_id, mint, refusal, value, "limit") '
                "VALUES (gen_random_uuid(), now(), CAST(:rs AS uuid), :mint, "
                "'snipers_above_max', 64, 20)"
            ),
            {"rs": rule_set_id, "mint": mint_b},
        )
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    'SELECT mint, refusal, value, "limit" FROM meme_gate_refusals_by_mint '
                    "WHERE rule_set_id = CAST(:rs AS uuid) ORDER BY mint"
                ),
                {"rs": rule_set_id},
            )
        ).all()
    by_mint = {r.mint: r for r in rows}
    assert by_mint[mint_a].refusal is None
    assert by_mint[mint_b].refusal == "snipers_above_max"
    assert by_mint[mint_b].value == 64 and by_mint[mint_b].limit == 20


async def test_refusal_trail_is_unique_per_rule_set_mint_and_instant(engine: AsyncEngine) -> None:
    rule_set_id = await _a_rule_set_id(engine)
    mint = f"MintDup{uuid.uuid4().hex[:6]}"
    as_of = datetime(2026, 9, 16, 16, 20, tzinfo=UTC)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO meme_gate_refusals_by_mint (id, as_of, rule_set_id, mint, refusal) "
                "VALUES (gen_random_uuid(), :as_of, CAST(:rs AS uuid), :mint, 'holders_below_min')"
            ),
            {"rs": rule_set_id, "mint": mint, "as_of": as_of},
        )
    with pytest.raises(DBAPIError, match="uq_meme_gate_refusals_by_mint"):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO meme_gate_refusals_by_mint (id, as_of, rule_set_id, mint, refusal) "
                    "VALUES (gen_random_uuid(), :as_of, CAST(:rs AS uuid), :mint, 'holders_below_min')"
                ),
                {"rs": rule_set_id, "mint": mint, "as_of": as_of},
            )


async def test_grants_let_the_worker_write_the_trail_and_the_api_only_read_it(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        worker_privileges = {
            p: await connection.scalar(
                text("SELECT has_table_privilege('hunter_worker', :t, :p)::text"),
                {"t": REFUSAL_TRAIL_TABLE, "p": p},
            )
            for p in ("SELECT", "INSERT", "DELETE", "UPDATE")
        }
        app_privileges = {
            p: await connection.scalar(
                text("SELECT has_table_privilege('hunter_app', :t, :p)::text"),
                {"t": REFUSAL_TRAIL_TABLE, "p": p},
            )
            for p in ("SELECT", "INSERT", "DELETE")
        }
        no_worker_on_history = await connection.scalar(
            text("SELECT has_table_privilege('hunter_worker', :t, 'SELECT')::text"),
            {"t": PARAM_HISTORY_TABLE},
        )
        no_app_on_history = await connection.scalar(
            text("SELECT has_table_privilege('hunter_app', :t, 'SELECT')::text"),
            {"t": PARAM_HISTORY_TABLE},
        )
    assert worker_privileges == {
        "SELECT": "true",
        "INSERT": "true",
        "DELETE": "true",
        "UPDATE": "false",
    }
    assert app_privileges == {"SELECT": "true", "INSERT": "false", "DELETE": "false"}
    assert no_worker_on_history == "false", "the CLI writes the param history, not the worker"
    assert no_app_on_history == "false", "the CLI writes/reads the param history, not the API"


def test_downgrade_refuses_while_either_table_holds_a_row(upgraded: str) -> None:
    config = alembic_config(upgraded)
    with pytest.raises(DBAPIError, match="meme_rule_set_param_history rows exist"):
        command.downgrade(config, "0044_meme_gate_e2b_arm")
    assert asyncio.run(_revision(upgraded)) == REVISION, (
        "a refused downgrade must not have moved the schema"
    )


async def _empty_both_tables(url: str) -> None:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"DELETE FROM {REFUSAL_TRAIL_TABLE}"))  # noqa: S608
            await connection.execute(text(f"DELETE FROM {PARAM_HISTORY_TABLE}"))  # noqa: S608
    finally:
        await engine.dispose()


async def _row_counts(url: str) -> tuple[int | None, int | None]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            history_count = await connection.scalar(
                text(f"SELECT count(*) FROM {PARAM_HISTORY_TABLE}")  # noqa: S608
            )
            trail_count = await connection.scalar(
                text(f"SELECT count(*) FROM {REFUSAL_TRAIL_TABLE}")  # noqa: S608
            )
    finally:
        await engine.dispose()
    return history_count, trail_count


def test_downgrade_succeeds_once_both_tables_are_emptied_and_upgrade_comes_back_clean(
    cycle_db_url: str,
) -> None:
    """Sync (module docstring): ``env.py`` calls ``asyncio.run``, which cannot
    run inside pytest-asyncio's already-running loop."""
    asyncio.run(_empty_both_tables(cycle_db_url))
    config = alembic_config(cycle_db_url)
    command.downgrade(config, "0044_meme_gate_e2b_arm")
    assert asyncio.run(_revision(cycle_db_url)) == "0044_meme_gate_e2b_arm"
    command.upgrade(config, REVISION)
    assert asyncio.run(_revision(cycle_db_url)) == REVISION
    history_count, trail_count = asyncio.run(_row_counts(cycle_db_url))
    assert history_count == 0 and trail_count == 0
