"""``GET /api/v1/radar`` — global, no-RLS read (``hunter_core/db/models
/analysis.py``'s ``Opportunity`` module docstring: analysis tables have no
``organization_id``). Every row comes from an actual ``opportunities`` row —
this repository selects ``FROM opportunities``, never ``FROM markets``, so a
market that has no scored episode yet is simply absent, not shown with a
fabricated zero score.

Filtering, sorting and the keyset cursor all happen in one SQL statement so
the 200-row scale of M2 pays for one round trip; see
``repositories/radar_common.py`` for the JSONB path the ``volatility``
filter and the ``volume`` sort key both read.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from typing import cast as type_cast

from sqlalchemy import Numeric, and_, exists, func, or_, select, tuple_
from sqlalchemy import cast as sa_cast
from sqlalchemy import false as sql_false

from hunter_api.repositories.radar_common import (
    FEATURE_KEY_VOLATILITY,
    FEATURE_KEY_VOLUME,
    LIKE_ESCAPE,
    decode_sort_cursor,
    encode_sort_cursor,
    feature_value_expr,
    like_contains,
    sentinel_for,
)
from hunter_core.db.models.analysis import (
    Anomaly,
    MarketRegimeRow,
    Opportunity,
    OpportunityHistory,
)
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import (
    AnomalyStatus,
    AnomalyType,
    MarketRegime,
    MarketType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class RadarRow:
    opportunity_id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    market_type: MarketType
    direction: TradeDirection
    score: Decimal
    confidence: Decimal
    peak_score: Decimal | None
    status: OpportunityStatus
    stage: OpportunityStage
    regime: MarketRegime | None
    change: Decimal | None
    first_seen_at: datetime
    last_updated_at: datetime
    below_40_since: datetime | None


@dataclass(frozen=True, slots=True)
class RadarFilters:
    score_min: Decimal | None = None
    statuses: tuple[str, ...] = ()
    """Raw tokens: ``OpportunityStatus`` members plus ``IN_POSITION``/
    ``RISK_BLOCKED``. Validated by the router before reaching here."""
    stages: tuple[OpportunityStage, ...] = ()
    exchange: str | None = None
    anomaly_type: AnomalyType | None = None
    regime: MarketRegime | None = None
    volatility_min: Decimal | None = None
    volatility_max: Decimal | None = None
    symbol_query: str | None = None
    sort: str = "score"
    order: str = "desc"


def _change_expr() -> Any:
    """``score`` minus the last persisted ``opportunity_history`` score for
    this episode — ``0`` when there is no history row yet (a brand new
    episode has nothing to compare against, not "unknown")."""
    last_history_score = (
        select(OpportunityHistory.score)
        .where(OpportunityHistory.opportunity_id == Opportunity.id)
        .order_by(OpportunityHistory.ts.desc())
        .limit(1)
        .correlate(Opportunity)
        .scalar_subquery()
    )
    return Opportunity.score - func.coalesce(last_history_score, Opportunity.score)


def _sort_raw_expr(sort: str) -> Any:
    if sort == "score":
        return Opportunity.score
    if sort == "age":
        return type_cast(Any, sa_cast(func.extract("epoch", Opportunity.first_seen_at), Numeric))
    if sort == "change":
        return _change_expr()
    if sort == "volume":
        return feature_value_expr(FEATURE_KEY_VOLUME)
    raise ValueError(f"unknown radar sort key: {sort!r}")


def _status_condition(
    status_word: str, in_position_market_ids: frozenset[uuid.UUID], *, risk_blocked: bool
) -> Any:
    if status_word == "IN_POSITION":
        if not in_position_market_ids:
            return sql_false()
        return Opportunity.market_id.in_(in_position_market_ids)
    if status_word == "RISK_BLOCKED":
        return sql_false() if not risk_blocked else Opportunity.id.is_not(None)
    return Opportunity.status == OpportunityStatus(status_word)


class RadarRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        filters: RadarFilters,
        *,
        limit: int,
        cursor: str | None,
        in_position_market_ids: frozenset[uuid.UUID] = frozenset(),
        risk_blocked: bool = False,
    ) -> tuple[list[RadarRow], str | None]:
        change_expr = _change_expr()
        sort_raw = _sort_raw_expr(filters.sort)
        sentinel = sentinel_for(filters.order)

        stmt = (
            select(
                Opportunity.id.label("opportunity_id"),
                Opportunity.market_id,
                Exchange.code.label("exchange"),
                Market.symbol,
                Market.market_type,
                Opportunity.direction,
                Opportunity.score,
                Opportunity.confidence,
                Opportunity.peak_score,
                Opportunity.status,
                Opportunity.stage,
                MarketRegimeRow.regime.label("regime"),
                change_expr.label("change"),
                Opportunity.first_seen_at,
                Opportunity.last_updated_at,
                Opportunity.below_40_since,
                func.coalesce(sort_raw, sentinel).label("sort_value"),
            )
            .join(Market, Market.id == Opportunity.market_id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .outerjoin(MarketRegimeRow, MarketRegimeRow.id == Opportunity.regime_id)
        )

        conditions: list[Any] = []
        if filters.score_min is not None:
            conditions.append(Opportunity.score >= filters.score_min)
        if filters.statuses:
            conditions.append(
                or_(
                    *(
                        _status_condition(token, in_position_market_ids, risk_blocked=risk_blocked)
                        for token in filters.statuses
                    )
                )
            )
        if filters.stages:
            conditions.append(Opportunity.stage.in_(filters.stages))
        if filters.exchange:
            conditions.append(Exchange.code == filters.exchange)
        if filters.regime is not None:
            conditions.append(MarketRegimeRow.regime == filters.regime)
        if filters.volatility_min is not None:
            conditions.append(feature_value_expr(FEATURE_KEY_VOLATILITY) >= filters.volatility_min)
        if filters.volatility_max is not None:
            conditions.append(feature_value_expr(FEATURE_KEY_VOLATILITY) <= filters.volatility_max)
        if filters.symbol_query:
            conditions.append(
                Market.symbol.ilike(like_contains(filters.symbol_query), escape=LIKE_ESCAPE)
            )
        if filters.anomaly_type is not None:
            conditions.append(
                exists(
                    select(1).where(
                        Anomaly.market_id == Opportunity.market_id,
                        Anomaly.type == filters.anomaly_type,
                        Anomaly.status == AnomalyStatus.ACTIVE,
                    )
                )
            )
        if conditions:
            stmt = stmt.where(and_(*conditions))

        subquery = stmt.subquery()
        outer = select(subquery)
        order_cols = (
            (subquery.c.sort_value.desc(), subquery.c.opportunity_id.desc())
            if filters.order == "desc"
            else (subquery.c.sort_value.asc(), subquery.c.opportunity_id.asc())
        )
        outer = outer.order_by(*order_cols)

        decoded = decode_sort_cursor(cursor)
        if decoded is not None:
            cursor_value, cursor_id = decoded
            pair = tuple_(subquery.c.sort_value, subquery.c.opportunity_id)
            outer = outer.where(
                pair < (cursor_value, cursor_id)
                if filters.order == "desc"
                else pair > (cursor_value, cursor_id)
            )

        outer = outer.limit(limit + 1)
        rows = (await self.session.execute(outer)).all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [
            RadarRow(
                opportunity_id=row.opportunity_id,
                market_id=row.market_id,
                exchange=row.exchange,
                symbol=row.symbol,
                market_type=row.market_type,
                direction=row.direction,
                score=row.score,
                confidence=row.confidence,
                peak_score=row.peak_score,
                status=row.status,
                stage=row.stage,
                regime=row.regime,
                change=row.change,
                first_seen_at=row.first_seen_at,
                last_updated_at=row.last_updated_at,
                below_40_since=row.below_40_since,
            )
            for row in page_rows
        ]
        next_cursor = (
            encode_sort_cursor(page_rows[-1].sort_value, page_rows[-1].opportunity_id)
            if has_more
            else None
        )
        return items, next_cursor
