"""``seed.py --dry-run``/``--only``/``--yes`` (T3.39) against a real Postgres.

The operator's stated need (T3.33e/f, ``docs/ACTIVATION.md`` §9): re-seed just
``strategies`` on the VPS (``session_orb`` missing, stale descriptions) without
going anywhere near ``risk_profiles``, and see the diff before writing anything.

Run: ``uv run pytest infra/scripts/tests/test_seed_dry_run.py -q``
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine
    from testcontainers.community.postgres import PostgresContainer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load(name: str) -> ModuleType:
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_it", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _create_database(admin_url: str, name: str) -> str:
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()
    return admin_url.rsplit("/", 1)[0] + "/" + name


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


@pytest.fixture(scope="module")
def seed_db_url(postgres_container: PostgresContainer) -> str:
    """A database of its own, migrated to head — separate from every other module's."""
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_seed_dry_run")
    )
    command.upgrade(_alembic_config(url), "head")
    return url


@pytest.fixture
def engine(seed_db_url: str) -> AsyncEngine:
    return create_async_engine(seed_db_url, connect_args={"statement_cache_size": 0})


@pytest.fixture
def cli(seed_db_url: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """``seed_cli`` pointed at the migrated database (``DATABASE_URL_MIGRATIONS``)."""
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", seed_db_url)
    return _load("seed_cli")


async def _count(engine: AsyncEngine, table: str, *, where: str = "true") -> int:
    async with engine.connect() as connection:
        value = await connection.scalar(text(f"SELECT count(*) FROM {table} WHERE {where}"))  # noqa: S608
    return int(value or 0)


class TestDryRunWritesNothing:
    async def test_a_dry_run_reports_the_diff_and_writes_nothing(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        counts, diff = await cli.seed_with_report(dry_run=True)
        assert counts["strategies"] > 0
        assert any("strategies." in line and "NEW" in line for line in diff)
        assert await _count(engine, "strategies") == 0
        assert await _count(engine, "risk_profiles") == 0

    async def test_a_dry_run_with_only_reports_just_that_table(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        counts, diff = await cli.seed_with_report(dry_run=True, only="strategies")
        assert set(counts) == {"strategies", "strategy_versions"}
        assert all(line.startswith("strategies.") for line in diff)
        assert await _count(engine, "strategies") == 0


class TestOnlyNeverTouchesOtherTables:
    async def test_only_strategies_never_writes_risk_profiles(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        counts, _diff = await cli.seed_with_report(only="strategies")
        assert counts["strategies"] > 0
        assert await _count(engine, "strategies") > 0
        assert await _count(engine, "risk_profiles") == 0
        assert await _count(engine, "exchanges") == 0

    async def test_only_risk_profiles_writes_only_that_table(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        # ``strategies`` already has rows from the previous test (tests in this
        # module share one database, like every other integration suite here);
        # what this proves is that *this* run touches nothing this run did not
        # itself seed.
        counts, _diff = await cli.seed_with_report(only="risk_profiles")
        assert counts["risk_profiles"] == 4  # conservative, balanced, aggressive, paper_v1
        assert await _count(engine, "risk_profiles") == 4
        assert await _count(engine, "feature_definitions") == 0
        assert await _count(engine, "exchanges") == 0


class TestTheRiskDirectiveGate:
    async def test_a_first_seed_needs_no_yes(self, cli: ModuleType, engine: AsyncEngine) -> None:
        counts, _diff = await cli.seed_with_report()
        assert counts["risk_profiles"] == 4
        assert await _count(engine, "risk_profiles") == 4

    async def test_reseeding_unchanged_limits_needs_no_yes(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await cli.seed_with_report()
        counts, diff = await cli.seed_with_report()
        assert counts["risk_profiles"] == 4
        assert not any(line.startswith("risk_profiles.") for line in diff)

    async def test_a_changed_limit_refuses_without_yes_and_writes_nothing(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await cli.seed_with_report(only="risk_profiles")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE risk_profiles SET limits = limits || '{\"max_leverage\": 99}'::jsonb "
                    "WHERE preset = 'conservative' AND organization_id IS NULL"
                )
            )
        with pytest.raises(SystemExit, match="risk_profiles limits would change"):
            await cli.seed_with_report()
        async with engine.connect() as connection:
            leverage = await connection.scalar(
                text(
                    "SELECT limits->>'max_leverage' FROM risk_profiles "
                    "WHERE preset = 'conservative' AND organization_id IS NULL"
                )
            )
        assert leverage == "99"  # untouched: the refusal rolled back the whole run
        # restore the shipped value: tests in this module share one database,
        # and a left-over divergence would make the *next* test's own setup
        # call hit this same gate for a reason it did not introduce.
        await cli.seed_with_report(yes=True)

    async def test_dry_run_shows_the_would_be_change_without_yes(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await cli.seed_with_report(only="risk_profiles")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE risk_profiles SET limits = limits || '{\"max_leverage\": 42}'::jsonb "
                    "WHERE preset = 'balanced' AND organization_id IS NULL"
                )
            )
        counts, diff = await cli.seed_with_report(dry_run=True)
        assert counts["risk_profiles"] == 4
        assert any("risk_profiles.balanced" in line and "max_leverage" in line for line in diff)
        await cli.seed_with_report(yes=True)  # restore the shipped value (see above)

    async def test_yes_confirms_the_change_and_writes_it(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await cli.seed_with_report(only="risk_profiles")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE risk_profiles SET limits = limits || '{\"max_leverage\": 7}'::jsonb "
                    "WHERE preset = 'aggressive' AND organization_id IS NULL"
                )
            )
        counts, _diff = await cli.seed_with_report(yes=True)
        assert counts["risk_profiles"] == 4
        async with engine.connect() as connection:
            leverage = await connection.scalar(
                text(
                    "SELECT limits->>'max_leverage' FROM risk_profiles "
                    "WHERE preset = 'aggressive' AND organization_id IS NULL"
                )
            )
        assert leverage == "3"  # seed_reference's shipped value, restored
