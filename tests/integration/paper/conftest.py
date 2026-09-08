"""The §0 base fixture of ``.claude/state/spec-T3.9-verificacoes.md``, persisted.

One opened paper wallet — R$100.000 converted at a **test** rate of 5,00
BRL/USDT into 20.000,0000000000 USDT — three markets labelled with the real
recorded SPOT filters, and an injected clock. Everything the tests in this
directory do afterwards goes through the durable path:
``open_paper_wallet`` (``d23b7bd``), ``build_portfolio_state`` +
``record_equity_point`` for the mark to market, ``evaluate_and_persist``
(``9a0ac45``) for the kill switch and ``admit`` (``ae2657d``) for every entry.

Four rules this module holds itself to, from §12 of that spec:

- **no wall clock.** :data:`NOW` is the instant of ``factories.py``
  (2026-09-06T18:30:00Z) and every later moment is :func:`at`, an explicit
  offset. Nothing here calls ``datetime.now`` and nothing sleeps;
- **no ``float``.** Every price, quantity and amount below is a ``Decimal``
  built from a string; ``test_v1_sizing.py`` asserts that as a property of the
  fixture itself;
- **no state written straight into a column.** The kill switch is never seeded:
  it is produced by a real mark to market and a real evaluation. The one place
  rows are written by hand is the *fill* (``buy_filled``), whose writer is T3.5
  and does not exist yet — and it writes them as ``hunter_worker``, the role
  that will write them, never as the container owner;
- **the engine's role, everywhere.** ``0007_paper_roles`` (T3.1c, in flight)
  makes ``portfolio_equity_snapshots`` read-only to ``hunter_app`` and takes
  ``UPDATE`` on ``trade_proposals`` away from it. Every fixture here writes
  risk state, curve and admission as :data:`ENGINE_ROLE`.

**T3.9b extension (§0 unchanged, nothing above this note redeclared).** V4-V9
and §10 need the real ``execution-worker`` cycles (``execute_approved_entries``,
``run_protection_cycle``, ``cancel_pending_entries``, ``expire_stale_reservations``)
against this same wallet, not the hand-written ``buy_filled``. Two additions make
that possible without touching a number above:

- ``_reference_data`` now also writes ``tick_size``/``step_size``/``min_notional``
  and ``metadata.spot_market_filters`` on each ``markets`` row (previously only
  the identity), because ``hunter_execution_worker.reference.load_market`` reads
  filters from the row, not from ``Market.spec`` (the Risk Engine's own view,
  built straight from the fixture). Every recorded symbol carries
  ``avgPriceMins = 5`` (measured, ``.claude/state/notes-T3.0a.md`` §5), so every
  entry attempt below supplies ``avg_price`` explicitly — the collector that
  would supply it for real (T3.0b) does not exist yet (``notes-T3.5.md`` §5.2);
- the book/trade builders, the ``WalletRef`` bridge and the cycle runners at the
  end of this module. Nothing here is a double that fills: ``StaticSpotMarketData``
  is the same labelled test double the execution-worker's own suites use, and
  the real ``PaperExecutionAdapter`` inside each cycle decides what it fills.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from hunter_core.admission.service import AdmissionResult, admit
from hunter_core.admission.sources import ProposalRequest
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import create_session_factory, tenant_session
from hunter_core.domain.enums import (
    ExitReason,
    KillSwitchState,
    MarketType,
    OrderSide,
    TradeDirection,
)
from hunter_core.domain.market import BookLevel as DomBookLevel
from hunter_core.domain.market import NormalizedOrderBook, NormalizedTrade
from hunter_core.domain.types import uuid7
from hunter_core.execution.intents import ExitIntent
from hunter_core.portfolio.fx_policy import FxPolicy
from hunter_core.portfolio.ledger import record_equity_point
from hunter_core.portfolio.opening import open_paper_wallet
from hunter_core.portfolio.state import PortfolioStateBuild, build_portfolio_state
from hunter_core.risk.kill_switch import KillSwitchEvaluation, evaluate_and_persist
from hunter_core.strategies.envelope import AssumedCosts
from hunter_exchanges.binance_spot.filters import parse_filters
from hunter_execution_worker.entry import execute_approved_entries
from hunter_execution_worker.guard import cancel_pending_entries, expire_stale_reservations
from hunter_execution_worker.intents_repo import insert_intent
from hunter_execution_worker.market_data import (
    SpotMarketData,
    SpotSnapshot,
    StaticSpotMarketData,
)
from hunter_execution_worker.positions import open_position
from hunter_execution_worker.protection import (
    DegradedRetries,
    TriggerWatermarks,
    run_protection_cycle,
)
from hunter_execution_worker.reference import MarketReference
from hunter_execution_worker.wallet import WalletRef
from hunter_risk.inputs import BetaEstimate, BookLevel, MarketIdentity, MarketLiquidity, MarketSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from testcontainers.community.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SPOT_EXCHANGE_INFO = (
    REPO_ROOT
    / "packages"
    / "exchange-adapters"
    / "hunter_exchanges"
    / "testing"
    / "fixtures"
    / "spot_exchange_info.json"
)
PAPER_DB = "hunter_paper_t39a"

NOW = datetime(2026, 9, 6, 18, 30, tzinfo=UTC)
"""The one instant of ``packages/risk-core/tests/unit/factories.py``. The engine
has no clock; neither does this suite."""

RATE = Decimal("5.0000000000")
CAPITAL_BRL = Decimal("100000")
CREDITED = Decimal("20000.0000000000")
"""100.000 = 20.000 x 5, exact: the fixture deliberately leaves no conversion
residual (§0), so nothing here depends on the rounding policy of the opening."""

TEST_FX_POLICY = FxPolicy(source="test_fixed")
"""§0: pair ``USDTBRL``, source ``test_fixed`` — a *labelled* test rate, never
the collector's, so no test can be read as evidence about a real quote."""

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)
"""§0's ``AssumedCosts``: 2 bps spread, 5 bps slippage, 4 bps fee — the Risk
Engine's *hypothesis*, never the real SPOT taker fee (10 bps), which belongs to
execution and to V5."""

