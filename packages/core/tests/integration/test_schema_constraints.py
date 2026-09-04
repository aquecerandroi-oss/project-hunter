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
    assert partition == "candles_5m_2026_10"


async def test_two_timeframes_of_the_same_minute_land_in_different_partitions(
    schema_engine: AsyncEngine, market_id: str
) -> None:
    """``LIST (timeframe)`` then ``RANGE (open_time)`` — DATABASE.md §1.3.

    This is what makes retention per timeframe possible at all: dropping 1m at 90
    days is ``DROP TABLE candles_1m_2026_05``, which cannot touch the 1h series
    that is kept forever. Under the previous single monthly RANGE both rows lived
    in ``candles_2026_10`` and only a row-by-row ``DELETE`` could separate them.
    """
    open_time = datetime(2026, 11, 3, 8, 0, tzinfo=UTC)
    async with schema_engine.begin() as connection:
        for timeframe in ("1m", "1h"):
            await connection.execute(
                text(
                    "INSERT INTO candles (market_id, timeframe, open_time, open, high, low, "
                    "close, volume) VALUES (:m, :tf, :t, 1, 1, 1, 1, 1)"
                ),
                {"m": market_id, "tf": timeframe, "t": open_time},
            )
        result = await connection.execute(
            text(
                "SELECT timeframe, tableoid::regclass::text FROM candles "
                "WHERE market_id = :m AND open_time = :t ORDER BY timeframe"
            ),
            {"m": market_id, "t": open_time},
        )
        landed = {row[0]: row[1] for row in result}

    assert landed == {"1m": "candles_1m_2026_11", "1h": "candles_1h_2026_11"}


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


@pytest_asyncio.fixture
async def portfolios(schema_engine: AsyncEngine) -> tuple[str, str, str, str]:
    """``(org A, portfolio A, org B, portfolio B)`` — two tenants, one portfolio each."""
    created: list[tuple[uuid.UUID, uuid.UUID]] = []
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_worker TO CURRENT_USER"))
        for _ in range(2):
            org, workspace, portfolio = uuid7(), uuid7(), uuid7()
            await connection.execute(
                text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, 'fk')"),
                {"id": org, "slug": f"fk-{uuid.uuid4().hex[:8]}"},
            )
            await connection.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, objective) "
                    "VALUES (:id, :org, 'ws', 'explore')"
                ),
                {"id": workspace, "org": org},
            )
            await connection.execute(
                text(
                    "INSERT INTO portfolios (id, organization_id, workspace_id, name, "
                    "initial_capital) VALUES (:id, :org, :ws, 'pf', 1000)"
                ),
                {"id": portfolio, "org": org, "ws": workspace},
            )
            created.append((org, portfolio))
    (org_a, pf_a), (org_b, pf_b) = created
    return str(org_a), str(pf_a), str(org_b), str(pf_b)


async def test_a_position_cannot_point_at_another_organizations_portfolio(
    schema_engine: AsyncEngine, market_id: str, portfolios: tuple[str, str, str, str]
) -> None:
    """The composite FK, exercised as ``hunter_worker`` — the role with BYPASSRLS.

    RLS is not a defence here: the worker legitimately scans every organization,
    and the row's own ``organization_id`` is the only thing a single-column
    ``portfolio_id`` foreign key would ever check. Keying it on
    ``(portfolio_id, organization_id) -> portfolios(id, organization_id)`` is what
    makes the mismatch unrepresentable.
    """
    org_a, _pf_a, org_b, pf_b = portfolios
    insert = text(
        "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
        "qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'long', 1, 100)"
    )

    with pytest.raises(IntegrityError, match="fk_positions_portfolio_id_portfolios"):
        async with schema_engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE hunter_worker"))
            await connection.execute(
                insert, {"id": uuid7(), "org": org_a, "pf": pf_b, "m": market_id}
            )

    async with schema_engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(insert, {"id": uuid7(), "org": org_b, "pf": pf_b, "m": market_id})


async def test_an_order_cannot_be_filled_beyond_its_own_quantity(
    schema_engine: AsyncEngine, market_id: str, portfolios: tuple[str, str, str, str]
) -> None:
    """``filled_qty <= qty`` — an over-fill is an accounting error, not a state."""
    org_a, pf_a, _org_b, _pf_b = portfolios
    insert = text(
        "INSERT INTO orders (id, organization_id, portfolio_id, market_id, client_order_id, "
        "side, type, purpose, qty, filled_qty) "
        "VALUES (:id, :org, :pf, :m, :coid, 'buy', 'market', 'entry', :qty, :filled)"
    )
    params = {"org": org_a, "pf": pf_a, "m": market_id}

    with pytest.raises(IntegrityError, match="ck_orders_filled_qty_within_qty"):
        async with schema_engine.begin() as connection:
            await connection.execute(
                insert, {**params, "id": uuid7(), "coid": "over", "qty": 2, "filled": 3}
            )

    async with schema_engine.begin() as connection:
        await connection.execute(
            insert, {**params, "id": uuid7(), "coid": "exact", "qty": 2, "filled": 2}
        )


