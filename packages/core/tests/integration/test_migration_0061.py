"""``0061_spot_desk_r71`` (R71), the ``test_migration_0057.py`` shape: chain and
slug; the seed constant is R71's measurement (six markets the Lab's
``mean_reversion`` family signalled and the map did not cover), with ``enabled``
derived from ``0057``'s own rule *minus* the two rows R71 holds back by name;
56 rows and 38 enabled after the upgrade; the mints in the database are the
mints in the constant; the insert is idempotent and never overwrites a row an
operator has edited; the downgrade refuses while a ``spot_orders`` or a
``spot_positions`` row names one of the six and otherwise removes exactly those
six, leaving ``0057``'s fifty untouched (§17.7).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from decimal import Decimal

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.domain.types import uuid7

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0061_spot_desk_r71"
PREVIOUS = "0060_meme_refused_probe_arm"
SEEDED_BY_0057, ENABLED_BY_0057 = 50, 35
NEW_ROWS, NEW_ENABLED = 6, 3
TOTAL_ROWS, TOTAL_ENABLED = SEEDED_BY_0057 + NEW_ROWS, ENABLED_BY_0057 + NEW_ENABLED
HELD = frozenset({"XRPUSDT", "BIRBUSDT"})
_BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_REVISION = "SELECT version_num FROM alembic_version"
_NEAR = "3ZLekZYq2qkZiSpnSvabjit34tUkjSwD1JFuW9as9wBG"
_WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
"""``0057``'s WIF row — the market this revision must **not** remove."""

_AN_ORDER = (
    "INSERT INTO spot_orders (id, signal_id, market_symbol, mint, side, client_order_id, status) "
    "VALUES (:id, :signal, :market, :mint, 'buy', :key, 'admitted')"
)
_A_POSITION = (
    "INSERT INTO spot_positions (id, signal_id, entry_order_id, market_symbol, mint, entry_at, "
    "  entry, tokens, sol_spent_lamports, initial_risk_sol, params) "
    "VALUES (:id, :signal, :order, 'NEARUSDT', :mint, now() - interval '1 minute', "
    "  '{}'::jsonb, 1000, 50000000, 0.0005, '{}'::jsonb)"
)
_CLEAN: tuple[str, ...] = (
    "DELETE FROM spot_positions",
    "DELETE FROM spot_orders",
    "DELETE FROM agent_signals WHERE params_hash = 'spot_desk_0061'",
)
_SIGNAL_ROWS: tuple[str, ...] = (
    "INSERT INTO strategies (id, key, name) VALUES (:strategy, :key, 'spot desk 0061')",
    "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:version, :strategy, 'v14')",
    "INSERT INTO exchanges (id, code, name) VALUES (:exchange, :key, 'spot desk 0061')",
    "INSERT INTO markets (id, exchange_id, symbol, market_type) "
    "VALUES (:market, :exchange, 'NEARUSDT', 'perpetual')",
    "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, direction, "
    "confidence) VALUES (:signal, :version, :market, 'spot_desk_0061', 'long', 0.5)",
)


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0061"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head`` (the ``0057`` argument)."""
    command.upgrade(alembic_config(db_url), REVISION)
    yield db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _run(engine: AsyncEngine, statements: list[tuple[str, dict[str, object]]]) -> None:
    async with engine.begin() as connection:
        for statement, parameters in statements:
            await connection.execute(text(statement), parameters)


async def _signal(engine: AsyncEngine) -> str:
    ids = {name: str(uuid7()) for name in ("strategy", "version", "exchange", "market", "signal")}
    params: dict[str, object] = {**ids, "key": f"spot0061-{uuid.uuid4().hex[:8]}"}
    await _run(engine, [(statement, params) for statement in _SIGNAL_ROWS])
    return ids["signal"]


async def _clean(engine: AsyncEngine) -> None:
    await _run(engine, [(statement, {}) for statement in _CLEAN])