CASH_MULTIPLIER = Decimal("1.00100024")
"""``(1 + 0,0006) x (1 + 0,0004)`` — what one unit of notional holds in cash."""

NO_EXIT_COST = Decimal(0)
"""The declared exit-cost hypothesis of this suite: zero, stated once so every
``planned_risk_quote`` below is the bare stop distance and nothing is hidden in
a default."""

ENGINE_ROLE = "hunter_worker"
BOOK_DEPTH = Decimal(10_000)
HEALTHY_MINUTE = Decimal(50_000_000)
MEDIAN_MINUTE = Decimal("4605.10")
"""KB-0067/0071's measured median minute on the VPS: the number that makes the
participation ceiling bite (46,0510)."""


def at(*, minutes: int = 0, seconds: int = 0) -> datetime:
    """An instant, as an explicit offset from :data:`NOW`. The injected clock."""
    return NOW + timedelta(minutes=minutes, seconds=seconds)


# --------------------------------------------------------------------------
# The container, the database, the migrations
# --------------------------------------------------------------------------


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


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


@pytest.fixture(scope="session")
def paper_db_url(postgres_container: PostgresContainer) -> Iterator[str]:
    """A database of this suite's own, at ``head`` — 0006 plus 0007's role model."""
    url = asyncio.run(_create_database(postgres_container.get_connection_url(), PAPER_DB))
    command.upgrade(_alembic_config(url), "head")
    yield url


@pytest_asyncio.fixture
async def engine(paper_db_url: str) -> AsyncIterator[AsyncEngine]:
    """The container owner's engine — used only to *read back* what the roles wrote."""
    built = create_async_engine(paper_db_url, connect_args={"statement_cache_size": 0})
    try:
        yield built
    finally:
        await built.dispose()


