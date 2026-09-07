"""Shared plumbing for the T04 schema tests: Alembic wiring and per-test databases.

Builds on the session-scoped ``postgres_container`` fixture from
``packages/core/tests/conftest.py``. Each schema test group gets its own
*database* inside that one container so a ``downgrade base`` in one test cannot
pull the schema out from under another. Roles are cluster-wide and shared, which
is exactly how a real deployment looks.
"""

from __future__ import annotations

import asyncio
import importlib
import itertools
import os
import sys
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = REPO_ROOT / "infra" / "scripts"


def async_engine(url: str) -> AsyncEngine:
    """An engine safe behind a transaction pooler (no prepared statement cache)."""
    return create_async_engine(url, connect_args={"statement_cache_size": 0})


def alembic_config(url: str) -> Config:
    """An Alembic ``Config`` pointed at ``url``.

    ``env.py`` reads the URL from ``Settings().database_url_migrations``, so the
    environment variable is what actually selects the database; setting it here
    keeps the two in one place.
    """
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


async def create_database(admin_url: str, name: str) -> str:
    """Create ``name`` in the same cluster as ``admin_url`` and return its URL."""
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


def migration_ddl(name: str) -> ModuleType:
    """Import ``infra/migrations/ddl/<name>.py``.

    Only importable once :func:`alembic_config` has put ``infra/migrations`` on
    ``sys.path`` — the same way Alembic itself reaches these modules.
    """
    return importlib.import_module(f"ddl.{name}")


@pytest.fixture(scope="session")
def container_url(postgres_container: PostgresContainer) -> str:
    """The asyncpg URL of the session's Postgres container."""
    return postgres_container.get_connection_url()


@pytest.fixture(scope="session")
def migrated_schema_db(container_url: str) -> Iterator[str]:
    """A database with ``0001_initial_schema`` applied, for the RLS/constraint tests.

    Sync on purpose: ``env.py`` calls ``asyncio.run``, which cannot run inside an
    already-running event loop, and a module/session scoped async fixture would
    need its own loop scope for no benefit.
    """
    url = asyncio.run(create_database(container_url, "hunter_schema"))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def schema_engine(migrated_schema_db: str) -> AsyncIterator[AsyncEngine]:
    """An engine on the migrated schema database, connected as the container owner."""
    engine = async_engine(migrated_schema_db)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def paper_ledger_db(container_url: str) -> Iterator[str]:
    """A database of its own with every migration applied, for the T3.3 ledger.

    Separate from ``migrated_schema_db`` because the ledger tests *write* the
    paper wallet's tables, and a wallet is unique per ``(organization,
    workspace)`` for ever: sharing a database with the schema tests would let
    one module's opening decide another module's ``WalletAlreadyOpen``.
    """
    url = asyncio.run(create_database(container_url, "hunter_paper_ledger"))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def ledger_engine(paper_ledger_db: str) -> AsyncIterator[AsyncEngine]:
    """An engine on the ledger database, connected as the container owner."""
    engine = async_engine(paper_ledger_db)
    try:
        yield engine
    finally:
        await engine.dispose()


class LedgerTenant:
    """One organization, workspace, exchange and SPOT market, freshly created.

    Built as the container owner (which RLS does not constrain) so that the code
    under test is the only thing that ever runs as ``hunter_app`` — every tenant
    read and write in the ledger tests then goes through the real policies.
    """

    def __init__(self, slug: str) -> None:
        from hunter_core.domain.types import uuid7

        self.slug = slug
        self.org_id = uuid7()
        self.workspace_id = uuid7()
        self.exchange_id = uuid7()
        self.market_id = uuid7()
        self.base_asset_id = uuid7()
        self.quote_asset_id = uuid7()
        self.symbol = f"HTR{slug[:6].upper()}USDT"
        self.base_symbol = f"HTR{slug[:6].upper()}"


@pytest_asyncio.fixture
async def ledger_tenant(ledger_engine: AsyncEngine) -> LedgerTenant:
    """A tenant with a market to trade, unique per test.

    ``USDT`` is created once and shared: ``assets.symbol`` is globally unique,
    and the operating currency of every wallet is the same asset.
    """
    import uuid as _uuid

    tenant = LedgerTenant(_uuid.uuid4().hex[:8])
    params = {
        "org": tenant.org_id,
        "ws": tenant.workspace_id,
        "ex": tenant.exchange_id,
        "market": tenant.market_id,
        "base": tenant.base_asset_id,
        "quote": tenant.quote_asset_id,
        "slug": tenant.slug,
        "symbol": tenant.symbol,
        "base_symbol": tenant.base_symbol,
    }
    async with ledger_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:org, :slug, :slug)"), params
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:ws, :org, :slug, 'paper_trading')"
            ),
            params,
        )
        await connection.execute(
            text("INSERT INTO exchanges (id, code, name) VALUES (:ex, :slug, 'Ledger probe')"),
            params,
        )
        await connection.execute(
            text("INSERT INTO assets (id, symbol) VALUES (:base, :base_symbol)"), params
        )
        await connection.execute(
            text(
                "INSERT INTO assets (id, symbol) VALUES (:quote, 'USDT') "
                "ON CONFLICT (symbol) DO NOTHING"
            ),
            params,
        )
        quote_id = await connection.scalar(text("SELECT id FROM assets WHERE symbol = 'USDT'"))
        tenant.quote_asset_id = quote_id
        params["quote"] = quote_id
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, base_asset_id, "
                "quote_asset_id) VALUES (:market, :ex, :symbol, 'spot', :base, :quote)"
            ),
            params,
        )
    return tenant


_FX_JITTER = itertools.count(1)
"""``uq_fx_observations_observation`` is ``(pair, source, observed_at)`` and the
table is immutable by trigger, so two ledger tests asking for "a rate at noon"
would collide — and they do collide when the two modules run in one process.
One counter for the whole session, a few microseconds *backwards* each time, so
no observation ever lands ahead of the instant that consumes it and no age
crosses a policy limit."""


@pytest.fixture
def observe_fx(
    ledger_engine: AsyncEngine,
) -> Callable[..., Awaitable[uuid.UUID]]:
    """Persist one ``fx_observations`` row, as the collector of T3.11 would."""
    from hunter_core.domain.types import uuid7
    from hunter_core.portfolio.opening import PAPER_FX_POLICY

    async def _observe(
        *,
        rate: Decimal = Decimal("5.4321"),
        pair: str = PAPER_FX_POLICY.pair,
        source: str = PAPER_FX_POLICY.source,
        observed_at: datetime,
        available_at: datetime | None = None,
    ) -> uuid.UUID:
        observation_id = uuid7()
        offset = timedelta(microseconds=next(_FX_JITTER))
        async with ledger_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                    "available_at) VALUES (:id, :pair, :rate, :source, :observed, :available)"
                ),
                {
                    "id": observation_id,
                    "pair": pair,
                    "rate": rate,
                    "source": source,
                    "observed": observed_at - offset,
                    "available": (available_at or observed_at) - offset,
                },
            )
        return observation_id

    return _observe
