"""``0057_spot_desk`` (T4.74-1), the ``test_migration_0055.py``/``0056`` shape:
chain and slug; the seed constant is R63 §2a minus ``SOLUSDT``/``ENAUSDT`` with
``enabled`` derived from the design's rule; 50 rows, 35 enabled after the
upgrade; global tables; the ``meme_live_*``-shaped CHECKs refuse what they exist
to refuse; the worker writes and the API only asks for a sale (as the roles);
``alembic check`` clean; the downgrade refuses with a signed order or a position
and unwinds otherwise (§17.7). One async engine per ``asyncio.run`` (``0056``).
"""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.domain.types import uuid7

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

REVISION = "0057_spot_desk"
PREVIOUS = "0056_meme_spot_swaps"
SEEDED_ROWS, SEEDED_ENABLED = 50, 35
DISABLED_AT_SEED = frozenset(
    "SUIUSDT AVAXUSDT STRKUSDT CAKEUSDT WLFIUSDT GALAUSDT DRIFTUSDT MEGAUSDT CHZUSDT GRASSUSDT "
    "VIRTUALUSDT ARXUSDT PNUTUSDT MOODENGUSDT CHILLGUYUSDT".split()
)
_BASE58 = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_DENIED = "permission denied"
_REVISION = "SELECT version_num FROM alembic_version"
_WIF = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"

_AN_ORDER = (
    "INSERT INTO spot_orders (id, signal_id, position_id, market_symbol, mint, side, "
    "  client_order_id, status, reason, tx_signature, fill) "
    "VALUES (:id, :signal, :position, 'WIFUSDT', :mint, :side, :key, :status, :reason, "
    "  :signature, :fill)"
)
_A_POSITION = (
    "INSERT INTO spot_positions (id, signal_id, entry_order_id, market_symbol, mint, entry_at, "
    "  entry, tokens, sol_spent_lamports, initial_risk_sol, params, mark_sol, mark_at, "
    "  mark_source) VALUES (:id, :signal, :order, 'WIFUSDT', :mint, "
    "  now() - interval '1 minute', '{}'::jsonb, 1000, 50000000, 0.0005, '{}'::jsonb, "
    "  :mark_sol, :mark_at, :mark_source)"
)
_CLEAN: tuple[str, ...] = (
    "UPDATE spot_positions SET exit_order_id = NULL",  # a closed position holds its sell
    "DELETE FROM spot_orders WHERE position_id IS NOT NULL",  # the sells, then the cycle is open
    "DELETE FROM spot_positions",
    "DELETE FROM spot_orders",
    "DELETE FROM agent_signals WHERE params_hash = 'spot_desk_0057'",
)
_SIGNAL_ROWS: tuple[str, ...] = (
    "INSERT INTO strategies (id, key, name) VALUES (:strategy, :key, 'spot desk 0057')",
    "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:version, :strategy, 'v1')",
    "INSERT INTO exchanges (id, code, name) VALUES (:exchange, :key, 'spot desk 0057')",
    "INSERT INTO markets (id, exchange_id, symbol, market_type) "
    "VALUES (:market, :exchange, 'WIFUSDT', 'perpetual')",
    "INSERT INTO agent_signals (id, strategy_version_id, market_id, params_hash, direction, "
    "confidence) VALUES (:signal, :version, :market, 'spot_desk_0057', 'long', 0.5)",
)
_ORDER_KEYS = ("signal", "position", "reason", "signature", "fill")
_POSITION_KEYS = ("mark_sol", "mark_at", "mark_source")


def _order(**overrides: object) -> dict[str, object]:
    key, defaults = f"spot:{uuid.uuid4()}", dict.fromkeys(_ORDER_KEYS)
    fixed = {"id": str(uuid7()), "mint": _WIF, "side": "buy", "key": key, "status": "admitted"}
    return {**defaults, **fixed, **overrides}


def _position(signal: str, order: str, **overrides: object) -> dict[str, object]:
    fixed = {"id": str(uuid7()), "mint": _WIF, "signal": signal, "order": order}
    return {**dict.fromkeys(_POSITION_KEYS), **fixed, **overrides}


@pytest.fixture(scope="module")
def db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_0057"))


@pytest.fixture(scope="module")
def upgraded(db_url: str) -> Iterator[str]:
    """This revision by name, not ``head`` (the ``0055`` argument)."""
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


async def _as(engine: AsyncEngine, role: str, statement: str, params: dict[str, object]) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(f"SET LOCAL ROLE {role}"))
        await connection.execute(text(statement), params)


async def _signal(engine: AsyncEngine) -> str:
    """One ``agent_signals`` row of a fresh version on a fresh market, as the owner."""
    ids = {name: str(uuid7()) for name in ("strategy", "version", "exchange", "market", "signal")}
    params: dict[str, object] = {**ids, "key": f"spot0057-{uuid.uuid4().hex[:8]}"}
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