@pytest_asyncio.fixture
async def factory(paper_db_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    built = create_async_engine(paper_db_url, connect_args={"statement_cache_size": 0})
    try:
        yield create_session_factory(built)
    finally:
        await built.dispose()


# --------------------------------------------------------------------------
# The markets: synthetic wallets, real recorded filters
# --------------------------------------------------------------------------


def recorded_filters(symbol: str) -> Any:
    """``SpotMarketFilters`` for ``symbol``, from the recorded ``exchangeInfo``.

    Read from ``spot_exchange_info.json`` (T3.0's recorded fixture) rather than
    typed in: §13 item 3 of the spec refuses to hard-code an ETHUSDT lot size
    nobody measured.
    """
    payload = json.loads(SPOT_EXCHANGE_INFO.read_text(encoding="utf-8"))
    for entry in payload["symbols"]:
        if entry["symbol"] == symbol:
            return parse_filters(entry)
    raise LookupError(f"{symbol} is not in {SPOT_EXCHANGE_INFO.name}")


class Market:
    """One market row plus the two objects the engine compares it against."""

    def __init__(self, symbol: str, base: str, market_id: uuid.UUID) -> None:
        filters = recorded_filters(symbol)
        self.symbol = symbol
        self.base = base
        self.id = market_id
        self.filters = filters
        """The parsed real filters — what T3.9b's execution-level tests judge a
        simulated fill by, read from the same ``markets`` row the worker reads
        (``_reference_data`` now writes ``tick_size``/``step_size``/``min_notional``
        and ``metadata.spot_market_filters`` for it, not only the identity)."""
        self.identity = MarketIdentity(
            exchange="binance",
            symbol=symbol,
            market_type=MarketType.SPOT,
            base_asset=base,
            quote_asset="USDT",
        )
        assert filters.min_notional is not None, f"{symbol} has no NOTIONAL filter"
        self.spec = MarketSpec(
            market=self.identity,
            step_size=filters.effective_step_size,
            min_notional=filters.min_notional,
            tick_size=filters.tick_size,
        )


SYMBOLS = (("BTCUSDT", "BTC"), ("ETHUSDT", "ETH"), ("SOLUSDT", "SOL"))


class Wallet:
    """The §0 wallet: one organization, one opened principal paper wallet."""

    def __init__(self, org_id: uuid.UUID, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.org_id = org_id
        self.workspace_id = workspace_id
        self.user_id = user_id
        self.portfolio_id: uuid.UUID = uuid7()
        self.agent_id: uuid.UUID = uuid7()
        self.markets: dict[str, Market] = {}

    def market(self, symbol: str) -> Market:
        return self.markets[symbol]

    @property
    def betas(self) -> dict[uuid.UUID, Decimal]:
        """A validated beta of 1 for every market, so the aggregate is never unknown."""
        return {market.id: Decimal(1) for market in self.markets.values()}


async def _reference_data(engine: AsyncEngine) -> dict[str, uuid.UUID]:
    """Exchange, assets and the three markets — global reference data, created once."""
    ids: dict[str, uuid.UUID] = {}
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO exchanges (id, code, name) VALUES (:id, 'binance', 'Binance') "
                "ON CONFLICT (code) DO NOTHING"
            ),
            {"id": uuid7()},
        )
        exchange_id = await connection.scalar(
            text("SELECT id FROM exchanges WHERE code = 'binance'")
        )
        for symbol, base in (*SYMBOLS, ("", "USDT")):
            await connection.execute(
                text(
                    "INSERT INTO assets (id, symbol) VALUES (:id, :symbol) "
                    "ON CONFLICT (symbol) DO NOTHING"
                ),
                {"id": uuid7(), "symbol": base},
            )
            del symbol
        quote_id = await connection.scalar(text("SELECT id FROM assets WHERE symbol = 'USDT'"))
        for symbol, base in SYMBOLS:
            base_id = await connection.scalar(
                text("SELECT id FROM assets WHERE symbol = :symbol"), {"symbol": base}
            )
            filters = recorded_filters(symbol)
            await connection.execute(
                text(
                    "INSERT INTO markets (id, exchange_id, symbol, market_type, base_asset_id, "
                    "quote_asset_id, tick_size, step_size, min_notional, is_monitored, metadata) "
                    "VALUES (:id, :ex, :symbol, 'spot', :base, :quote, :tick, :step, "
                    ":min_notional, true, CAST(:meta AS jsonb)) "
                    "ON CONFLICT (exchange_id, symbol, market_type) DO NOTHING"
                ),
                {
                    "id": uuid7(),
                    "ex": exchange_id,
                    "symbol": symbol,
                    "base": base_id,
                    "quote": quote_id,
                    "tick": filters.tick_size,
                    "step": filters.step_size,
                    "min_notional": filters.min_notional,
                    "meta": json.dumps({"spot_market_filters": filters.to_metadata()}),
                },
            )
            market_id = await connection.scalar(
                text(
                    "SELECT id FROM markets WHERE exchange_id = :ex AND symbol = :symbol "
                    "AND market_type = 'spot'"
                ),
                {"ex": exchange_id, "symbol": symbol},
            )
            assert market_id is not None
            ids[symbol] = market_id
    return ids


_FX_JITTER = itertools.count(1)
"""``uq_fx_observations_observation`` is ``(pair, source, observed_at)`` and the
table is immutable by trigger, so two tests asking for "the test rate at 18:30"
collide when they share one database. One counter for the session, a few
microseconds **backwards** each time — never forwards, so no observation is ever
stamped after the instant that consumes it (the same device the T3.3 ledger
fixtures use)."""


