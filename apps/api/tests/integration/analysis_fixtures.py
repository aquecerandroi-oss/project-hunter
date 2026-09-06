"""Shared seeding helpers for the T2.6 integration suite (radar, opportunities,
anomalies, regime). Every row here follows the T2.1 models exactly
(``hunter_core.db.models.analysis``/``analysis_baselines``) — no field is
invented outside a model's own contract, per the brief's "sem dado fabricado
fora de teste".
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import update

from hunter_core.db.models.analysis import Anomaly, MarketRegimeRow, Opportunity
from hunter_core.db.models.execution import Position
from hunter_core.db.models.identity import Organization
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.domain.enums import (
    AnomalyEvaluationState,
    AnomalyStatus,
    AnomalyType,
    KillSwitchState,
    MarketRegime,
    MarketType,
    OpportunityStage,
    OpportunityStatus,
    PortfolioType,
    PositionStatus,
    RegimeScope,
    TradeDirection,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

_JSON_EMPTY: dict[str, Any] = {}


async def seed_exchange(session_factory: async_sessionmaker[AsyncSession]) -> tuple[str, uuid.UUID]:
    tag = uuid.uuid4().hex[:10]
    exchange_code = f"anex{tag}"
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        session.add(exchange)
        await session.commit()
        return exchange_code, exchange.id


async def seed_market_on(
    session_factory: async_sessionmaker[AsyncSession], exchange_id: uuid.UUID
) -> tuple[str, uuid.UUID]:
    """One more perpetual market on an existing exchange — for tests that need
    several markets isolated to one ``exchange=`` filter value.
    """
    tag = uuid.uuid4().hex[:10]
    symbol = f"AN{tag.upper()}USDT"
    async with session_factory() as session:
        market = Market(
            exchange_id=exchange_id,
            symbol=symbol,
            market_type=MarketType.PERPETUAL,
            is_monitored=True,
        )
        session.add(market)
        await session.commit()
        return symbol, market.id


async def seed_market(
    session_factory: async_sessionmaker[AsyncSession], *, suffix: str | None = None
) -> tuple[str, str, uuid.UUID]:
    """A fresh exchange + one perpetual market, uniquely named."""
    tag = suffix or uuid.uuid4().hex[:10]
    exchange_code = f"anex{tag}"
    symbol = f"AN{tag.upper()}USDT"
    async with session_factory() as session:
        exchange = Exchange(code=exchange_code, name=exchange_code)
        session.add(exchange)
        await session.flush()
        market = Market(
            exchange_id=exchange.id,
            symbol=symbol,
            market_type=MarketType.PERPETUAL,
            is_monitored=True,
        )
        session.add(market)
        await session.commit()
        return exchange_code, symbol, market.id


async def seed_opportunity(
    session_factory: async_sessionmaker[AsyncSession],
    market_id: uuid.UUID,
    *,
    score: Decimal = Decimal("55.00"),
    confidence: Decimal = Decimal("0.5000"),
    status: OpportunityStatus = OpportunityStatus.WATCHING,
    stage: OpportunityStage = OpportunityStage.NONE,
    direction: TradeDirection = TradeDirection.LONG,
    regime_id: uuid.UUID | None = None,
    decomposition: dict[str, Any] | None = None,
    explanation: dict[str, Any] | None = None,
    feature_snapshot: dict[str, Any] | None = None,
    weights_version: str | None = "v2",
    peak_score: Decimal | None = None,
    below_40_since: datetime | None = None,
    expired_at: datetime | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        opportunity = Opportunity(
            market_id=market_id,
            direction=direction,
            score=score,
            confidence=confidence,
            status=status,
            stage=stage,
            regime_id=regime_id,
            decomposition=decomposition if decomposition is not None else _JSON_EMPTY,
            explanation=explanation if explanation is not None else _JSON_EMPTY,
            feature_snapshot=feature_snapshot if feature_snapshot is not None else _JSON_EMPTY,
            weights_version=weights_version,
            peak_score=peak_score,
            below_40_since=below_40_since,
            expired_at=expired_at,
        )
        session.add(opportunity)
        await session.commit()
        return opportunity.id


async def seed_anomaly(
    session_factory: async_sessionmaker[AsyncSession],
    market_id: uuid.UUID,
    *,
    anomaly_type: AnomalyType = AnomalyType.VOLUME_SPIKE,
    severity: Decimal = Decimal("70.00"),
    confidence: Decimal = Decimal("0.8000"),
    status: AnomalyStatus = AnomalyStatus.ACTIVE,
    evaluation_state: AnomalyEvaluationState = AnomalyEvaluationState.OK,
    detected_at: datetime | None = None,
) -> uuid.UUID:
    async with session_factory() as session:
        anomaly = Anomaly(
            market_id=market_id,
            type=anomaly_type,
            severity=severity,
            confidence=confidence,
            status=status,
            evaluation_state=evaluation_state,
        )
        if detected_at is not None:
            anomaly.detected_at = detected_at
        session.add(anomaly)
        await session.commit()
        return anomaly.id


async def seed_regime(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    scope: RegimeScope = RegimeScope.GLOBAL,
    regime: MarketRegime = MarketRegime.SIDEWAYS,
    confidence: Decimal | None = Decimal("0.7500"),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    supporting_features: dict[str, Any] | None = None,
) -> uuid.UUID:
    """``market_regimes`` has only two scopes and ``uq_market_regimes_open_per_scope``
    allows at most one open (``end_time IS NULL``) row per scope in the whole
    (shared, session-scoped) test database. Requesting another open row for
    ``scope`` here closes whichever one is currently open first — exactly
    what a real classifier transition does — so tests in different files
    seeding the same scope never collide on the constraint.
    """
    async with session_factory() as session:
        if end_time is None:
            await session.execute(
                update(MarketRegimeRow)
                .where(MarketRegimeRow.scope == scope, MarketRegimeRow.end_time.is_(None))
                .values(end_time=datetime.now(UTC))
            )
        row = MarketRegimeRow(
            scope=scope,
            regime=regime,
            confidence=confidence,
            start_time=start_time or datetime.now(UTC),
            end_time=end_time,
            supporting_features=(
                supporting_features if supporting_features is not None else _JSON_EMPTY
            ),
        )
        session.add(row)
        await session.commit()
        return row.id


async def seed_open_position(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    market_id: uuid.UUID,
    status: PositionStatus = PositionStatus.OPEN,
) -> uuid.UUID:
    """A portfolio and one position on ``market_id`` for ``org_id`` — what
    ``services/radar_org_derivation.py`` reads to mark ``in_position``.
    """
    async with session_factory() as session:
        portfolio = Portfolio(
            organization_id=org_id,
            workspace_id=workspace_id,
            name="fixture-portfolio",
            type=PortfolioType.PAPER,
            initial_capital=Decimal("10000"),
        )
        session.add(portfolio)
        await session.flush()
        position = Position(
            organization_id=org_id,
            portfolio_id=portfolio.id,
            market_id=market_id,
            direction=TradeDirection.LONG,
            qty=Decimal("1"),
            avg_entry_price=Decimal("100"),
            status=status,
        )
        session.add(position)
        await session.commit()
        return position.id


async def set_org_kill_switch(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    *,
    state: KillSwitchState,
    reason: str | None = None,
) -> None:
    async with session_factory() as session:
        org = await session.get(Organization, org_id)
        assert org is not None
        org.kill_switch_state = state
        org.kill_switch_reason = reason
        await session.commit()
