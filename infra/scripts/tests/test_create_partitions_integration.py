"""T2.5f against a real Postgres: the job provisions the recent past.

The unit tests next door prove what the job *plans*; this one proves what the
plan does to a database. Three properties, in the order an operator would check
them after a deploy:

1. a clean database (``alembic upgrade head``, nothing else) plus one run has a
   partition for every backward month the policy covers, on every monthly
   parent — not just on ``candles``;
2. running it again creates nothing (idempotent: ``CREATE TABLE IF NOT
   EXISTS``, unconditional ``REVOKE``, policies dropped before being created);
3. a candle timestamped **45 days ago** inserts. That is the failure this task
   exists to remove: before the backward horizon the insert raised ``no
   partition of relation "candles_1m" found for row`` and took the whole
   transaction — candles, outbox rows and the gap's own status — down with it.

Run:
    uv run pytest infra/scripts/tests/test_create_partitions_integration.py -q
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import monthly_partition_parents, partition_name
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.integration

SCRIPTS_DIR = Path(__file__).resolve().parents[1]


def _load_script(name: str) -> ModuleType:
    """Load ``infra/scripts/<name>.py`` the way running it as a script would."""
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


def _use(url: str) -> None:
    """Point the scripts' ``Settings()`` at this database."""
    os.environ["DATABASE_URL_MIGRATIONS"] = url


async def _run(url: str, work: Any) -> Any:
    engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as connection:
            return await work(connection)
    finally:
        await engine.dispose()


async def _partition_names(url: str) -> set[str]:
    async def _query(connection: AsyncConnection) -> set[str]:
        result = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "WHERE c.relispartition AND c.relnamespace = 'public'::regnamespace "
                # tables and partitioned tables only: a partitioned *index* is
                # also relispartition, and every new month brings one per index
                "AND c.relkind IN ('r', 'p')"
            )
        )
        return {row[0] for row in result}

    return await _run(url, _query)


async def _seed_market(url: str) -> UUID:
    """One exchange, two assets and a perpetual market — the FK a candle needs."""

    async def _insert(connection: AsyncConnection) -> UUID:
        exchange_id, base_id, quote_id, market_id = uuid7(), uuid7(), uuid7(), uuid7()
        await connection.execute(
            text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, :name)"),
            {"id": exchange_id, "code": "t25f", "name": "T2.5f"},
        )
        for asset_id, symbol in ((base_id, "T25FBASE"), (quote_id, "T25FQUOTE")):
            await connection.execute(
                text("INSERT INTO assets (id, symbol) VALUES (:id, :symbol)"),
                {"id": asset_id, "symbol": symbol},
            )
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, "
                "base_asset_id, quote_asset_id) VALUES (:id, :exchange_id, :symbol, "
                "'perpetual', :base_id, :quote_id)"
            ),
            {
                "id": market_id,
                "exchange_id": exchange_id,
                "symbol": "T25FUSDT",
                "base_id": base_id,
                "quote_id": quote_id,
            },
        )
        return market_id

    return await _run(url, _insert)


async def _insert_candle(url: str, market_id: UUID, open_time: datetime) -> None:
    async def _insert(connection: AsyncConnection) -> None:
        await connection.execute(
            text(
                "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, "
                "close, volume, is_final) VALUES (:market_id, '1m', :open_time, :price, "
                ":price, :price, :price, :volume, true)"
            ),
            {
                "market_id": market_id,
                "open_time": open_time,
                "price": Decimal("100.0000000000"),
                "volume": Decimal("1.0000000000"),
            },
        )

    await _run(url, _insert)


def _backward_months(
    partition_plan: ModuleType, owner: str, now: datetime, policy: dict[str, int | None]
) -> list[tuple[int, int]]:
    """The past months the plan wants for ``owner`` — the current one and ahead removed."""
    months = partition_plan.planned_months(owner, 3, 2, now, policy)
    return [(year, month) for year, month in months if (year, month) < (now.year, now.month)]