async def observe_fx(
    engine: AsyncEngine, *, at_instant: datetime, rate: Decimal = RATE
) -> uuid.UUID:
    """One ``fx_observations`` row from the labelled test source, at ``at_instant``."""
    observation_id = uuid7()
    stamp = at_instant - timedelta(microseconds=next(_FX_JITTER))
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
                "VALUES (:id, :pair, :rate, :source, :ts, :ts)"
            ),
            {
                "id": observation_id,
                "pair": TEST_FX_POLICY.pair,
                "rate": rate,
                "source": TEST_FX_POLICY.source,
                "ts": stamp,
            },
        )
    return observation_id


@pytest_asyncio.fixture
async def wallet(engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]) -> Wallet:
    """§0, opened for real: R$100.000 at 5,00 credit 20.000 USDT, as the engine."""
    return await open_fresh_wallet(engine, factory)


async def open_fresh_wallet(
    engine: AsyncEngine, factory: async_sessionmaker[AsyncSession]
) -> Wallet:
    """The ``wallet`` fixture's own body, callable directly.

    T3.9b's Hypothesis property test (V5 step 4) needs a **fresh** wallet per
    generated example, and a pytest fixture is resolved once per test item —
    including once for a whole ``@given`` run, since Hypothesis re-invokes the
    same function body rather than asking pytest for a new one. This is the
    one place that body lives; the fixture above is now a one-line caller.
    """
    market_ids = await _reference_data(engine)
    built = Wallet(uuid7(), uuid7(), uuid7())
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO users (id, external_auth_id, email) VALUES (:id, :ext, :email)"),
            {
                "id": built.user_id,
                "ext": f"clerk_{built.user_id}",
                "email": f"t39a-{built.user_id}@example.test",
            },
        )
        await connection.execute(
            text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
            {"id": built.org_id, "slug": f"t39a-{uuid.uuid4().hex[:10]}"},
        )
        await connection.execute(
            text(
                "INSERT INTO workspaces (id, organization_id, name, objective) "
                "VALUES (:id, :org, 'paper', 'paper_trading')"
            ),
            {"id": built.workspace_id, "org": built.org_id},
        )
    built.markets = {symbol: Market(symbol, base, market_ids[symbol]) for symbol, base in SYMBOLS}

    fx_id = await observe_fx(engine, at_instant=NOW)
    async with tenant_session(factory, built.org_id, db_role=ENGINE_ROLE) as session:
        observation = await FxObservationRepository(session).get(fx_id)
        assert observation is not None
        result = await open_paper_wallet(
            session,
            organization_id=built.org_id,
            workspace_id=built.workspace_id,
            fx=observation,
            as_of=NOW,
            capital_brl=CAPITAL_BRL,
            fx_policy=TEST_FX_POLICY,
        )
    built.portfolio_id = result.portfolio_id
    assert result.conversion.credited_amount == CREDITED
    await _enable_agent(engine, built)
    return built


async def _enable_agent(engine: AsyncEngine, wallet: Wallet) -> None:
    """One enabled agent for this wallet — an agent proposal names a real one.

    ``fk_trade_proposals_agent_id_agents`` is composite ``(agent_id,
    organization_id)``: a proposal cannot be attributed to an agent that does not
    belong to the same tenant, which is why the §11 idempotency race needs this
    row rather than an invented uuid.
    """
    strategy_id, version_id = uuid7(), uuid7()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO strategies (id, key, name) VALUES (:id, 't39a_probe', 'T3.9a probe') "
                "ON CONFLICT (key) DO NOTHING"
            ),
            {"id": strategy_id},
        )
        strategy_id = await connection.scalar(
            text("SELECT id FROM strategies WHERE key = 't39a_probe'")
        )
        await connection.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, version) "
                "VALUES (:id, :strategy, 'v0') ON CONFLICT DO NOTHING"
            ),
            {"id": version_id, "strategy": strategy_id},
        )
        version_id = await connection.scalar(
            text("SELECT id FROM strategy_versions WHERE strategy_id = :s AND version = 'v0'"),
            {"s": strategy_id},
        )
        await connection.execute(
            text(
                "INSERT INTO agents (id, organization_id, workspace_id, portfolio_id, name, "
                "strategy_version_id, status) VALUES (:id, :org, :ws, :pf, 'probe', :version, "
                "'enabled')"
            ),
            {
                "id": wallet.agent_id,
                "org": wallet.org_id,
                "ws": wallet.workspace_id,
                "pf": wallet.portfolio_id,
                "version": version_id,
            },
        )


# --------------------------------------------------------------------------
# The engine's inputs, all stamped at one explicit instant
# --------------------------------------------------------------------------


