"""``infra/scripts/open_paper_wallet.py`` against a real Postgres — the
confirmation, audit and scope contract from the security review of
``2688ef1`` (S3, T3.1c).

Runs the script's own ``_run(args)`` directly (no subprocess, no ``sys.argv``
plumbing) against a database with every migration applied, exactly as an
operator invoking the script would reach it — ``hunter_worker`` BYPASSRLS
included. ``fetch_quote`` is monkeypatched to a fixed rate: this is not a
test of Binance's API, and hitting the real network here would make the
suite flaky and non-hermetic (CLAUDE.md: ``live`` markers only, never in CI).

Run:
    uv run pytest infra/scripts/tests/test_open_paper_wallet.py -q
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
import time
import uuid
from decimal import Decimal
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


def _load_script(name: str) -> ModuleType:
    """Load ``infra/scripts/<name>.py`` the way running it as a script would.

    ``SCRIPTS_DIR`` on ``sys.path`` also makes ``open_paper_wallet.py``'s own
    ``from paper_wallet_lookup import ...`` / ``from paper_wallet_confirmation
    import ...`` resolve exactly as they do when the script is actually run.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}_it", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
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
def wallet_db_url(postgres_container: PostgresContainer) -> str:
    """A database of its own, migrated to head — separate from the partition
    job's database so one module's rows never affect the other's counts."""
    url = asyncio.run(
        _create_database(postgres_container.get_connection_url(), "hunter_open_paper_wallet")
    )
    command.upgrade(_alembic_config(url), "head")
    return url


@pytest.fixture
def engine(wallet_db_url: str) -> AsyncEngine:
    return create_async_engine(wallet_db_url, connect_args={"statement_cache_size": 0})


def _use(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the script's own ``Settings()`` at this database."""
    monkeypatch.setenv("DATABASE_URL", url)


async def _seed_org(engine: AsyncEngine, *, slug: str, workspace: str) -> uuid.UUID:
    org_id, workspace_id = uuid.uuid4(), uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
            {"id": org_id, "slug": slug},
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, :name, 'paper_trading')"
            ),
            {"id": workspace_id, "org": org_id, "name": workspace},
        )
    return org_id


async def _seed_member(engine: AsyncEngine, org_id: uuid.UUID, email: str) -> uuid.UUID:
    """A ``users`` row and its ``organization_members`` link — the shape
    ``paper_wallet_confirmation.resolve_actor`` looks for."""
    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO users (id, external_auth_id, email) VALUES (:id, :auth, :email)"),
            {"id": user_id, "auth": f"clerk_{user_id.hex}", "email": email},
        )
        await connection.execute(
            text(
                "INSERT INTO organization_members (organization_id, user_id, role, status) "
                "VALUES (:org, :user, 'OWNER', 'active')"
            ),
            {"org": org_id, "user": user_id},
        )
    return user_id


async def _table_count(engine: AsyncEngine, table: str, org_id: uuid.UUID) -> int:
    async with engine.connect() as connection:
        value = await connection.scalar(
            text(f"SELECT count(*) FROM {table} WHERE organization_id = :org"),  # noqa: S608
            {"org": org_id},
        )
    return int(value or 0)


async def _audit_row(engine: AsyncEngine, org_id: uuid.UUID, action: str) -> Any:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT actor_type, actor_id, metadata FROM audit_logs "
                    "WHERE organization_id = :org AND action = :action"
                ),
                {"org": org_id, "action": action},
            )
        ).one_or_none()


def _raw_ticker(rate: Decimal) -> dict[str, Any]:
    """A ``ticker/24hr`` body recent enough to pass the FX policy's age limits."""
    close_time_ms = int(time.time() * 1000)
    price = str(rate)
    return {
        "symbol": "USDTBRL",
        "closeTime": close_time_ms,
        "lastPrice": price,
        "bidPrice": price,
        "askPrice": price,
        "bidQty": "1",
        "askQty": "1",
        "volume": "1",
        "quoteVolume": "1",
        "highPrice": price,
        "lowPrice": price,
        "priceChangePercent": "0",
    }


def _args(
    *,
    org: str,
    workspace: str,
    fx_source: str,
    yes: str | None = None,
    actor: str | None = None,
    dry_run: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        org=org, workspace=workspace, fx_source=fx_source, yes=yes, actor=actor, dry_run=dry_run
    )


