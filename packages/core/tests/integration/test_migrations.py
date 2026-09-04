"""The initial migration applies, reverses, re-applies and matches the models.

Runs in its own database inside the session's Postgres container, so the
``downgrade base`` here cannot pull the schema out from under the other tests.

Anything that drives Alembic is a **sync** test: ``env.py`` calls
``asyncio.run``, which raises inside a running event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.db.models import (
    Base,
    list_partition_name,
    list_partitioned_tables,
    partition_name,
    partitioned_tables,
)
from hunter_core.domain.enums import ALL_ENUMS

from .conftest import alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration


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


async def test_upgrade_head_reaches_the_initial_revision(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "0001_initial_schema"


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