def test_a_clean_database_gains_the_backward_months_for_every_monthly_parent(
    migrated_db_url: str,
) -> None:
    """Property 1 and 2 in one pass: everything planned exists, and a second run is a no-op."""
    _use(migrated_db_url)
    create_partitions = _load_script("create_partitions")
    partition_plan = _load_script("partition_plan")
    partition_retention = _load_script("partition_retention")
    now = datetime.now(UTC)
    policy = partition_retention.retention_days()

    before = asyncio.run(_partition_names(migrated_db_url))
    groups = create_partitions.planned_groups(3, now)
    created: list[str] = asyncio.run(create_partitions.ensure_partitions(groups))
    after = asyncio.run(_partition_names(migrated_db_url))

    assert set(created) == after - before
    for owner in monthly_partition_parents():
        expected = partition_plan.planned_months(
            owner, 3, create_partitions.DEFAULT_MONTHS_BEHIND, now, policy
        )
        behind = [
            (year, month) for year, month in expected if (year, month) < (now.year, now.month)
        ]
        # No ``assert behind`` per owner, and that is the policy, not a
        # weakening (Astra's review of this diff): a parent whose retention
        # window has already passed — ``feature_snapshots``, 14 days, after the
        # 15th of a month — is *supposed* to get no backward month at all.
        # Demanding one would have made this test fail on a date, not on a bug.
        for year, month in behind:
            assert partition_name(owner, year, month) in after
    # ``candles_1m`` is the one parent that must always have both months back:
    # it is what the backfill writes and its 90 days always cover them (the
    # upper bound of the month before last is at most ~62 days old).
    assert len(_backward_months(partition_plan, "candles_1m", now, policy)) == 2

    created_again: list[str] = asyncio.run(
        create_partitions.ensure_partitions(create_partitions.planned_groups(3, now))
    )
    assert created_again == []
    assert asyncio.run(_partition_names(migrated_db_url)) == after


def test_a_candle_from_45_days_ago_can_be_stored(migrated_db_url: str) -> None:
    """Property 3 — the reason the task exists.

    45 days is inside the 7-day bootstrap window only by accident; it is the
    number that proves the *month* boundary was crossed, which is what the
    backfill consumer refused on (``market_backfill_refused
    reason=no_partition``). ``candles_1m`` keeps 90 days, so retention never
    trims this month away.
    """
    _use(migrated_db_url)
    create_partitions = _load_script("create_partitions")
    now = datetime.now(UTC)
    asyncio.run(create_partitions.ensure_partitions(create_partitions.planned_groups(3, now)))

    market_id = asyncio.run(_seed_market(migrated_db_url))
    open_time = (now - timedelta(days=45)).replace(second=0, microsecond=0)
    asyncio.run(_insert_candle(migrated_db_url, market_id, open_time))

    async def _count(connection: AsyncConnection) -> int:
        value = await connection.scalar(
            text("SELECT count(*) FROM candles WHERE market_id = :id"), {"id": market_id}
        )
        return int(value or 0)

    assert asyncio.run(_run(migrated_db_url, _count)) == 1


def test_the_backward_months_are_hardened_like_every_other_partition(
    migrated_db_url: str,
) -> None:
    """A partition created for the past is no more reachable than one for the future.

    DATABASE.md §1.3: privileges and policies are not inherited from a
    partitioned parent, so every child is created with ``REVOKE ALL`` for both
    application roles and — for a child of a tenant parent — RLS enabled,
    forced and policed on the child itself.
    """
    _use(migrated_db_url)
    create_partitions = _load_script("create_partitions")
    now = datetime.now(UTC)
    asyncio.run(create_partitions.ensure_partitions(create_partitions.planned_groups(3, now)))
    previous = (now.replace(day=1) - timedelta(days=1)).replace(day=1)

    async def _inspect(connection: AsyncConnection) -> tuple[list[str], list[str]]:
        granted = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "WHERE c.relispartition AND c.relnamespace = 'public'::regnamespace "
                "AND c.relname LIKE :suffix AND ("
                "  has_table_privilege('hunter_app', c.oid, 'SELECT')"
                "  OR has_table_privilege('hunter_worker', c.oid, 'SELECT'))"
            ),
            {"suffix": f"%{previous.year:04d}_{previous.month:02d}"},
        )
        unforced = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c "
                "JOIN pg_attribute a ON a.attrelid = c.oid "
                "WHERE c.relispartition AND c.relnamespace = 'public'::regnamespace "
                "AND c.relname LIKE :suffix AND a.attname = 'organization_id' "
                "AND NOT a.attisdropped "
                "AND NOT (c.relrowsecurity AND c.relforcerowsecurity)"
            ),
            {"suffix": f"%{previous.year:04d}_{previous.month:02d}"},
        )
        return [row[0] for row in granted], [row[0] for row in unforced]

    directly_granted, unforced_tenant_children = asyncio.run(_run(migrated_db_url, _inspect))

    assert directly_granted == []
    assert unforced_tenant_children == []