def liquidity_for(
    market: Market,
    *,
    as_of: datetime,
    last_price: Decimal = Decimal(100),
    minute_volume: Decimal = HEALTHY_MINUTE,
) -> MarketLiquidity:
    """A healthy market: fresh price, deep book, 24 h volume above the floor."""
    return MarketLiquidity(
        market=market.identity,
        last_price=last_price,
        mid_price=last_price,
        best_bid=last_price * Decimal("0.9999"),
        best_ask=last_price * Decimal("1.0001"),
        price_ts=as_of,
        asks=(
            BookLevel(price=last_price * Decimal("1.0001"), qty=BOOK_DEPTH),
            BookLevel(price=last_price * Decimal("1.0005"), qty=BOOK_DEPTH),
        ),
        book_ts=as_of,
        quote_volume_24h=Decimal(100_000_000),
        last_minute_quote_volume=minute_volume,
        median_30m_quote_volume=minute_volume,
        volume_window_complete=True,
        volume_ts=as_of,
        gap_state="ok",
        in_universe=True,
    )


def beta_for(*, as_of: datetime, validated: bool = True) -> BetaEstimate:
    return BetaEstimate(value=Decimal("1.0"), as_of=as_of, validated=validated, bars=120)


def request_for(
    wallet: Wallet,
    market: Market,
    *,
    client_key: str = "manual-1",
    entry_ref: Decimal = Decimal(100),
    stop: Decimal = Decimal("97.5"),
    **overrides: Any,
) -> ProposalRequest:
    fields: dict[str, Any] = {
        "client_key": client_key,
        "organization_id": wallet.org_id,
        "portfolio_id": wallet.portfolio_id,
        "market_id": market.id,
        "market": market.identity,
        "direction": TradeDirection.LONG,
        "entry_ref": entry_ref,
        "stop": stop,
        "assumed_costs": COSTS,
        "actor_id": str(wallet.user_id),
    }
    fields.update(overrides)
    return ProposalRequest.model_validate(fields)


async def admit_in(
    session: AsyncSession,
    wallet: Wallet,
    market: Market,
    request: ProposalRequest,
    *,
    now: datetime,
    marks: Mapping[uuid.UUID, Decimal],
    liquidity: MarketLiquidity | None = None,
    source: str = "manual",
) -> AdmissionResult:
    """``admit`` inside a transaction the caller owns (the two-session tests need that)."""
    return await admit(
        session,
        request,
        source=source,
        liquidity=liquidity if liquidity is not None else liquidity_for(market, as_of=now),
        spec=market.spec,
        beta=beta_for(as_of=now),
        prices=dict(marks),
        betas=wallet.betas,
        exit_cost_rate=NO_EXIT_COST,
        now=now,
        system=KillSwitchState.ACTIVE,
    )


async def admit_entry(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    market: Market,
    *,
    now: datetime,
    marks: Mapping[uuid.UUID, Decimal],
    client_key: str = "manual-1",
    liquidity: MarketLiquidity | None = None,
    source: str = "manual",
    **request_over: Any,
) -> AdmissionResult:
    """One admission in a transaction of its own, as the engine role."""
    request = request_for(wallet, market, client_key=client_key, **request_over)
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await admit_in(
            session,
            wallet,
            market,
            request,
            now=now,
            marks=marks,
            liquidity=liquidity,
            source=source,
        )


# --------------------------------------------------------------------------
# Mark to market, the equity curve and the kill switch — the durable path
# --------------------------------------------------------------------------


async def buy_filled(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    market: Market,
    *,
    qty: Decimal,
    price: Decimal,
    stop: Decimal,
    ts: datetime,
) -> uuid.UUID:
    """One entry that already filled: order, fill and the position it opened.

    Written by hand because its writer is the execution worker (T3.5), which
    does not exist yet — but written **as ``hunter_worker``**, the role that
    will write it, so nothing here passes only because the container owner may
    do anything.
    """
    order_id, fill_id, position_id = uuid7(), uuid7(), uuid7()
    params = {
        "org": wallet.org_id,
        "pf": wallet.portfolio_id,
        "market": market.id,
        "order": order_id,
        "fill": fill_id,
        "position": position_id,
        "qty": qty,
        "price": price,
        "stop": stop,
        "ts": ts,
        "key": f"exec-{fill_id}",
        "client": f"cli-{order_id}",
    }
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        await session.execute(
            text(
                "INSERT INTO orders (id, organization_id, portfolio_id, market_id, "
                "client_order_id, side, type, purpose, qty, filled_qty, execution_mode, status) "
                "VALUES (:order, :org, :pf, :market, :client, 'buy', 'market', 'entry', :qty, "
                ":qty, 'paper', 'filled')"
            ),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO fills (id, organization_id, portfolio_id, order_id, execution_key, "
                "ts, qty, price, fee, fee_asset) VALUES (:fill, :org, :pf, :order, :key, :ts, "
                ":qty, :price, 0, 'USDT')"
            ),
            params,
        )
        await session.execute(
            text(
                "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
                "qty, avg_entry_price, mark_price, stop_price, status, opened_at) "
                "VALUES (:position, :org, :pf, :market, 'long', :qty, :price, :price, :stop, "
                "'open', :ts)"
            ),
            params,
        )
    return position_id


