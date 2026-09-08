"""Trades/Positions carry fees/PnL in both currencies, the feature snapshot
and the protection intents — brief T3.25 item 3.

Rows are written directly through the app's own session factory (as the DB
superuser the test container connects with, exactly like ``lab_fixtures.py``
does for Shadow Lab rows) rather than through a writer service: T3.4/T3.5's
actual execution-worker writer is out of this brief's scope, and the point
here is only that the read side (``routers/portfolio.py``) renders what the
schema already carries.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from hunter_core.db.models.execution_fills import Position
from hunter_core.db.models.execution_trades import Trade
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.models.paper_execution import PortfolioExitIntent
from hunter_core.db.repositories.fx import FxObservationRepository
from hunter_core.db.session import role_session, tenant_session
from hunter_core.domain.enums import (
    ExecutionMode,
    ExitIntentState,
    ExitReason,
    MarketType,
    PositionStatus,
    TradeDirection,
)
from hunter_core.domain.types import utcnow, uuid7
from hunter_core.portfolio.opening import open_paper_wallet

from .conftest import Actor, create_org

if TYPE_CHECKING:
    from collections.abc import Callable

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

pytestmark = pytest.mark.integration

CAPITAL_BRL = Decimal("100000")
RATE = Decimal("5.4321")


async def _observe_fx(
    session_factory: async_sessionmaker[AsyncSession], *, rate: Decimal, observed_at: datetime
) -> uuid.UUID:
    from sqlalchemy import text

    observation_id = uuid7()
    async with role_session(session_factory, db_role="hunter_worker") as session:
        await session.execute(
            text(
                "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                "available_at, raw) VALUES (:id, 'USDTBRL', :rate, 'binance.spot.ticker', "
                ":observed, :observed, '{}'::jsonb)"
            ),
            {"id": observation_id, "rate": rate, "observed": observed_at},
        )
    return observation_id


class Wallet:
    def __init__(self, actor: Actor, portfolio_id: uuid.UUID) -> None:
        self.actor = actor
        self.portfolio_id = portfolio_id

    @property
    def base(self) -> str:
        return f"/api/v1/orgs/{self.actor.org_id}/portfolios/{self.portfolio_id}"


@pytest_asyncio.fixture
async def wallet(
    client: httpx.AsyncClient,
    make_actor: Callable[[str], Actor],
    session_factory: async_sessionmaker[AsyncSession],
) -> Wallet:
    unique = uuid.uuid4().hex[:8]
    actor = await create_org(client, make_actor(f"tx-{unique}"), f"Trades {unique}")
    assert actor.org_id is not None and actor.workspace_id is not None
    now = utcnow()
    fx_id = await _observe_fx(session_factory, rate=RATE, observed_at=now)
    async with tenant_session(
        session_factory, actor.org_id, actor.user_id, db_role="hunter_worker"
    ) as session:
        fx = await FxObservationRepository(session).get(fx_id)
        assert fx is not None
        result = await open_paper_wallet(
            session,
            organization_id=actor.org_id,
            workspace_id=actor.workspace_id,
            fx=fx,
            as_of=now,
            capital_brl=CAPITAL_BRL,
        )
    return Wallet(actor, result.portfolio_id)


async def _seed_market(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    tag = uuid.uuid4().hex[:10]
    async with session_factory() as session:
        exchange = Exchange(code=f"txex{tag}", name=f"txex{tag}")
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=f"TX{tag.upper()}USDT",
            market_type=MarketType.SPOT,
            is_monitored=True,
        )
        session.add(market)
        await session.commit()
        return market.id


async def _seed_closed_trade(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    market_id: uuid.UUID,
    closed_at: datetime,
) -> tuple[uuid.UUID, uuid.UUID]:
    """One closed ``positions`` row, its ``trades`` row and one exit intent
    that protected it. Returns ``(position_id, trade_id)``."""
    position_id = uuid7()
    async with session_factory() as session:
        session.add(
            Position(
                id=position_id,
                organization_id=org_id,
                portfolio_id=portfolio_id,
                market_id=market_id,
                direction=TradeDirection.LONG,
                qty=Decimal("0"),
                avg_entry_price=Decimal("100"),
                status=PositionStatus.CLOSED,
                closed_at=closed_at,
            )
        )
        session.add(
            PortfolioExitIntent(
                id=uuid7(),
                organization_id=org_id,
                portfolio_id=portfolio_id,
                position_id=position_id,
                market_id=market_id,
                reason=ExitReason.TARGET,
                protection_key="target:1",
                state=ExitIntentState.FULFILLED,
                intended_qty=Decimal("10"),
                filled_qty=Decimal("10"),
                trigger_price=Decimal("110"),
                closed_reason="filled",
                closed_at=closed_at,
            )
        )
        await session.flush()
        trade_id = uuid7()
        session.add(
            Trade(
                id=trade_id,
                organization_id=org_id,
                portfolio_id=portfolio_id,
                market_id=market_id,
                position_id=position_id,
                execution_mode=ExecutionMode.PAPER,
                direction=TradeDirection.LONG,
                entry_price=Decimal("100"),
                exit_price=Decimal("110"),
                qty=Decimal("10"),
                fees=Decimal("2"),
                pnl=Decimal("98"),
                pnl_pct=Decimal("0.098"),
                exit_reason=ExitReason.TARGET,
                entry_snapshot={"rsi": "55"},
                exit_snapshot={"rsi": "70"},
                opened_at=closed_at - timedelta(hours=2),
                closed_at=closed_at,
            )
        )
        await session.commit()
    return position_id, trade_id


async def test_trade_carries_brl_fees_pnl_snapshots_and_protection_intents(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
) -> None:
    market_id = await _seed_market(session_factory)
    closed_at = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
    await _observe_fx(session_factory, rate=RATE, observed_at=closed_at - timedelta(minutes=1))
    _position_id, trade_id = await _seed_closed_trade(
        session_factory,
        org_id=wallet.actor.org_id,  # type: ignore[arg-type]
        portfolio_id=wallet.portfolio_id,
        market_id=market_id,
        closed_at=closed_at,
    )

    response = await client.get(f"{wallet.base}/trades", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    trade = next(item for item in items if item["id"] == str(trade_id))
    assert trade["fees"] == "2"
    assert Decimal(trade["fees_brl"]) == Decimal("2") * RATE
    assert trade["fees_brl_unavailable_reason"] is None
    assert trade["pnl"] == "98"
    assert Decimal(trade["pnl_brl"]) == Decimal("98") * RATE
    assert trade["entry_snapshot"] == {"rsi": "55"}
    assert trade["exit_snapshot"] == {"rsi": "70"}
    assert len(trade["protection_intents"]) == 1
    intent = trade["protection_intents"][0]
    assert intent["reason"] == "target"
    assert intent["state"] == "fulfilled"
    assert intent["protection_key"] == "target:1"


async def test_trade_fees_brl_is_honestly_null_without_an_fx_observation(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
) -> None:
    market_id = await _seed_market(session_factory)
    # Before any fx_observation this suite's ``wallet`` fixture wrote (its own
    # is at ``now - 1 day``, and this closes a full year earlier).
    closed_at = datetime(2020, 1, 1, tzinfo=UTC)
    _, trade_id = await _seed_closed_trade(
        session_factory,
        org_id=wallet.actor.org_id,  # type: ignore[arg-type]
        portfolio_id=wallet.portfolio_id,
        market_id=market_id,
        closed_at=closed_at,
    )

    response = await client.get(f"{wallet.base}/trades", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    trade = next(item for item in items if item["id"] == str(trade_id))
    assert trade["fees_brl"] is None
    assert trade["fees_brl_unavailable_reason"] == "no_fx_observation"
    assert trade["pnl_brl"] is None
    assert trade["pnl_brl_unavailable_reason"] == "no_fx_observation"


async def test_position_carries_its_protection_intents(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    wallet: Wallet,
) -> None:
    market_id = await _seed_market(session_factory)
    closed_at = datetime(2026, 9, 7, 16, 0, tzinfo=UTC)
    await _observe_fx(session_factory, rate=RATE, observed_at=closed_at - timedelta(minutes=1))
    position_id, _ = await _seed_closed_trade(
        session_factory,
        org_id=wallet.actor.org_id,  # type: ignore[arg-type]
        portfolio_id=wallet.portfolio_id,
        market_id=market_id,
        closed_at=closed_at,
    )

    response = await client.get(f"{wallet.base}/positions", headers=wallet.actor.headers)

    assert response.status_code == 200, response.text
    items = response.json()["items"]
    position = next(item for item in items if item["id"] == str(position_id))
    assert len(position["protection_intents"]) == 1
    assert position["protection_intents"][0]["protection_key"] == "target:1"
