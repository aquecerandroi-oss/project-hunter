"""Every migration applies, reverses, re-applies and matches the models.

Runs in its own database inside the session's Postgres container, so the
``downgrade base`` here cannot pull the schema out from under the other tests.

Anything that drives Alembic is a **sync** test: ``env.py`` calls
``asyncio.run``, which raises inside a running event loop.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.db.models import (
    Base,
    list_partition_name,
    list_partitioned_tables,
    partition_name,
    partitioned_tables,
)
from hunter_core.domain.enums import ALL_ENUMS
from hunter_core.domain.types import uuid7

from .conftest import alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

HEAD_REVISION = "0002_shadow_lab"
"""The revision ``upgrade head`` must reach. Bumped by every new revision, on
purpose: it is the one place that notices a revision file that never ran."""


@pytest.fixture(scope="module")
def cycle_db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_cycle"))


@pytest.fixture(scope="module")
def upgraded(cycle_db_url: str) -> Iterator[str]:
    """``alembic upgrade head`` on a clean database — that it does not raise is
    the first assertion of this module.
    """
    command.upgrade(alembic_config(cycle_db_url), "head")
    yield cycle_db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _revision(url: str) -> str | None:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


_LEGACY_OUTCOMES: dict[str, str] = {
    # label -> the columns a 0001 database could have written
    "resolved": "(signal_id, result, exit_ts) VALUES (:id, 'target', now())",
    "entered": "(signal_id, entry_ts) VALUES (:id, now())",
    "waiting": "(signal_id) VALUES (:id)",
}

_CONTRADICTORY_OUTCOME = "(signal_id, result, exit_ts) VALUES (:id, 'open', now())"
"""Still open, and yet it left: no ``tracking_state`` follows from this row."""


async def _legacy_signals(connection: AsyncConnection, count: int) -> list[uuid.UUID]:
    """``count`` signals of one fresh strategy version on one fresh market."""
    strategy, version, exchange, market = uuid7(), uuid7(), uuid7(), uuid7()
    await connection.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, 'Legacy')"),
        {"id": strategy, "key": f"legacy-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:id, :strategy, 'v1')"
        ),
        {"id": version, "strategy": strategy},
    )
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Legacy')"),
        {"id": exchange, "code": f"legacy-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :exchange, 'BTCUSDT', 'perpetual')"
        ),
        {"id": market, "exchange": exchange},
    )
    signals = [uuid7() for _ in range(count)]
    for signal_id in signals:
        await connection.execute(
            text(
                "INSERT INTO agent_signals (id, strategy_version_id, market_id, "
                "params_hash, direction, confidence) "
                "VALUES (:id, :version, :market, 'legacy', 'long', 0.5)"
            ),
            {"id": signal_id, "version": version, "market": market},
        )
    return signals


async def _seed_legacy_outcomes(url: str) -> dict[str, uuid.UUID]:
    """One ``signal_outcomes`` row per shape ``0001`` could hold, keyed by label."""
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            signals = await _legacy_signals(connection, len(_LEGACY_OUTCOMES))
            ids = dict(zip(_LEGACY_OUTCOMES, signals, strict=True))
            for label, columns in _LEGACY_OUTCOMES.items():
                await connection.execute(
                    text(f"INSERT INTO signal_outcomes {columns}"),
                    {"id": ids[label]},
                )
    finally:
        await engine.dispose()
    return ids


async def _seed_contradictory_outcome(url: str) -> uuid.UUID:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            (signal_id,) = await _legacy_signals(connection, 1)
            await connection.execute(
                text(f"INSERT INTO signal_outcomes {_CONTRADICTORY_OUTCOME}"),
                {"id": signal_id},
            )
    finally:
        await engine.dispose()
    return signal_id


async def _delete_outcome(url: str, signal_id: uuid.UUID) -> None:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM signal_outcomes WHERE signal_id = :id"), {"id": signal_id}
            )
    finally:
        await engine.dispose()


async def _tracking_states(url: str, ids: dict[str, uuid.UUID]) -> dict[str, str]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT signal_id, tracking_state FROM signal_outcomes "
                    "WHERE signal_id = ANY(:ids)"
                ),
                {"ids": list(ids.values())},
            )
            by_id = {row[0]: row[1] for row in result}
    finally:
        await engine.dispose()
    return {label: by_id[signal_id] for label, signal_id in ids.items()}


async def _scalar_counts(url: str) -> tuple[int, int]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.scalar(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            )
            enums = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' AND t.typtype = 'e'"
                )
            )
    finally:
        await engine.dispose()
    return int(tables or 0), int(enums or 0)


async def test_upgrade_head_reaches_the_latest_revision(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == HEAD_REVISION


async def test_every_table_in_the_metadata_exists(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        present = {row[0] for row in result}
    missing = set(Base.metadata.tables) - present
    assert not missing, f"declared in the models but absent from the database: {missing}"


async def test_every_enum_type_exists_with_the_expected_labels(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT t.typname, e.enumlabel FROM pg_type t "
                "JOIN pg_enum e ON e.enumtypid = t.oid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' ORDER BY t.typname, e.enumsortorder"
            )
        )
        actual: dict[str, list[str]] = {}
        for type_name, label in result:
            actual.setdefault(type_name, []).append(label)

    expected = {name: [member.value for member in cls] for name, cls in ALL_ENUMS.items()}
    assert actual == expected


async def test_every_partitioned_parent_has_its_initial_partitions(engine: AsyncEngine) -> None:
    partitions = migration_ddl("partitions")
    initial_months: tuple[tuple[int, int], ...] = partitions.INITIAL_MONTHS
    frozen_range: tuple[str, ...] = partitions.PARTITIONED_TABLES
    frozen_list: tuple[tuple[str, tuple[str, ...], str], ...] = partitions.LIST_PARTITIONED_TABLES

    assert set(frozen_range) == set(partitioned_tables()), (
        "a model gained or lost a RANGE postgresql_partition_by without a "
        "migration updating ddl.partitions.PARTITIONED_TABLES"
    )
    assert {name: (values, key) for name, values, key in frozen_list} == {
        name: (values, key) for name, (_column, values, key) in list_partitioned_tables().items()
    }, (
        "a model gained or lost a LIST postgresql_partition_by without a "
        "migration updating ddl.partitions.LIST_PARTITIONED_TABLES"
    )

    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT relname FROM pg_class WHERE relispartition AND relkind IN ('r', 'p')")
        )
        present = {row[0] for row in result}

    expected = {
        partition_name(table, year, month)
        for table in frozen_range
        for year, month in initial_months
    }
    for parent, values, _key in frozen_list:
        for value in values:
            intermediate = list_partition_name(parent, value)
            # the timeframe level is itself a partition, and partitioned in turn
            expected.add(intermediate)
            expected |= {
                partition_name(intermediate, year, month) for year, month in initial_months
            }
    assert expected <= present


def test_every_enum_type_belongs_to_exactly_one_revision(upgraded: str) -> None:
    """The frozen per-revision enum tuples still partition ``ALL_ENUMS``.

    ``ddl/enums.py`` used to iterate ``ALL_ENUMS`` live, so adding a type for a
    new revision made ``0001`` create it retroactively and the new revision fail
    with "type already exists". The tuples are frozen now; this is what keeps
    them honest, exactly like the grant-class test does for tables.
    """
    enums = migration_ddl("enums")
    initial: tuple[str, ...] = enums.INITIAL_ENUMS
    shadow: tuple[str, ...] = enums.SHADOW_ENUMS

    classified = [*initial, *shadow]
    assert len(classified) == len(set(classified)), "an enum type is owned by two revisions"
    assert set(classified) == set(ALL_ENUMS), (
        "an enum was added to ALL_ENUMS without a revision claiming it in ddl/enums.py"
    )


def test_the_new_revision_reverses_and_re_applies(upgraded: str) -> None:
    """``downgrade -1`` then ``upgrade head`` for the head revision alone.

    Cheaper than the full ``downgrade base`` below and much more specific: it is
    the exact operation an operator runs when a deploy has to be rolled back.
    """
    config = alembic_config(upgraded)

    command.downgrade(config, "-1")
    tables, _enums = asyncio.run(_scalar_counts(upgraded))
    assert asyncio.run(_revision(upgraded)) != HEAD_REVISION
    assert tables > 1, "downgrading one revision must not empty the schema"

    command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_the_new_revision_upgrades_a_database_that_already_has_rows(upgraded: str) -> None:
    """``0002`` on a populated ``0001``, not only on an empty schema.

    Raised by Astra's review of S0: ``signal_outcomes.tracking_state`` arrives
    with the column default ``pending_entry``, so an outcome that had already
    resolved (``result = 'target'``) would violate
    ``ck_signal_outcomes_tracking_state_matches_result`` the moment the CHECK is
    added, and the upgrade would abort — on every database except an empty one.
    The revision backfills from columns that already exist; this proves it.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    legacy = asyncio.run(_seed_legacy_outcomes(upgraded))

    command.upgrade(config, "head")

    states = asyncio.run(_tracking_states(upgraded, legacy))
    assert states == {"resolved": "terminal", "entered": "active", "waiting": "pending_entry"}
    command.check(config)