async def mark_to_market(
    engine: AsyncEngine,
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    marks: Mapping[uuid.UUID, Decimal],
    at_instant: datetime,
) -> tuple[PortfolioStateBuild, KillSwitchEvaluation]:
    """One MTM cycle: value the wallet, append the curve, evaluate the kill switch.

    The three in **one** transaction, in this order and as the engine role — the
    order the peak guard requires (a peak may only rise to an equity the curve
    already showed) and the atomicity DATABASE.md §18.7 requires of a move.
    """
    fx_id = await observe_fx(engine, at_instant=at_instant)
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        build = await build_portfolio_state(
            session,
            organization_id=wallet.org_id,
            portfolio_id=wallet.portfolio_id,
            as_of=at_instant,
            marks=dict(marks),
            exit_cost_rate=NO_EXIT_COST,
            betas=wallet.betas,
        )
        observation = await FxObservationRepository(session).get(fx_id)
        await record_equity_point(session, build=build, fx=observation, fx_policy=TEST_FX_POLICY)
        evaluation = await evaluate_and_persist(
            session,
            wallet.portfolio_id,
            build.state,
            at_instant,
            system=KillSwitchState.ACTIVE,
        )
    return build, evaluation


async def read_state(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    marks: Mapping[uuid.UUID, Decimal],
    at_instant: datetime,
) -> PortfolioStateBuild:
    """The wallet as the engine sees it, read back from Postgres alone."""
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await build_portfolio_state(
            session,
            organization_id=wallet.org_id,
            portfolio_id=wallet.portfolio_id,
            as_of=at_instant,
            marks=dict(marks),
            exit_cost_rate=NO_EXIT_COST,
            betas=wallet.betas,
        )


# --------------------------------------------------------------------------
# Reading the rows back
# --------------------------------------------------------------------------


async def read_proposal(engine: AsyncEngine, proposal_id: uuid.UUID) -> Any:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT status::text AS status, source::text AS source, admission_seq, "
                    "reservation_state::text AS reservation_state, reserved_notional, "
                    "reserved_cash, reserved_risk, reserved_slot, reserved_until, decided_at, "
                    "rejection_reason, risk_decision, kill_switch_snapshot "
                    "FROM trade_proposals WHERE id = :id"
                ),
                {"id": proposal_id},
            )
        ).one()


async def read_latch(engine: AsyncEngine, wallet: Wallet) -> KillSwitchState:
    async with engine.connect() as connection:
        latch = await connection.scalar(
            text("SELECT kill_switch_state FROM portfolios WHERE id = :id"),
            {"id": wallet.portfolio_id},
        )
    return KillSwitchState(latch)


async def read_transitions(engine: AsyncEngine, wallet: Wallet) -> list[Any]:
    async with engine.connect() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT from_state::text AS from_state, to_state::text AS to_state, "
                        "actor_type, reason, evidence FROM kill_switch_transitions "
                        "WHERE scope = 'portfolio' AND scope_id = :id ORDER BY created_at, id"
                    ),
                    {"id": wallet.portfolio_id},
                )
            ).all()
        )


async def read_risk_state(engine: AsyncEngine, wallet: Wallet) -> Any:
    async with engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT equity_day_start, peak_equity, trading_day, last_admission_seq "
                    "FROM portfolio_risk_state WHERE portfolio_id = :id"
                ),
                {"id": wallet.portfolio_id},
            )
        ).one()