def test_the_revision_lands_on_0056_and_fits_the_version_column() -> None:
    source = REPO_ROOT / "infra" / "migrations" / "versions" / f"{REVISION}.py"
    assert f'down_revision: str | None = "{PREVIOUS}"' in source.read_text(encoding="utf-8")
    assert len(REVISION) <= 32


def test_the_seed_constant_is_the_r63_map_minus_sol_and_ena() -> None:
    """Pure: 50 rows, unique symbols, base58 mints, the two ``1000`` markets at
    1 000 units, and ``enabled`` following the rule — 35 on, the 15 named off."""
    rows = migration_ddl("spot_desk_seed").seed_rows()
    kinds = migration_ddl("spot_desk").SPOT_MARKET_KINDS_0057
    symbols = [row.binance_symbol for row in rows]
    assert len(rows) == SEEDED_ROWS and len(set(symbols)) == SEEDED_ROWS
    assert "SOLUSDT" not in symbols and "ENAUSDT" not in symbols
    for row in rows:
        assert row.binance_symbol.endswith("USDT") and row.base == row.binance_symbol[:-4]
        assert _BASE58.match(row.mint), row
        assert row.units_per_binance_unit == (1000 if row.base.startswith("1000") else 1)
        assert row.kind in kinds and row.tier in ("A", "B", "C")
        assert row.enabled == (
            row.tier != "C" and row.round_trip_cost_pct_at_seed <= Decimal("0.004")
        )
    assert {r.binance_symbol for r in rows if not r.enabled} == DISABLED_AT_SEED
    assert sum(1 for r in rows if r.enabled) == SEEDED_ENABLED


async def test_the_map_is_seeded_with_fifty_markets_and_thirty_five_enabled(
    engine: AsyncEngine,
) -> None:
    async with engine.connect() as connection:
        counts = (
            await connection.execute(
                text(
                    "SELECT count(*), count(*) FILTER (WHERE enabled), "
                    "count(*) FILTER (WHERE decimals IS NOT NULL), "
                    "count(*) FILTER (WHERE updated_by <> 'migration:0057_spot_desk') "
                    "FROM spot_desk_markets"
                )
            )
        ).one()
        rows = {
            row[0]: tuple(row[1:])
            for row in await connection.execute(
                text(
                    "SELECT binance_symbol, base, mint, units_per_binance_unit, kind, tier, "
                    "enabled, round_trip_cost_pct_at_seed FROM spot_desk_markets "
                    "WHERE binance_symbol IN ('ETHUSDT', '1000BONKUSDT', 'VIRTUALUSDT', "
                    "'SUIUSDT', 'UNIUSDT')"
                )
            )
        }
    assert tuple(counts) == (SEEDED_ROWS, SEEDED_ENABLED, 0, 0)
    eth = ("ETH", "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs", Decimal(1), "ponte", "A", True)
    assert rows["ETHUSDT"][:6] == eth
    bonk = ("1000BONK", "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", Decimal(1000), "nativo")
    assert rows["1000BONKUSDT"][:4] == bonk and rows["1000BONKUSDT"][5]
    assert rows["VIRTUALUSDT"][4:] == ("A", False, Decimal("0.00601")), "0,60 % round trip"
    assert rows["SUIUSDT"][4:6] == ("C", False), "tier C stays off until an operator enables it"
    assert rows["UNIUSDT"][2:] == (Decimal(1), "representacao", "B", True, Decimal("0.00193"))


async def test_the_tables_are_global_and_carry_no_policy(engine: AsyncEngine) -> None:
    """§25.5: "no policy needed" and "policy forgotten" look the same from outside."""
    tenant_columns = await _scalar(
        engine,
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'public' "
        "AND table_name LIKE 'spot_%' AND column_name = 'organization_id'",
    )
    policies = await _scalar(
        engine,
        "SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
        "WHERE c.relname LIKE 'spot_%'",
    )
    tables = await _scalar(engine, "SELECT count(*) FROM pg_tables WHERE tablename LIKE 'spot_%'")
    assert (tenant_columns, policies, tables) == (0, 0, 3)


