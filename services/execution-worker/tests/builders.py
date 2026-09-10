"""Shared setup for the execution-worker suites: a wallet, a market, a tape.

The numbers are the closed ones of ``.claude/state/spec-T3.9-verificacoes.md``
§0 — R$100.000 at a test rate of 5,00 BRL/USDT credits exactly 20.000 USDT, and
the synthetic market has ``step_size=0,001``, ``min_notional=5``,
``tick_size=0,01`` with ``entry_ref=100`` and ``stop=97,5``, which is what makes
``qty=18,518`` / ``notional=1.851,800`` the same number here and in the pure
core.

Nothing here fabricates a fill: the doubles are a *book* and a *tape*, and the
real ``PaperExecutionAdapter`` decides what they fill (spec §12, trap 4).
"""

from __future__ import annotations

import itertools
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import MarketType, OrderSide, TradeDirection
from hunter_core.domain.market import BookLevel, NormalizedOrderBook, NormalizedTrade
from hunter_core.domain.types import uuid7
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk.inputs import BetaEstimate, MarketIdentity, MarketLiquidity, MarketSpec
from hunter_risk.inputs import BookLevel as RiskBookLevel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

NOW = datetime(2026, 9, 6, 15, 30, tzinfo=UTC)
RATE = Decimal("5.0000000000")
CREDITED = Decimal("20000.0000000000")
NO_EXIT_COST = Decimal(0)
WORKER_ROLE = "hunter_worker"

COSTS = AssumedCosts(
    spread_bps=Decimal(2), slippage_bps=Decimal(5), fee_bps=Decimal(4), max_entry_delay_s=60
)

STEP = Decimal("0.001")
MIN_NOTIONAL = Decimal(5)
TICK = Decimal("0.01")

_FX_JITTER = itertools.count(1)