def cap_of(decision: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """One ceiling of a **persisted** decision, by name."""
    sizing = decision["sizing"]
    assert sizing is not None, "the decision carries no sizing"
    for cap in sizing["caps"]:
        if cap["name"] == name:
            return cap
    raise LookupError(f"no cap named {name}")


def check_of(decision: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    """One check of a **persisted** decision, by name — §12 item 9: always name it."""
    for entry in decision["checks"]:
        if entry["name"] == name:
            return entry
    raise LookupError(f"no check named {name}")


# --------------------------------------------------------------------------
# T3.9b — the execution-worker cycles against this same §0 wallet
# --------------------------------------------------------------------------


def wallet_ref(wallet: Wallet) -> WalletRef:
    """The worker's own identity for this wallet — both halves, never one."""
    return WalletRef(wallet.org_id, wallet.portfolio_id)


def market_reference(market: Market) -> MarketReference:
    """The worker's view of a §0 market: real filters, ``SPOT_VIP0`` fees.

    Built from the same :class:`Market` the Risk Engine's ``MarketSpec`` comes
    from, so a test that opens a position "directly" (bypassing the entry
    cycle, to fix a round quantity like V4's ten units) still books it against
    the identical filters ``load_market`` would read back from the row.
    """
    return MarketReference(market_id=market.id, identity=market.identity, filters=market.filters)


def spot_book(
    market: Market,
    *,
    received_at: datetime,
    bid: Decimal = Decimal(100),
    ask: Decimal = Decimal(100),
    qty: Decimal = BOOK_DEPTH,
    sequence: int | None = None,
) -> NormalizedOrderBook:
    """One flat, deep SPOT snapshot for ``market`` — a single level keeps the
    walk's VWAP exact, matching every closed number of the spec."""
    return NormalizedOrderBook(
        exchange=market.identity.exchange,
        symbol=market.symbol,
        market_type=MarketType.SPOT,
        ts=received_at,
        received_at=received_at,
        bids=[DomBookLevel(price=bid, qty=qty)],
        asks=[DomBookLevel(price=ask, qty=qty)],
        sequence=sequence,
        is_snapshot=True,
    )


def spot_trade(
    market: Market,
    *,
    price: Decimal,
    ts: datetime,
    trade_id: int,
    received_at: datetime | None = None,
    qty: Decimal = Decimal(1),
    side: OrderSide = OrderSide.BUY,
) -> NormalizedTrade:
    return NormalizedTrade(
        exchange=market.identity.exchange,
        symbol=market.symbol,
        market_type=MarketType.SPOT,
        ts=ts,
        received_at=received_at or ts,
        trade_id=str(trade_id),
        price=price,
        qty=qty,
        side=side,
    )


def static_data(market: Market, snapshot: SpotSnapshot) -> StaticSpotMarketData:
    """The labelled double (CLAUDE.md): the snapshot handed to it, nothing else.

    The real ``PaperExecutionAdapter`` inside every cycle below decides what it
    fills — this only stands in for the SPOT collector that does not exist yet
    (``notes-T3.5.md`` §5.3).
    """
    return StaticSpotMarketData({(market.identity.exchange, market.symbol): snapshot})


async def run_entries(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    data: SpotMarketData,
    *,
    now: datetime,
) -> tuple[Any, ...]:
    """One ``execute_approved_entries`` cycle, as the engine, in its own transaction."""
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await execute_approved_entries(
            session, wallet=wallet_ref(wallet), data=data, now=now
        )


async def run_protection(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    data: SpotMarketData,
    *,
    now: datetime,
    watermarks: TriggerWatermarks | None = None,
    retries: DegradedRetries | None = None,
    clock: Any = None,
) -> tuple[Any, ...]:
    """One ``run_protection_cycle``, as the engine, in its own transaction.

    A fresh ``watermarks``/``retries`` on every call **is** the restart of V6
    step 5 and §10: both are declared in-memory-only by ``triggering.py``, so a
    test that never passes the previous call's objects back is exercising
    exactly the recovery path a real process restart would take.
    """
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await run_protection_cycle(
            session,
            wallet=wallet_ref(wallet),
            data=data,
            now=now,
            watermarks=watermarks,
            retries=retries,
            clock=clock,
        )


async def run_cancel_pending(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet, *, now: datetime
) -> tuple[uuid.UUID, ...]:
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await cancel_pending_entries(session, wallet=wallet_ref(wallet), now=now)


async def run_expire_reservations(
    factory: async_sessionmaker[AsyncSession], wallet: Wallet, *, now: datetime
) -> tuple[uuid.UUID, ...]:
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await expire_stale_reservations(session, wallet=wallet_ref(wallet), now=now)


async def open_position_directly(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    market: Market,
    *,
    qty: Decimal,
    entry_price: Decimal,
    stop_price: Decimal | None,
    now: datetime,
) -> uuid.UUID:
    """Open a position with the real writer, at a round quantity a fee would never leave.

    Used only where the scenario is about **protection** (V4's stop-vs-target
    dispute, V8's gap, V9's missing book) and a fill's own arithmetic
    (18,518 @ 100,01 → 18,499482 net) would just be noise around the number the
    test actually cares about. The writer is ``hunter_execution_worker.positions
    .open_position`` itself, not a stub — nothing here fabricates a fill or a
    balance the ledger does not also see (``build_portfolio_state`` reads this
    row exactly as it would read one a real entry cycle produced).
    """
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await open_position(
            session,
            wallet=wallet_ref(wallet),
            market=market_reference(market),
            qty=qty,
            entry_price=entry_price,
            stop_price=stop_price,
            fees_quote=Decimal(0),
            now=now,
            proposal_id=None,
        )


async def insert_intent_directly(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    market: Market,
    *,
    position_id: uuid.UUID,
    protection_key: str,
    intended_qty: Decimal,
    trigger_price: Decimal | None,
    now: datetime,
    reason: ExitReason = ExitReason.STOP,
) -> ExitIntent:
    async with tenant_session(factory, wallet.org_id, db_role=ENGINE_ROLE) as session:
        return await insert_intent(
            session,
            wallet=wallet_ref(wallet),
            market=market_reference(market),
            position_id=position_id,
            protection_key=protection_key,
            reason=reason,
            intended_qty=intended_qty,
            trigger_price=trigger_price,
            now=now,
        )


async def read_positions(engine: AsyncEngine, wallet: Wallet) -> list[Any]:
    async with engine.begin() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT id, market_id, qty, avg_entry_price, mark_price, realized_pnl, "
                        "fees_paid, status::text AS status, stop_price FROM positions "
                        "WHERE portfolio_id = :pf ORDER BY opened_at"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).all()
        )