@pytest.fixture
def module(wallet_db_url: str, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    _use(wallet_db_url, monkeypatch)
    loaded = _load_script("open_paper_wallet")
    rate = Decimal("5.4321")

    async def _fake_fetch_quote(source: str) -> tuple[Decimal, dict[str, Any]]:
        assert source == loaded.SOURCE
        return rate, _raw_ticker(rate)

    monkeypatch.setattr(loaded, "fetch_quote", _fake_fetch_quote)
    return loaded


class TestWithoutYesNothingIsWritten:
    async def test_a_real_org_without_yes_writes_nothing(
        self, module: ModuleType, engine: AsyncEngine
    ) -> None:
        slug = f"t-{uuid.uuid4().hex[:8]}"
        org_id = await _seed_org(engine, slug=slug, workspace="principal")

        code = await module._run(_args(org=slug, workspace="principal", fx_source=module.SOURCE))

        assert code == 0
        assert await _table_count(engine, "portfolios", org_id) == 0
        assert await _table_count(engine, "portfolio_currency_anchor", org_id) == 0
        assert await _table_count(engine, "audit_logs", org_id) == 0


class TestWrongYesRefuses:
    async def test_yes_not_matching_org_refuses_and_writes_nothing(
        self, module: ModuleType, engine: AsyncEngine
    ) -> None:
        slug = f"t-{uuid.uuid4().hex[:8]}"
        org_id = await _seed_org(engine, slug=slug, workspace="principal")

        code = await module._run(
            _args(
                org=slug,
                workspace="principal",
                fx_source=module.SOURCE,
                yes="not-the-slug",
                actor="operator@example.com",
            )
        )

        assert code == 1
        assert await _table_count(engine, "portfolios", org_id) == 0

    async def test_yes_without_actor_refuses_before_any_lookup(
        self, module: ModuleType, engine: AsyncEngine
    ) -> None:
        slug = f"t-{uuid.uuid4().hex[:8]}"
        org_id = await _seed_org(engine, slug=slug, workspace="principal")

        code = await module._run(
            _args(org=slug, workspace="principal", fx_source=module.SOURCE, yes=slug, actor=None)
        )

        assert code == 1
        assert await _table_count(engine, "portfolios", org_id) == 0


class TestScopeViolationRollsBack:
    async def test_a_scope_mismatch_refuses_and_rolls_back_the_wallet(
        self, module: ModuleType, engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulates the exact defect ``verify_scope`` exists to catch: every
        write lands correctly, but the post-condition is fed a different
        organization than the one that actually owns the wallet."""
        from hunter_core.portfolio import opening as opening_module

        slug = f"t-{uuid.uuid4().hex[:8]}"
        org_id = await _seed_org(engine, slug=slug, workspace="principal")
        wrong_org = uuid.uuid4()
        real_verify_scope = opening_module._verify_scope  # pyright: ignore[reportPrivateUsage]

        async def _verify_against_wrong_org(
            session: Any, *, organization_id: uuid.UUID, **kwargs: Any
        ) -> None:
            await real_verify_scope(session, organization_id=wrong_org, **kwargs)

        # Patched where ``open_paper_wallet`` actually calls it
        # (``hunter_core.portfolio.opening``), not where ``verify_scope`` is
        # defined (``opening_scope``) — that module-level name is resolved
        # once at ``opening.py``'s own import time and a patch on
        # ``opening_scope`` alone would never be seen by ``open_paper_wallet``.
        monkeypatch.setattr(opening_module, "_verify_scope", _verify_against_wrong_org)

        code = await module._run(
            _args(
                org=slug,
                workspace="principal",
                fx_source=module.SOURCE,
                yes=slug,
                actor="operator@example.com",
            )
        )

        assert code == 1
        assert await _table_count(engine, "portfolios", org_id) == 0
        assert await _table_count(engine, "portfolio_currency_anchor", org_id) == 0
        assert await _table_count(engine, "portfolio_risk_state", org_id) == 0
        assert await _table_count(engine, "portfolio_equity_snapshots", org_id) == 0
        assert await _table_count(engine, "audit_logs", org_id) == 0


class TestActorAudit:
    async def test_an_existing_members_email_is_recorded_as_actor_type_user(
        self, module: ModuleType, engine: AsyncEngine
    ) -> None:
        slug = f"t-{uuid.uuid4().hex[:8]}"
        org_id = await _seed_org(engine, slug=slug, workspace="principal")
        user_id = await _seed_member(engine, org_id, "owner@example.com")

        code = await module._run(
            _args(
                org=slug,
                workspace="principal",
                fx_source=module.SOURCE,
                yes=slug,
                actor="owner@example.com",
            )
        )

        assert code == 0
        row = await _audit_row(engine, org_id, "portfolio.opened.confirmed_by")
        assert row is not None
        assert row.actor_type == "user"
        assert row.actor_id == user_id
        assert row.metadata["actor_input"] == "owner@example.com"
        assert "hostname" in row.metadata
        assert "os_user" in row.metadata

        opened = await _audit_row(engine, org_id, "portfolio.opened")
        assert opened is not None
        assert opened.actor_id == user_id

    async def test_free_text_actor_is_recorded_as_actor_type_system(
        self, module: ModuleType, engine: AsyncEngine
    ) -> None:
        slug = f"t-{uuid.uuid4().hex[:8]}"
        org_id = await _seed_org(engine, slug=slug, workspace="principal")

        code = await module._run(
            _args(
                org=slug,
                workspace="principal",
                fx_source=module.SOURCE,
                yes=slug,
                actor="everton (SSH bastion)",
            )
        )

        assert code == 0
        row = await _audit_row(engine, org_id, "portfolio.opened.confirmed_by")
        assert row is not None
        assert row.actor_type == "system"
        assert row.actor_id is None  # not a uuid; the text lives in metadata/action name
        assert row.metadata["actor_input"] == "everton (SSH bastion)"