async def test_a_system_kill_switch_row_can_never_carry_an_organization(
    schema_engine: AsyncEngine, portfolios: tuple[str, str, str, str]
) -> None:
    """``(scope = 'system') = (organization_id IS NULL)``.

    The invariant the ``system_scope_readable`` policy leans on: that policy
    publishes every ``system`` row to every tenant, so a ``system`` row carrying
    an organization would be a cross-tenant leak by construction.
    """
    org_a, _pf_a, _org_b, _pf_b = portfolios
    insert = text(
        "INSERT INTO kill_switch_transitions "
        "(id, organization_id, scope, from_state, to_state, actor_type) "
        "VALUES (:id, :org, :scope, 'ACTIVE', 'WARNING', 'system')"
    )
    invariant = "ck_kill_switch_transitions_system_scope_has_no_org"

    with pytest.raises(IntegrityError, match=invariant):
        async with schema_engine.begin() as connection:
            await connection.execute(insert, {"id": uuid7(), "org": org_a, "scope": "system"})

    with pytest.raises(IntegrityError, match=invariant):
        async with schema_engine.begin() as connection:
            await connection.execute(insert, {"id": uuid7(), "org": None, "scope": "organization"})

    async with schema_engine.begin() as connection:
        await connection.execute(insert, {"id": uuid7(), "org": None, "scope": "system"})
        await connection.execute(insert, {"id": uuid7(), "org": org_a, "scope": "organization"})


async def test_funding_rates_keep_full_numeric_precision(schema_engine: AsyncEngine) -> None:
    """A funding rate is money-shaped, not a percentage — DATABASE.md §15.

    ``NUMERIC(9,6)`` rounded a 0.0000125 rate to 0.000013, and anything below
    5e-7 to zero — which is most of them.
    """
    async with schema_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT table_name, numeric_precision, numeric_scale "
                "FROM information_schema.columns WHERE table_schema = 'public' "
                "AND (table_name, column_name) IN "
                "(('market_snapshots', 'funding_rate'), ('funding_rates', 'rate'))"
            )
        )
        rows = {row[0]: (row[1], row[2]) for row in result}

    assert rows == {"market_snapshots": (28, 10), "funding_rates": (28, 10)}


async def test_every_hot_foreign_key_column_is_indexed(schema_engine: AsyncEngine) -> None:
    """ "todo FK indexado" (DATABASE.md §1), for the columns the review named.

    A composite ``(portfolio_id, organization_id)`` index would serve these as a
    leading column, so the assertion is on the *first* indexed column rather than
    on an index of exactly one column.
    """
    expected = {
        "agents": "portfolio_id",
        "positions": "portfolio_id",
        "trade_proposals": "portfolio_id",
        "trades": "portfolio_id",
        "fills": "portfolio_id",
        "notifications": "user_id",
    }
    async with schema_engine.connect() as connection:
        missing: list[str] = []
        for table, column in expected.items():
            covered = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_index i "
                    "JOIN pg_class c ON c.oid = i.indrelid "
                    "JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = i.indkey[0] "
                    "WHERE c.relname = :t AND a.attname = :col"
                ),
                {"t": table, "col": column},
            )
            if not covered:
                missing.append(f"{table}.{column}")
    assert missing == [], f"foreign key columns with no index leading on them: {missing}"


async def test_a_position_quantity_can_never_go_negative(
    schema_engine: AsyncEngine, market_id: str, portfolios: tuple[str, str, str, str]
) -> None:
    """``positions.qty >= 0`` — DATABASE.md §15.8.

    Zero is legal (a position being closed passes through it before it becomes a
    ``trade``); below zero is an accounting impossibility that would flip the
    sign of every exposure and drawdown computed from it. A short is expressed by
    ``direction``, never by a negative quantity.
    """
    _org_a, _pf_a, org_b, pf_b = portfolios
    insert = text(
        "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
        "qty, avg_entry_price) VALUES (:id, :org, :pf, :m, 'short', :qty, 100)"
    )
    params = {"org": org_b, "pf": pf_b, "m": market_id}

    with pytest.raises(IntegrityError, match="ck_positions_qty_non_negative"):
        async with schema_engine.begin() as connection:
            await connection.execute(text("SET LOCAL ROLE hunter_worker"))
            await connection.execute(insert, {**params, "id": uuid7(), "qty": -1})

    async with schema_engine.begin() as connection:
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        await connection.execute(insert, {**params, "id": uuid7(), "qty": 0})