async def read_orders(engine: AsyncEngine, wallet: Wallet) -> list[Any]:
    async with engine.begin() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT client_order_id, side::text AS side, purpose::text AS purpose, "
                        "status::text AS status, qty, filled_qty, avg_fill_price, reason "
                        "FROM orders WHERE portfolio_id = :pf ORDER BY created_at"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).all()
        )


async def read_fills(engine: AsyncEngine, wallet: Wallet) -> list[Any]:
    async with engine.begin() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT f.execution_key, f.qty, f.price, f.fee, f.fee_asset, "
                        "f.slippage_bps, o.side::text AS side FROM fills f "
                        "JOIN orders o ON o.id = f.order_id WHERE f.portfolio_id = :pf "
                        "ORDER BY f.ts"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).all()
        )


async def read_exit_intents(engine: AsyncEngine, wallet: Wallet) -> list[Any]:
    async with engine.begin() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT id, protection_key, state::text AS state, intended_qty, "
                        "filled_qty, degraded_since, degraded_reason, closed_reason "
                        "FROM portfolio_exit_intents WHERE portfolio_id = :pf "
                        "ORDER BY created_at"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).all()
        )


async def read_trades(engine: AsyncEngine, wallet: Wallet) -> list[Any]:
    async with engine.begin() as connection:
        return list(
            (
                await connection.execute(
                    text(
                        "SELECT entry_price, exit_price, qty, fees, pnl, pnl_pct, "
                        "exit_reason::text AS exit_reason FROM trades "
                        "WHERE portfolio_id = :pf ORDER BY closed_at"
                    ),
                    {"pf": wallet.portfolio_id},
                )
            ).all()
        )


async def sum_sold(engine: AsyncEngine, wallet: Wallet) -> Decimal:
    """Every unit ever sold by this wallet, across every sell fill."""
    async with engine.begin() as connection:
        total = await connection.scalar(
            text(
                "SELECT coalesce(sum(f.qty), 0) FROM fills f JOIN orders o ON o.id = f.order_id "
                "WHERE f.portfolio_id = :pf AND o.side = 'sell'"
            ),
            {"pf": wallet.portfolio_id},
        )
    return Decimal(total)


async def count_rows(engine: AsyncEngine, wallet: Wallet, table: str) -> int:
    """How many rows of ``table`` this wallet has. ``table`` is never input."""
    allowed = (
        "orders",
        "fills",
        "positions",
        "trades",
        "portfolio_exit_intents",
        "participation_consumptions",
    )
    if table not in allowed:
        raise ValueError(f"{table} is not one of {allowed}")
    async with engine.begin() as connection:
        return int(
            await connection.scalar(
                text(f"SELECT count(*) FROM {table} WHERE portfolio_id = :pf"),  # noqa: S608
                {"pf": wallet.portfolio_id},
            )
            or 0
        )