async def _once[T](url: str, step: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    created = async_engine(url)
    try:
        return await step(created)
    finally:
        await created.dispose()


async def _scalar(engine: AsyncEngine, statement: str) -> object:
    async with engine.connect() as connection:
        return await connection.scalar(text(statement))


def _scalar_of(url: str, statement: str) -> object:
    return asyncio.run(_once(url, lambda e: _scalar(e, statement)))


def test_the_revision_lands_on_0060_and_fits_the_version_column() -> None:
    source = REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py"
    assert f'down_revision: str | None = "{PREVIOUS}"' in source.read_text(encoding="utf-8")
    assert len(REVISION) <= 32


def test_the_seed_constant_is_r71s_measurement_and_holds_two_rows_back() -> None:
    """Pure: six new markets, none of them already in ``0057``'s fifty, base58
    mints, ``enabled`` = ``0057``'s rule AND not held back by name, every row
    carrying the note that says where its identity came from."""
    r71 = migration_ddl("spot_desk_r71")
    seed_0057 = migration_ddl("spot_desk_seed")
    kinds = migration_ddl("spot_desk").SPOT_MARKET_KINDS_0057
    rows = r71.seed_rows_0061()
    old = {row.binance_symbol for row in seed_0057.seed_rows()}
    symbols = [row.binance_symbol for row in rows]
    assert len(rows) == NEW_ROWS and len(set(symbols)) == NEW_ROWS
    assert not (set(symbols) & old), "0061 re-seeds a market 0057 already planted"
    assert set(r71.HELD_FOR_REVIEW_0061) == HELD
    for row in rows:
        assert row.binance_symbol.endswith("USDT") and row.base == row.binance_symbol[:-4]
        assert _BASE58.match(row.mint), row
        assert row.units_per_binance_unit == 1
        assert row.kind in kinds and row.tier in ("A", "B", "C")
        assert row.enabled == (
            seed_0057.is_enabled_at_seed(row.tier, row.round_trip_cost_pct_at_seed)
            and row.binance_symbol not in HELD
        )
        assert r71.seed_note(row.binance_symbol), row
    assert sum(1 for row in rows if row.enabled) == NEW_ENABLED
    assert {row.binance_symbol for row in rows if not row.enabled} == {*HELD, "SLXUSDT"}


def test_the_measured_numbers_are_the_ones_r71_reported() -> None:
    """The four numbers that decide money: mint, tier, liquidity and the round
    trip as a **fraction** (0,00312 = 0,312 %), R63 §2a's convention."""
    rows = {row.binance_symbol: row for row in migration_ddl("spot_desk_r71").seed_rows_0061()}
    assert rows["NEARUSDT"].mint == _NEAR
    assert (rows["NEARUSDT"].kind, rows["NEARUSDT"].tier) == ("ponte", "A")
    assert rows["NEARUSDT"].round_trip_cost_pct_at_seed == Decimal("0.001442")
    assert rows["NEARUSDT"].liquidity_usd_at_seed == 1955016
    assert rows["XRPUSDT"].mint == "6UpQcMAb5xMzxc7ZfPaVMgx3KqsvKZdT5U718BzD5We2"
    assert rows["XRPUSDT"].tier == "A" and not rows["XRPUSDT"].enabled, "held: freeze authority"
    assert rows["BTCUSDT"].mint == "3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh"
    assert rows["BTCUSDT"].kind == "ponte" and rows["BTCUSDT"].enabled
    assert rows["SLXUSDT"].tier == "C" and not rows["SLXUSDT"].enabled, "tier C stays off"
    assert rows["SLXUSDT"].mint == "SLXdx4BUt2v9uJQNzWqSfzTJ9UKLUDsvxHFMEEdrfgq"
    assert rows["ORCAUSDT"].mint == "orcaEKTdK7LKz57vaAYr9QeNsVEPfiu6QeMU1kektZE"
    assert rows["BIRBUSDT"].mint == "G7vQWurMkMMm2dU3iZpXYFTHT9Biio4F4gZCrwFpKNwG"


async def test_the_map_grows_to_fifty_six_markets_with_thirty_eight_enabled(
    engine: AsyncEngine,
) -> None:
    """The count, the enabled count, and — the assertion that costs money if it
    fails — every new mint in the database is the mint in the constant."""
    rows = {row.binance_symbol: row for row in migration_ddl("spot_desk_r71").seed_rows_0061()}
    writer = migration_ddl("spot_desk_r71").SEED_WRITER_0061
    async with engine.connect() as connection:
        counts = (
            await connection.execute(
                text(
                    "SELECT count(*), count(*) FILTER (WHERE enabled), "
                    "count(*) FILTER (WHERE decimals IS NOT NULL) FROM spot_desk_markets"
                )
            )
        ).one()
        planted = {
            row[0]: tuple(row[1:])
            for row in await connection.execute(
                text(
                    "SELECT binance_symbol, base, mint, units_per_binance_unit, kind, tier, "
                    "  enabled, liquidity_usd_at_seed, round_trip_cost_pct_at_seed, note, "
                    "  updated_by FROM spot_desk_markets WHERE updated_by = :writer"
                ),
                {"writer": writer},
            )
        }
    assert tuple(counts) == (TOTAL_ROWS, TOTAL_ENABLED, 0)
    assert set(planted) == set(rows)
    for symbol, seeded in rows.items():
        assert planted[symbol] == (
            seeded.base,
            seeded.mint,
            Decimal(seeded.units_per_binance_unit),
            seeded.kind,
            seeded.tier,
            seeded.enabled,
            Decimal(seeded.liquidity_usd_at_seed),
            seeded.round_trip_cost_pct_at_seed,
            migration_ddl("spot_desk_r71").seed_note(symbol),
            writer,
        )


async def test_re_running_the_insert_never_overwrites_an_operator_row(engine: AsyncEngine) -> None:
    """``ON CONFLICT (binance_symbol) DO NOTHING``: an operator who enabled
    ``XRPUSDT`` with the audited script keeps his row if the seed runs again."""
    r71 = migration_ddl("spot_desk_r71")
    operator = (
        "UPDATE spot_desk_markets SET enabled = true, updated_by = 'operator:test' "
        "WHERE binance_symbol = 'XRPUSDT'"
    )
    try:
        await _run(engine, [(operator, {})])
        async with engine.begin() as connection:
            await connection.execute(r71.SPOT_DESK_R71_INSERT, r71.seed_parameters())
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT enabled, updated_by FROM spot_desk_markets "
                        "WHERE binance_symbol = 'XRPUSDT'"
                    )
                )
            ).one()
            total = await connection.scalar(text("SELECT count(*) FROM spot_desk_markets"))
        assert tuple(row) == (True, "operator:test")
        assert total == TOTAL_ROWS, "a re-run inserted a duplicate"
    finally:
        await _run(
            engine,
            [
                (
                    "UPDATE spot_desk_markets SET enabled = false, updated_by = :writer "
                    "WHERE binance_symbol = 'XRPUSDT'",
                    {"writer": r71.SEED_WRITER_0061},
                )
            ],
        )


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken to ``head``."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0061_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_under_a_spot_row_and_otherwise_removes_only_its_six(
    upgraded: str,
) -> None:
    """§17.7: an order or a position naming one of the six blocks the downgrade
    and nothing commits; with them gone the six rows leave and ``0057``'s fifty
    stay, with the 35 the older revision enabled."""
    config = alembic_config(upgraded)

    def _buy(signal: str, market: str, mint: str) -> dict[str, object]:
        return {
            "id": str(uuid7()),
            "signal": signal,
            "market": market,
            "mint": mint,
            "key": f"r71:{uuid.uuid4()}",
        }

    async def an_order(engine: AsyncEngine) -> None:
        signal = await _signal(engine)
        await _run(engine, [(_AN_ORDER, _buy(signal, "NEARUSDT", _NEAR))])

    async def a_position(engine: AsyncEngine) -> None:
        """The entry order sits on one of ``0057``'s markets, so only the
        positions guard can fire — otherwise the orders guard hides it."""
        signal = await _signal(engine)
        order = _buy(signal, "WIFUSDT", _WIF)
        position = {"id": str(uuid7()), "signal": signal, "order": order["id"], "mint": _NEAR}
        await _run(engine, [(_AN_ORDER, order), (_A_POSITION, position)])

    for populate, guarded in ((an_order, "1 spot_orders"), (a_position, "1 spot_positions")):
        asyncio.run(_once(upgraded, populate))
        try:
            with pytest.raises(DBAPIError, match=guarded):
                command.downgrade(config, "-1")
            assert _scalar_of(upgraded, _REVISION) == REVISION, "the downgrade must not commit"
        finally:
            asyncio.run(_once(upgraded, _clean))
    command.downgrade(config, "-1")
    try:
        assert _scalar_of(upgraded, _REVISION) == PREVIOUS
        left = "SELECT count(*), count(*) FILTER (WHERE enabled) FROM spot_desk_markets"
        assert _scalar_of(upgraded, left.replace(", count(*) FILTER (WHERE enabled)", "")) == (
            SEEDED_BY_0057
        )
        enabled = "SELECT count(*) FROM spot_desk_markets WHERE enabled"
        assert _scalar_of(upgraded, enabled) == ENABLED_BY_0057
        gone = "SELECT count(*) FROM spot_desk_markets WHERE binance_symbol = 'NEARUSDT'"
        assert _scalar_of(upgraded, gone) == 0
    finally:
        command.upgrade(config, REVISION)
    assert _scalar_of(upgraded, "SELECT count(*) FROM spot_desk_markets") == TOTAL_ROWS
