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


async def _delete_strategy(engine: AsyncEngine, key: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM strategies WHERE key = :key"), {"key": key})


class TestDryRunWritesNothing:
    async def test_a_dry_run_reports_the_diff_and_writes_nothing(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """BAIXA-10 (T3.39b review): never assumes this test runs before another
        one in the module — tests here share one database (module-scoped
        fixture) — by clearing one known key first, so this run always has a
        NEW row to report, whatever else the shared database already holds.
        Counts are compared to their own *before* value, never to a hardcoded
        zero, for the same reason.
        """
        await _delete_strategy(engine, "session_orb")
        before_strategies = await _count(engine, "strategies")
        before_risk_profiles = await _count(engine, "risk_profiles")
        counts, diff = await cli.seed_with_report(dry_run=True)
        assert counts["strategies"] > 0
        assert any("strategies.session_orb: NEW" in line for line in diff)
        assert await _count(engine, "strategies") == before_strategies
        assert await _count(engine, "risk_profiles") == before_risk_profiles

    async def test_a_dry_run_with_only_reports_just_that_table(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """BAIXA-9: ``strategy_versions`` is what actually carries ``code_ref``
        and parameters, and it moves with ``strategies`` in every real write
        (``seed_strategies``) — the diff has to show it moving too, including
        under ``--only strategies``."""
        await _delete_strategy(engine, "narrative")
        before = await _count(engine, "strategies")
        counts, diff = await cli.seed_with_report(dry_run=True, only="strategies")
        assert set(counts) == {"strategies", "strategy_versions"}
        assert all(line.startswith(("strategies.", "strategy_versions.")) for line in diff)
        assert any("strategies.narrative: NEW" in line for line in diff)
        assert any("strategy_versions.narrative v1: NEW" in line for line in diff)
        assert await _count(engine, "strategies") == before


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

    async def test_a_changed_limit_refuses_without_yes_via_only_too(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """BAIXA-7: the same gate applies to ``--only risk_profiles``, not just
        a full run — the operator's stated need is re-seeding *one* table."""
        await cli.seed_with_report(only="risk_profiles")
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE risk_profiles SET limits = limits || '{\"max_leverage\": 55}'::jsonb "
                    "WHERE preset = 'balanced' AND organization_id IS NULL"
                )
            )
        with pytest.raises(SystemExit, match="risk_profiles limits would change"):
            await cli.seed_with_report(only="risk_profiles")
        async with engine.connect() as connection:
            leverage = await connection.scalar(
                text(
                    "SELECT limits->>'max_leverage' FROM risk_profiles "
                    "WHERE preset = 'balanced' AND organization_id IS NULL"
                )
            )
        assert leverage == "55"  # untouched: the refusal rolled back the whole run
        await cli.seed_with_report(only="risk_profiles", yes=True)  # restore the shipped value

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


SEEDED_TABLES = (
    # Mirrors packages/core/tests/integration/test_schema_seed_and_partitions.py's
    # constant of the same name — the set of tables ``seed()`` reports.
    "exchanges",
    "strategies",
    "strategy_versions",
    "plan_entitlements",
    "feature_flags",
    "risk_profiles",
    "feature_definitions",
    "opportunity_weights",
)


class TestRunEverythingMatchesSeededTables:
    async def test_it_reports_exactly_the_seeded_tables(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """MÉDIA-5: ``seed_cli._run_everything`` and ``seed()``'s own report
        (``SEEDED_TABLES``, asserted the same way there) describe the same set
        of tables — a table added to one side and not the other is a count
        that goes quietly missing from an operator's report."""
        async with engine.begin() as connection:
            counts = await cli._run_everything(connection)
        assert set(counts) == set(SEEDED_TABLES)


class TestUnattendedGate:
    """MÉDIA-4 (T3.39b review): a non-empty diff refuses to commit when nobody
    is watching (``attended=False``, ``main()``'s ``sys.stdin.isatty()``),
    unless ``--yes`` or ``--dry-run`` — and the diff is emitted before that
    decision, never after a commit that already happened."""

    async def test_a_non_empty_diff_refuses_when_unattended_and_not_yes(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await _delete_strategy(engine, "derivatives")
        before = await _count(engine, "strategies")
        with pytest.raises(SystemExit, match="stdin is not a TTY"):
            await cli.seed_with_report(only="strategies", attended=False)
        assert await _count(engine, "strategies") == before

    async def test_yes_writes_even_when_unattended(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await _delete_strategy(engine, "derivatives")
        counts, _diff = await cli.seed_with_report(only="strategies", attended=False, yes=True)
        assert counts["strategies"] > 0
        assert await _count(engine, "strategies", where="key = 'derivatives'") == 1

    async def test_dry_run_never_needs_yes_even_when_unattended(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        await _delete_strategy(engine, "ensemble")
        counts, diff = await cli.seed_with_report(only="strategies", attended=False, dry_run=True)
        assert counts["strategies"] > 0
        assert any("strategies.ensemble: NEW" in line for line in diff)
        assert await _count(engine, "strategies", where="key = 'ensemble'") == 0

    async def test_the_diff_is_emitted_before_any_write_lands(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """The diff is printed (``emit``) before the transaction commits: an
        ``emit`` that blows up right after the first line must still leave the
        table untouched, which could not be true if the write had already
        landed by the time the old code printed anything (it printed only
        after ``seed_with_report`` had already returned and committed)."""
        await _delete_strategy(engine, "order_flow")
        before = await _count(engine, "strategies")

        def _boom(_line: str) -> None:
            raise RuntimeError("emit raised before commit")

        with pytest.raises(RuntimeError, match="emit raised before commit"):
            await cli.seed_with_report(only="strategies", emit=_boom)
        assert await _count(engine, "strategies") == before


class TestOnlyExchanges:
    """T3.44c: ``--only exchanges`` — the venue catalogue joins ``--only``.

    It joined only because the seed gained something to say about ``exchanges``:
    until ``0016`` added ``planned`` (DATABASE.md §28), ``seed_exchanges`` never
    wrote ``status``, so a re-seed of that table could not change a stored row
    and the diff would always have been empty.
    """

    async def test_it_is_a_choice_the_cli_accepts(self, cli: ModuleType) -> None:
        assert "exchanges" in cli.seed_dry_run.TABLE_CHOICES

    async def test_a_dry_run_shows_the_label_moving_and_writes_nothing(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        """The operator's whole reason for the flag: see Bybit go back to
        ``planned`` *before* committing it."""
        await cli.seed_with_report(only="exchanges")
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE exchanges SET status = 'active' WHERE code = 'bybit'")
            )
        counts, diff = await cli.seed_with_report(only="exchanges", dry_run=True)
        assert set(counts) == {"exchanges"}
        assert any(
            line.startswith("exchanges.bybit:") and "'active' -> " in line and "planned" in line
            for line in diff
        ), diff
        assert await _count(engine, "exchanges", where="code = 'bybit' AND status = 'active'") == 1

    async def test_writing_it_moves_the_label_and_touches_no_other_table(
        self, cli: ModuleType, engine: AsyncEngine
    ) -> None:
        before_strategies = await _count(engine, "strategies")
        counts, _diff = await cli.seed_with_report(only="exchanges", yes=True)
        assert counts["exchanges"] == 2
        assert await _count(engine, "exchanges", where="code = 'bybit' AND status = 'planned'") == 1
        assert (
            await _count(engine, "exchanges", where="code = 'binance' AND status = 'active'") == 1
        )
        assert await _count(engine, "strategies") == before_strategies