async def test_the_checks_refuse_the_shapes_they_exist_to_refuse(engine: AsyncEngine) -> None:
    signal = await _signal(engine)
    try:
        refused: list[tuple[str, dict[str, object], str]] = [
            (_AN_ORDER, _order(signal=signal, side="sell"), "a_sell_names_its_position"),
            (_AN_ORDER, _order(signal=signal, status="refused"), "names_its_reason"),
            (_AN_ORDER, _order(signal=signal, status="submitted_unconfirmed"), "has_a_signature"),
            (_AN_ORDER, _order(signal=signal, status="confirmed", signature="s1"), "its_fill"),
        ]
        for statement, params, constraint in refused:
            with pytest.raises(IntegrityError, match=constraint):
                await _run(engine, [(statement, params)])
        buy = _order(signal=signal)
        await _run(engine, [(_AN_ORDER, buy)])
        with pytest.raises(IntegrityError, match="one_buy_per_signal"):
            await _run(engine, [(_AN_ORDER, _order(signal=signal))])
        position = _position(signal, str(buy["id"]))
        marked = {"mark_sol": Decimal("0.05"), "mark_at": datetime.now(UTC)}
        with pytest.raises(IntegrityError, match="mark_source_is_a_known_label"):
            await _run(engine, [(_A_POSITION, {**position, **marked, "mark_source": "tape"})])
        with pytest.raises(IntegrityError, match="a_mark_says_when_and_whence"):
            await _run(engine, [(_A_POSITION, {**position, "mark_sol": Decimal("0.05")})])
        await _run(engine, [(_A_POSITION, position)])
        with pytest.raises(IntegrityError, match="a_sell_names_its_position"):
            await _run(engine, [(_AN_ORDER, _order(signal=signal, position=position["id"]))])
        sell = _order(signal=signal, side="sell", position=position["id"])
        await _run(engine, [(_AN_ORDER, sell)])
    finally:
        await _clean(engine)


async def test_the_worker_writes_the_ledger_and_the_api_only_asks_for_a_sale(
    engine: AsyncEngine,
) -> None:
    """As the roles, not asked of the catalogue (§18.7's rule)."""
    signal = await _signal(engine)
    buy = _order(signal=signal)
    position = _position(signal, str(buy["id"]))
    where = {"id": position["id"]}
    allowed: tuple[tuple[str, str, dict[str, object]], ...] = (
        ("hunter_worker", _AN_ORDER, buy),
        ("hunter_worker", _A_POSITION, position),
        (
            "hunter_worker",
            "UPDATE spot_positions SET mark_sol = 0.051, mark_at = now(), "
            "mark_source = 'jupiter_quote' WHERE id = :id",
            where,
        ),
        ("hunter_worker", "UPDATE spot_desk_markets SET decimals = 6 WHERE base = 'WIF'", {}),
        ("hunter_app", "SELECT count(*) FROM spot_orders", {}),
        (
            "hunter_app",
            "UPDATE spot_positions SET sell_requested_at = now(), sell_requested_by = 'owner' "
            "WHERE id = :id",
            where,
        ),
    )
    try:
        for role, statement, params in allowed:
            await _as(engine, role, statement, params)
        denied = (
            ("hunter_app", "UPDATE spot_positions SET mark_sol = 1 WHERE false"),
            ("hunter_app", "UPDATE spot_desk_markets SET enabled = true WHERE false"),
            ("hunter_app", "INSERT INTO spot_orders (id) VALUES (gen_random_uuid())"),
            ("hunter_app", "DELETE FROM spot_positions WHERE false"),
            ("hunter_worker", "DELETE FROM spot_orders WHERE false"),
            ("hunter_worker", "DELETE FROM spot_positions WHERE false"),
            ("hunter_worker", "DELETE FROM spot_desk_markets WHERE false"),
        )
        for role, statement in denied:
            with pytest.raises(ProgrammingError, match=_DENIED):
                await _as(engine, role, statement, {})
    finally:
        await _run(engine, [("UPDATE spot_desk_markets SET decimals = NULL", {})])
        await _clean(engine)


def test_the_models_and_the_migrations_agree(container_url: str) -> None:
    """``alembic check`` on a database of its own taken to ``head``."""
    db_url = asyncio.run(create_database(container_url, "hunter_migration_0057_head"))
    config = alembic_config(db_url)
    command.upgrade(config, "head")
    command.check(config)


def test_the_downgrade_refuses_while_a_signed_order_exists_and_unwinds_otherwise(
    upgraded: str,
) -> None:
    """§17.7: a ``tx_signature`` on the ledger blocks the downgrade and nothing
    commits; with the signed row gone the three tables fall, ``0056`` is the
    revision, and the upgrade re-seeds the 50 rows."""
    config = alembic_config(upgraded)

    async def signed(engine: AsyncEngine) -> None:
        signal = await _signal(engine)
        row = _order(signal=signal, status="submitted_unconfirmed", signature="sig0057")
        await _run(engine, [(_AN_ORDER, row)])

    async def unsigned_but_positioned(engine: AsyncEngine) -> None:
        """A position over an ``admitted`` buy: never written, still money (Astra)."""
        signal = await _signal(engine)
        buy = _order(signal=signal)
        await _run(engine, [(_AN_ORDER, buy), (_A_POSITION, _position(signal, str(buy["id"])))])

    for populate, guarded in (
        (signed, "1 spot_orders rows"),
        (unsigned_but_positioned, "1 spot_positions"),
    ):
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
        left = "SELECT count(*) FROM pg_tables WHERE tablename LIKE 'spot_%'"
        assert _scalar_of(upgraded, left) == 0
    finally:
        command.upgrade(config, REVISION)
    assert _scalar_of(upgraded, "SELECT count(*) FROM spot_desk_markets") == SEEDED_ROWS
