"""``infra/scripts/seed.py`` and ``infra/scripts/create_partitions.py`` are idempotent.

Both scripts run against a database of their own so their writes cannot disturb
the RLS and constraint tests. They are loaded by path rather than imported: they
are operational scripts under ``infra/scripts``, not an installed package.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from collections.abc import Iterator
from types import ModuleType
from typing import Any, cast

import pytest
from alembic import command
from sqlalchemy import text

from .conftest import SCRIPTS_DIR, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

SEEDED_TABLES = (
    "exchanges",
    "strategies",
    "strategy_versions",
    "plan_entitlements",
    "feature_flags",
    "risk_profiles",
    "opportunity_weights",
)


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seed_db(container_url: str) -> Iterator[str]:
    """A migrated database used only by this module."""
    url = asyncio.run(create_database(container_url, "hunter_seed"))
    command.upgrade(alembic_config(url), "head")
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    yield url


async def _row_counts(url: str) -> dict[str, int]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            counts: dict[str, int] = {}
            for table in SEEDED_TABLES:
                value = await connection.scalar(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
                counts[table] = int(value or 0)
    finally:
        await engine.dispose()
    return counts


async def _partition_names(url: str) -> set[str]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT relname FROM pg_class WHERE relispartition AND relkind = 'r'")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


def test_seeding_twice_leaves_the_same_rows(seed_db: str) -> None:
    seed = _load_script("seed")

    first: dict[str, int] = asyncio.run(seed.seed())
    counts_after_first = asyncio.run(_row_counts(seed_db))
    second: dict[str, int] = asyncio.run(seed.seed())
    counts_after_second = asyncio.run(_row_counts(seed_db))

    assert first == second
    assert counts_after_first == counts_after_second
    assert counts_after_first["exchanges"] == 2
    assert counts_after_first["strategies"] == 8
    assert counts_after_first["strategy_versions"] == 8
    assert counts_after_first["plan_entitlements"] == 36
    assert counts_after_first["feature_flags"] == 7
    assert counts_after_first["risk_profiles"] == 3
    assert counts_after_first["opportunity_weights"] == 1


def test_seeded_risk_presets_carry_the_documented_limits(seed_db: str) -> None:
    """RISK_ENGINE.md §2, and fractions are JSON strings so they stay exact."""
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _balanced_limits() -> dict[str, Any]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                value = await connection.scalar(
                    text("SELECT limits FROM risk_profiles WHERE preset = 'balanced'")
                )
        finally:
            await engine.dispose()
        assert isinstance(value, dict)
        return cast("dict[str, Any]", value)

    limits = asyncio.run(_balanced_limits())
    assert limits["max_position_pct"] == "0.05"
    assert limits["risk_per_trade_pct"] == "0.005"
    assert limits["max_drawdown_pct"] == "0.10"
    assert limits["max_concurrent_positions"] == 6
    assert limits["auto_close_on_emergency"] is False


def test_create_partitions_is_idempotent(seed_db: str) -> None:
    create_partitions = _load_script("create_partitions")

    statements: list[tuple[str, str]] = create_partitions.planned_statements(2)
    before = asyncio.run(_partition_names(seed_db))
    created: list[str] = asyncio.run(create_partitions.ensure_partitions(statements))
    after = asyncio.run(_partition_names(seed_db))

    assert set(created) == after - before
    assert {name for name, _ in statements} <= after

    created_again: list[str] = asyncio.run(create_partitions.ensure_partitions(statements))
    assert created_again == []
    assert asyncio.run(_partition_names(seed_db)) == after


def test_create_partitions_dry_run_touches_nothing(seed_db: str) -> None:
    create_partitions = _load_script("create_partitions")

    before = asyncio.run(_partition_names(seed_db))
    statements: list[tuple[str, str]] = create_partitions.planned_statements(12)
    assert all(sql.startswith("CREATE TABLE IF NOT EXISTS") for _, sql in statements)
    assert asyncio.run(_partition_names(seed_db)) == before