def test_the_new_revision_refuses_a_contradictory_legacy_row(upgraded: str) -> None:
    """An outcome that is ``open`` *and* has an ``exit_ts`` stops the upgrade.

    Astra's second round: the backfill can derive a tracking state from a
    consistent row, but not from a self-contradictory one, and inventing
    ``pending_entry`` for a tracking that already left would hand a finished
    outcome back to the worker as one waiting to enter. The migration names the
    rows instead of guessing.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    signal_id = asyncio.run(_seed_contradictory_outcome(upgraded))
    try:
        with pytest.raises(DBAPIError, match="cannot infer a tracking_state"):
            command.upgrade(config, "head")
        assert asyncio.run(_revision(upgraded)) != HEAD_REVISION, "the upgrade must not commit"
    finally:
        asyncio.run(_delete_outcome(upgraded, signal_id))
        command.upgrade(config, "head")


def test_alembic_check_reports_no_drift(upgraded: str) -> None:
    """The models and the migration describe the same schema."""
    command.check(alembic_config(upgraded))


def test_downgrade_base_then_upgrade_head(upgraded: str) -> None:
    """``downgrade()`` really reverses, and the schema can be rebuilt on top."""
    config = alembic_config(upgraded)

    command.downgrade(config, "base")
    tables, enums = asyncio.run(_scalar_counts(upgraded))
    assert tables == 1, "only alembic_version may survive a downgrade to base"
    assert enums == 0, "every enum type must be dropped by the downgrade"

    command.upgrade(config, "head")
    command.check(config)