class Tenant:
    """One organization, workspace, exchange and SPOT market, freshly created."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        self.org_id = uuid7()
        self.workspace_id = uuid7()
        self.exchange_id = uuid7()
        self.market_id = uuid7()
        self.base_asset_id = uuid7()
        self.quote_asset_id = uuid7()
        self.symbol = f"HTR{slug[:6].upper()}USDT"
        self.base_symbol = f"HTR{slug[:6].upper()}"
        self.step = STEP


class Wallet:
    """An opened paper wallet plus the ids its tests need."""

    def __init__(self, tenant: Tenant, portfolio_id: uuid.UUID) -> None:
        self.tenant = tenant
        self.portfolio_id = portfolio_id
        self.org_id = tenant.org_id
        self.market_id = tenant.market_id


def filters_metadata() -> str:
    """``markets.metadata`` exactly as ``binance_spot.normalize`` writes it."""
    return json.dumps(
        {
            "spot_market_filters": {
                "market_step_size": "0",
                "market_min_qty": "0",
                "market_max_qty": "0",
                "apply_min_to_market": True,
                "max_notional": None,
                "apply_max_to_market": False,
                "avg_price_mins": 5,
                "bid_multiplier_up": "5",
                "bid_multiplier_down": "0.2",
                "ask_multiplier_up": "5",
                "ask_multiplier_down": "0.2",
            }
        }
    )


async def create_tenant(engine: AsyncEngine, *, step: Decimal = STEP) -> Tenant:
    """A tenant with a SPOT market carrying the real filter shape in metadata.

    ``step`` is the ``LOT_SIZE`` step of the market. It matters more than it
    looks: a spot buy pays its fee in the base asset, so the net quantity is
    ``qty x 0,999`` and whether that is a whole number of steps decides whether
    the position can ever be sold to zero or ends holding dust (V7 item 5).
    """
    tenant = Tenant(uuid.uuid4().hex[:8])
    tenant.step = step
    params: dict[str, Any] = {
        "org": tenant.org_id,
        "ws": tenant.workspace_id,
        "ex": tenant.exchange_id,
        "market": tenant.market_id,
        "base": tenant.base_asset_id,
        "quote": tenant.quote_asset_id,
        "slug": tenant.slug,
        "symbol": tenant.symbol,
        "base_symbol": tenant.base_symbol,
        "tick": TICK,
        "step": step,
        "min_notional": MIN_NOTIONAL,
    }
    async with engine.begin() as connection:
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
            text("INSERT INTO exchanges (id, code, name) VALUES (:ex, :slug, 'Execution probe')"),
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
                "quote_asset_id, tick_size, step_size, min_notional, is_monitored, metadata) "
                "VALUES (:market, :ex, :symbol, 'spot', :base, :quote, :tick, :step, "
                ":min_notional, true, CAST(:meta AS jsonb))"
            ),
            params | {"meta": filters_metadata()},
        )
    return tenant


async def observe_fx(
    engine: AsyncEngine,
    *,
    rate: Decimal = RATE,
    observed_at: datetime = NOW,
    available_at: datetime | None = None,
) -> uuid.UUID:
    """Persist one ``fx_observations`` row, as the collector of T3.11 would."""
    from hunter_core.portfolio.opening import PAPER_FX_POLICY

    observation_id = uuid7()
    offset = timedelta(microseconds=next(_FX_JITTER))
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, available_at) "
                "VALUES (:id, :pair, :rate, :source, :observed, :available)"
            ),
            {
                "id": observation_id,
                "pair": PAPER_FX_POLICY.pair,
                "rate": rate,
                "source": PAPER_FX_POLICY.source,
                "observed": observed_at - offset,
                "available": (available_at or observed_at) - offset,
            },
        )
    return observation_id


async def link_paper_profile(
    factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
    *,
    limits: dict[str, Any] | None = None,
) -> uuid.UUID:
    """``docs/ACTIVATION.md`` §8b in test form: a ``paper_v1`` row, and the link.

    T3.69b made the linked row the **applied** source of the wallet's limits, so
    a wallet without one admits nothing. Written as ``hunter_app`` because
    ``risk_profiles`` and ``portfolios`` are its tables (``ddl/tables.py``:
    ``APP_WRITE_TABLES``) — the worker may read them, never write them — and
    tenant-scoped rather than a system preset, which only the migrating role may
    write under ``FORCE ROW LEVEL SECURITY``.
    """
    from hunter_risk.limits import PAPER_V1

    profile_id = uuid7()
    stored = PAPER_V1.model_dump(mode="json") if limits is None else limits
    async with tenant_session(factory, wallet.tenant.org_id) as session:
        await session.execute(
            text(
                "INSERT INTO risk_profiles (id, organization_id, name, preset, limits) VALUES "
                "(:id, :org, 'Paper v1', 'paper_v1', CAST(:limits AS jsonb))"
            ),
            {"id": profile_id, "org": wallet.tenant.org_id, "limits": json.dumps(stored)},
        )
        await session.execute(
            text("UPDATE portfolios SET risk_profile_id = :profile WHERE id = :id"),
            {"profile": profile_id, "id": wallet.portfolio_id},
        )
    return profile_id


async def open_wallet(
    factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    tenant: Tenant,
    *,
    as_of: datetime = NOW,
    link_profile: bool = True,
) -> Wallet:
    """Open the wallet **as the engine** — §19.6: the curve is the worker's.

    ``link_profile`` is on by default because since T3.69b a wallet without a
    linked ``risk_profiles`` row admits nothing: every suite here is about what
    happens *after* admission, so the operator act of ``ACTIVATION.md`` §8b is
    part of opening a wallet in these tests. The one suite that is about the
    link itself opens without it.
    """
    from hunter_core.db.repositories.fx import FxObservationRepository
    from hunter_core.portfolio.opening import open_paper_wallet

    fx_id = await observe_fx(engine, observed_at=as_of)
    async with tenant_session(factory, tenant.org_id, db_role=WORKER_ROLE) as session:
        observation = await FxObservationRepository(session).get(fx_id)
        assert observation is not None
        result = await open_paper_wallet(
            session,
            organization_id=tenant.org_id,
            workspace_id=tenant.workspace_id,
            fx=observation,
            as_of=as_of,
        )
    wallet = Wallet(tenant, result.portfolio_id)
    if link_profile:
        await link_paper_profile(factory, wallet)
    return wallet


def market_identity(tenant: Tenant | SecondMarket) -> MarketIdentity:
    return MarketIdentity(
        exchange=tenant.slug,
        symbol=tenant.symbol,
        market_type=MarketType.SPOT,
        base_asset=tenant.base_symbol,
        quote_asset="USDT",
    )


def spec_for(tenant: Tenant | SecondMarket) -> MarketSpec:
    return MarketSpec(
        market=market_identity(tenant),
        step_size=tenant.step,
        min_notional=MIN_NOTIONAL,
        tick_size=TICK,
    )


def liquidity_for(
    tenant: Tenant | SecondMarket,
    *,
    as_of: datetime = NOW,
    last_price: Decimal = Decimal(100),
    minute_volume: Decimal = Decimal(50_000_000),
    depth: Decimal = Decimal(10_000),
) -> MarketLiquidity:
    return MarketLiquidity(
        market=market_identity(tenant),
        last_price=last_price,
        mid_price=last_price,
        best_bid=last_price * Decimal("0.9999"),
        best_ask=last_price * Decimal("1.0001"),
        price_ts=as_of,
        asks=(
            RiskBookLevel(price=last_price * Decimal("1.0001"), qty=depth),
            RiskBookLevel(price=last_price * Decimal("1.0005"), qty=depth),
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


def beta_for(*, as_of: datetime = NOW, validated: bool = True) -> BetaEstimate:
    return BetaEstimate(value=Decimal("1.0"), as_of=as_of, validated=validated, bars=120)


def book(
    tenant: Tenant,
    *,
    received_at: datetime,
    ask: Decimal = Decimal(100),
    bid: Decimal = Decimal(100),
    qty: Decimal = Decimal(1_000),
    sequence: int | None = None,
) -> NormalizedOrderBook:
    """One flat, deep snapshot. A single level keeps ``vwap`` exact."""
    return NormalizedOrderBook(
        exchange=tenant.slug,
        symbol=tenant.symbol,
        market_type=MarketType.SPOT,
        ts=received_at,
        received_at=received_at,
        bids=[BookLevel(price=bid, qty=qty)],
        asks=[BookLevel(price=ask, qty=qty)],
        sequence=sequence,
        is_snapshot=True,
    )


def trade(
    tenant: Tenant,
    *,
    price: Decimal,
    ts: datetime,
    trade_id: int,
    received_at: datetime | None = None,
    qty: Decimal = Decimal(1),
) -> NormalizedTrade:
    return NormalizedTrade(
        exchange=tenant.slug,
        symbol=tenant.symbol,
        market_type=MarketType.SPOT,
        ts=ts,
        received_at=received_at or ts,
        trade_id=str(trade_id),
        price=price,
        qty=qty,
        side=OrderSide.BUY,
    )


def request_for(
    wallet: Wallet,
    *,
    client_key: str = "manual-1",
    entry_ref: Decimal = Decimal(100),
    stop: Decimal = Decimal("97.5"),
    **overrides: Any,
) -> Any:
    from hunter_core.admission.sources import ProposalRequest

    fields: dict[str, Any] = {
        "client_key": client_key,
        "organization_id": wallet.org_id,
        "portfolio_id": wallet.portfolio_id,
        "market_id": wallet.market_id,
        "market": market_identity(wallet.tenant),
        "direction": TradeDirection.LONG,
        "entry_ref": entry_ref,
        "stop": stop,
        "assumed_costs": COSTS,
        "actor_id": str(uuid.uuid4()),
    }
    fields.update(overrides)
    return ProposalRequest.model_validate(fields)


class SecondMarket:
    """A second SPOT market in the same tenant, for the cross-market scenarios."""

    def __init__(self, tenant: Tenant, market_id: uuid.UUID, symbol: str, base: str) -> None:
        self.slug = tenant.slug
        self.symbol = symbol
        self.base_symbol = base
        self.market_id = market_id
        self.step = tenant.step


async def add_market(engine: AsyncEngine, tenant: Tenant, *, suffix: str = "B") -> SecondMarket:
    """One more market, so a pending entry can exist where a position does not.

    ``suffix`` names the extra coin: the bridge suites need several distinct
    ones in the same tenant, and ``assets.symbol`` is globally unique.
    """
    market_id, base_id = uuid7(), uuid7()
    symbol = f"{tenant.base_symbol}{suffix}USDT"
    base = f"{tenant.base_symbol}{suffix}"
    async with engine.begin() as connection:
        await connection.execute(
            text("INSERT INTO assets (id, symbol) VALUES (:id, :symbol)"),
            {"id": base_id, "symbol": base},
        )
        await connection.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, base_asset_id, "
                "quote_asset_id, tick_size, step_size, min_notional, is_monitored, metadata) "
                "VALUES (:id, :ex, :symbol, 'spot', :base, :quote, :tick, :step, :min_notional, "
                "true, CAST(:meta AS jsonb))"
            ),
            {
                "id": market_id,
                "ex": tenant.exchange_id,
                "symbol": symbol,
                "base": base_id,
                "quote": tenant.quote_asset_id,
                "tick": TICK,
                "step": tenant.step,
                "min_notional": MIN_NOTIONAL,
                "meta": filters_metadata(),
            },
        )
    return SecondMarket(tenant, market_id, symbol, base)
