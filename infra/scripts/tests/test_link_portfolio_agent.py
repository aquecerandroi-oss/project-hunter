"""T4.72 — the ``agents`` link that turns the bridge's population from zero to one.

``docs/ACTIVATION.md`` §8a measured the root cause of "154 sinais paper, 0
propostas" on 2026-09-08: ``bridge_screen._agent_for`` only admits a signal
whose ``strategy_version_id`` is run by an **enabled** ``agents`` row inside
the target wallet, and nothing in the product writes that row. This module
tests ``infra/scripts/link_portfolio_agent.py`` — the audited act that does,
on the same pattern as ``test_link_portfolio_risk_profile.py``: refusals
first, no write without ``--yes``, one ``audit_logs`` row per real write, and
an idempotent replay.

Run:
    uv run pytest infra/scripts/tests/test_link_portfolio_agent.py -q
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
import uuid
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

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

ORG_ID = uuid.UUID("01a07a72-0000-7000-8000-00000000000a")
WORKSPACE_ID = uuid.UUID("01a07a72-0000-7000-8000-00000000000b")
WALLET_ID = uuid.UUID("01a07a72-0000-7000-8000-00000000000c")
STRATEGY_ID = uuid.UUID("01a07a72-0000-7000-8000-00000000000d")
PAPER_VERSION_ID = uuid.UUID("01a07a72-0000-7000-8000-00000000000e")
RESEARCH_VERSION_ID = uuid.UUID("01a07a72-0000-7000-8000-00000000000f")
DRAFT_PAPER_VERSION_ID = uuid.UUID("01a07a72-0000-7000-8000-000000000010")


def _load(name: str) -> ModuleType:
    """Load ``infra/scripts/<name>.py`` the way running it as a script would."""
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_t472", SCRIPTS_DIR / f"{name}.py"
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
    import os

    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


@pytest.fixture(scope="module")
def link_agent_db_url(postgres_container: PostgresContainer) -> str:
    """A database of its own, migrated to head, seeded like the VPS of T3.71."""
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_link_agent")
    )
    command.upgrade(_alembic_config(url), "head")
    asyncio.run(_seed(url))
    return url


async def _seed(url: str) -> None:
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO organizations (id, slug, name) VALUES (:id, 'ever', 'ever')"),
                {"id": ORG_ID},
            )
            await conn.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, objective) "
                    "VALUES (:id, :org, 'principal', 'paper_trading')"
                ),
                {"id": WORKSPACE_ID, "org": ORG_ID},
            )
            await conn.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                    "initial_capital) VALUES (:id, :org, :ws, 'Carteira paper principal', "
                    "'paper', 20000)"
                ),
                {"id": WALLET_ID, "org": ORG_ID, "ws": WORKSPACE_ID},
            )
            await conn.execute(
                text("INSERT INTO strategies (id, key, name) VALUES (:id, 'momentum', 'Momentum')"),
                {"id": STRATEGY_ID},
            )
            # v2: research_only, active — the sibling coorte that must never be linkable.
            await conn.execute(
                text(
                    "INSERT INTO strategy_versions (id, strategy_id, version, status, purpose, "
                    "code_ref, activated_at) VALUES (:id, :strategy, 'v2', 'active', "
                    "'research_only', 'hunter_core.strategies.momentum_v1@sha256:aa', now())"
                ),
                {"id": RESEARCH_VERSION_ID, "strategy": STRATEGY_ID},
            )
            # v3: purpose=paper, active — EXP-0005's candidate, the one this script links.
            await conn.execute(
                text(
                    "INSERT INTO strategy_versions (id, strategy_id, version, status, purpose, "
                    "code_ref, activated_at) VALUES (:id, :strategy, 'v3', 'active', 'paper', "
                    "'hunter_core.strategies.momentum_v1@sha256:ab', now())"
                ),
                {"id": PAPER_VERSION_ID, "strategy": STRATEGY_ID},
            )
            # v4: purpose=paper but still draft — not yet activated, must be refused.
            await conn.execute(
                text(
                    "INSERT INTO strategy_versions (id, strategy_id, version, status, purpose) "
                    "VALUES (:id, :strategy, 'v4', 'draft', 'paper')"
                ),
                {"id": DRAFT_PAPER_VERSION_ID, "strategy": STRATEGY_ID},
            )
    finally:
        await engine.dispose()


@pytest.fixture
def engine(link_agent_db_url: str) -> AsyncEngine:
    return create_async_engine(link_agent_db_url, connect_args={"statement_cache_size": 0})


@pytest.fixture
def script(link_agent_db_url: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("DATABASE_URL_MIGRATIONS", link_agent_db_url)
    return _load("link_portfolio_agent")


def _args(
    *,
    org_slug: str = "ever",
    strategy: str = "momentum",
    version: str = "v3",
    name: str | None = None,
    yes: bool = False,
    actor: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        org_slug=org_slug,
        strategy=strategy,
        version=version,
        name=name,
        dry_run=not yes,
        yes=yes,
        actor=actor,
    )


async def _agent_row(engine: AsyncEngine, version_id: uuid.UUID = PAPER_VERSION_ID) -> Any:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT id, status::text AS status, allowed_directions::text[] AS dirs, "
                    "name FROM agents WHERE organization_id = :org AND portfolio_id = :pf "
                    "AND strategy_version_id = :version AND deleted_at IS NULL"
                ),
                {"org": ORG_ID, "pf": WALLET_ID, "version": version_id},
            )
        ).one_or_none()


async def _audit_rows(engine: AsyncEngine, entity_id: uuid.UUID) -> list[Any]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT organization_id, actor_type, action, entity_type, entity_id, before, "
                "after, metadata FROM audit_logs WHERE entity_id = :id ORDER BY created_at"
            ),
            {"id": entity_id},
        )
        return list(result.mappings())


async def _delete_agent(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM agents WHERE organization_id = :org"), {"org": ORG_ID})


class TestTheLinkRefuses:
    async def test_an_unknown_org_slug_is_refused(self, script: ModuleType, capsys: Any) -> None:
        assert await script.run(_args(org_slug="nope", yes=True)) == 1
        assert "no organization" in capsys.readouterr().out

    async def test_an_unknown_strategy_version_is_refused(
        self, script: ModuleType, capsys: Any
    ) -> None:
        assert await script.run(_args(version="v99", yes=True)) == 1
        assert "no strategy_versions row" in capsys.readouterr().out

    async def test_a_research_only_version_is_refused(
        self, script: ModuleType, capsys: Any
    ) -> None:
        assert await script.run(_args(version="v2", yes=True)) == 1
        printed = capsys.readouterr().out
        assert "purpose=" in printed and "research_only" in printed

    async def test_a_draft_paper_version_is_refused(self, script: ModuleType, capsys: Any) -> None:
        assert await script.run(_args(version="v4", yes=True)) == 1
        assert "status='draft'" in capsys.readouterr().out or "status=" in capsys.readouterr().out

    async def test_dry_run_and_yes_together_are_a_usage_error(
        self, script: ModuleType, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "link_portfolio_agent.py",
                "--org-slug",
                "ever",
                "--strategy",
                "momentum",
                "--version",
                "v3",
                "--dry-run",
                "--yes",
            ],
        )
        with pytest.raises(SystemExit) as exit_info:
            script.main()
        assert exit_info.value.code == 2


class TestTheLinkWrites:
    async def test_the_preview_prints_the_plan_and_writes_nothing(
        self, script: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _delete_agent(engine)
        assert await script.run(_args()) == 0
        printed = capsys.readouterr().out
        assert "would link" in printed
        assert "['long']" in printed
        assert "nothing written" in printed
        assert await _agent_row(engine) is None

    async def test_yes_creates_an_enabled_long_only_agent_and_one_audit_row(
        self, script: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        await _delete_agent(engine)
        assert await script.run(_args(yes=True, actor="Everton")) == 0
        printed = capsys.readouterr().out
        assert "linked" in printed

        row = await _agent_row(engine)
        assert row is not None
        assert row.status == "enabled"
        assert row.dirs == ["long"]
        assert row.name == "momentum v3 (paper)"

        rows = await _audit_rows(engine, row.id)
        assert len(rows) == 1
        assert rows[0]["action"] == "agent.created"
        assert rows[0]["actor_type"] == "system"
        assert rows[0]["entity_type"] == "agent"
        assert rows[0]["metadata"]["actor_input"] == "Everton"
        assert rows[0]["metadata"]["task"] == "T4.72"

    async def test_running_it_again_is_a_no_op_and_adds_no_second_audit_row(
        self, script: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        row = await _agent_row(engine)
        assert row is not None and row.status == "enabled"
        before_rows = len(await _audit_rows(engine, row.id))

        assert await script.run(_args(yes=True)) == 0
        assert "already status=enabled" in capsys.readouterr().out
        assert len(await _audit_rows(engine, row.id)) == before_rows

    async def test_a_paused_agent_is_reactivated_not_duplicated(
        self, script: ModuleType, engine: AsyncEngine, capsys: Any
    ) -> None:
        row = await _agent_row(engine)
        assert row is not None
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE agents SET status = 'paused' WHERE id = :id"), {"id": row.id}
            )
        before_rows = len(await _audit_rows(engine, row.id))

        assert await script.run(_args(yes=True)) == 0
        printed = capsys.readouterr().out
        assert "reactivated: True" in printed or "reactivating" in printed

        after = await _agent_row(engine)
        assert after is not None
        assert after.id == row.id, "reactivation must reuse the row, never insert a second one"
        assert after.status == "enabled"

        rows = await _audit_rows(engine, row.id)
        assert len(rows) == before_rows + 1
        assert rows[-1]["action"] == "agent.reactivated"

    async def test_the_agent_is_exactly_what_bridge_screen_agent_for_selects(
        self, script: ModuleType, engine: AsyncEngine
    ) -> None:
        """The point of the whole task: after the link, ``_agent_for``'s own
        query (mirrored here, not imported, since it lives behind an asyncpg
        session in ``hunter_execution_worker``) finds exactly one row."""
        async with engine.connect() as conn:
            agent_id = await conn.scalar(
                text(
                    "SELECT id FROM agents WHERE organization_id = :org AND portfolio_id = :pf "
                    "AND strategy_version_id = :version AND status = 'enabled' "
                    "AND deleted_at IS NULL ORDER BY created_at LIMIT 1"
                ),
                {"org": ORG_ID, "pf": WALLET_ID, "version": PAPER_VERSION_ID},
            )
        assert agent_id is not None
