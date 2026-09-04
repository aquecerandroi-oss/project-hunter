"""The constraints the product depends on, asserted against a real Postgres.

- ``exchange_connections.withdraw_enabled`` can never be true (SECURITY.md §4);
- money survives a round trip at full ``NUMERIC(28,10)`` precision, so a
  ``Decimal`` never silently becomes a float;
- rows land in the right monthly partition, and a row outside every declared
  partition is refused rather than lost.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.domain.types import uuid7

pytestmark = pytest.mark.integration

_SMALLEST = Decimal("0.0000000001")  # 1e-10, the last digit NUMERIC(28,10) can hold


@pytest_asyncio.fixture
async def market_id(schema_engine: AsyncEngine) -> str:
    """A market to hang candles off, with its exchange."""
    exchange_id, market = uuid7(), uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Binance')"),
            {"id": exchange_id, "code": f"binance-{uuid.uuid4().hex[:8]}"},
        )
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                "VALUES (:id, :ex, 'BTCUSDT', 'perpetual')"
            ),
            {"id": market, "ex": exchange_id},
        )
    return str(market)


@pytest_asyncio.fixture
async def organization_id(schema_engine: AsyncEngine) -> str:
    org = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, 'ck')"),
            {"id": org, "slug": f"ck-{uuid.uuid4().hex[:8]}"},
        )
    return str(org)


async def test_withdraw_enabled_true_is_rejected(
    schema_engine: AsyncEngine, organization_id: str
) -> None:
    """A key with withdrawal permission is never persisted as usable."""
    exchange_id = uuid7()
    async with schema_engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Bybit')"),
            {"id": exchange_id, "code": f"bybit-{uuid.uuid4().hex[:8]}"},
        )

    with pytest.raises(IntegrityError, match="ck_exchange_connections_withdraw_disabled"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO exchange_connections "
                    "(id, organization_id, exchange_id, label, withdraw_enabled) "
                    "VALUES (:id, :org, :ex, 'main', true)"
                ),
                {"id": uuid7(), "org": organization_id, "ex": exchange_id},
            )

    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO exchange_connections "
                "(id, organization_id, exchange_id, label, withdraw_enabled) "
                "VALUES (:id, :org, :ex, 'main', false)"
            ),
            {"id": uuid7(), "org": organization_id, "ex": exchange_id},
        )


async def test_numeric_28_10_round_trips_the_smallest_representable_amount(
    schema_engine: AsyncEngine, market_id: str
) -> None:
    open_time = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, close, "
                "volume) VALUES (:m, '1m', :t, :v, :v, :v, :v, :v)"
            ),
            {"m": market_id, "t": open_time, "v": _SMALLEST},
        )
        stored = await connection.scalar(
            text("SELECT close FROM candles WHERE market_id = :m AND open_time = :t"),
            {"m": market_id, "t": open_time},
        )

    # asyncpg hands back a Decimal (never a float) and the tenth decimal place
    # survived: a NUMERIC with a smaller scale would have rounded this to zero.
    assert isinstance(stored, Decimal)
    assert stored == _SMALLEST
    assert stored != Decimal(0)


async def test_a_candle_lands_in_the_partition_for_its_month(
    schema_engine: AsyncEngine, market_id: str
) -> None:
    open_time = datetime(2026, 10, 17, 9, 30, tzinfo=UTC)
    async with schema_engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, close, "
                "volume) VALUES (:m, '5m', :t, 1, 1, 1, 1, 1)"
            ),
            {"m": market_id, "t": open_time},
        )
        partition = await connection.scalar(
            text(
                "SELECT tableoid::regclass::text FROM candles "
                "WHERE market_id = :m AND open_time = :t AND timeframe = '5m'"
            ),
            {"m": market_id, "t": open_time},
        )
    assert partition == "candles_2026_10"


async def test_a_candle_outside_every_partition_is_refused(
    schema_engine: AsyncEngine, market_id: str
) -> None:
    """A missing partition must fail loudly — DATABASE.md §1.3 makes it a
    `critical` system event, never a silently dropped row.
    """
    with pytest.raises(IntegrityError, match="no partition of relation"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, "
                    "close, volume) VALUES (:m, '1h', :t, 1, 1, 1, 1, 1)"
                ),
                {"m": market_id, "t": datetime(2019, 1, 1, tzinfo=UTC)},
            )


async def test_money_columns_are_numeric_28_10(schema_engine: AsyncEngine) -> None:
    """Spot-check the contract across the tables that hold money."""
    async with schema_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT table_name, column_name, numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_schema = 'public' AND column_name "
                "IN ('initial_capital', 'entry_price', 'exit_price', 'pnl', 'equity', 'cash')"
            )
        )
        rows = list(result)

    assert rows
    for table, column, precision, scale in rows:
        assert (precision, scale) == (28, 10), f"{table}.{column} is NUMERIC({precision},{scale})"
