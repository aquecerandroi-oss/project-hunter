"""``GET /api/v1/opportunities`` and ``/{id}`` — DATABASE.md §17.3.

The list carries fewer *filters* than ``repositories/radar.py`` (the rich
filter/sort contract belongs to the radar table; this endpoint exists mainly
to support the detail view), but it pages the same way: one keyset statement
over ``(score, id)`` with ``LIMIT limit + 1``, never "select everything, then
window it in Python".

MF-2 (security-reviewer, 2026-09-06): the earlier version had no ``LIMIT`` at
all and scanned the returned list linearly to honour the cursor, so a table
that accumulated ``EXPIRED`` episodes turned every page request into a full
table read plus a full JSONB decode. Two things follow from that and are load
bearing here:

- ``decomposition`` is **not** selected by the list statement. It is a JSONB
  blob per row whose only consumer is the detail view, and shipping it for
  every row of every page was most of the cost. ``build_list_statement`` is a
  module-level function precisely so a unit test can compile it and assert the
  column is absent.
- The cursor carries ``(score, id)``, not just ``id``, because a keyset needs
  the sort key it seeks on.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from fastapi import status
from sqlalchemy import select, tuple_

from hunter_api.errors import HunterError
from hunter_api.repositories.radar_common import LIKE_ESCAPE, like_contains
from hunter_core.db.models.analysis import (
    Anomaly,
    MarketRegimeRow,
    Opportunity,
    OpportunityHistory,
)
from hunter_core.db.models.markets import Exchange, Market
from hunter_core.domain.enums import (
    AnomalyStatus,
    MarketRegime,
    MarketType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

DEFAULT_HISTORY_LIMIT = 100
MAX_CURSOR_LENGTH = 96


class InvalidOpportunityCursorError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cursor",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The pagination cursor is not valid.",
        )


def encode_opportunity_cursor(score: Decimal, row_id: uuid.UUID) -> str:
    """The keyset position of the last row of a page: ``(score, id)``.

    Both halves are needed — ``score`` is ``NUMERIC(5,2)`` and ties are
    common, so ``id`` is what breaks them deterministically.
    """
    return base64.urlsafe_b64encode(f"{score}|{row_id}".encode()).decode()


def decode_opportunity_cursor(cursor: str | None) -> tuple[Decimal, uuid.UUID] | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > MAX_CURSOR_LENGTH:
        raise InvalidOpportunityCursorError
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        score_raw, _, id_raw = raw.partition("|")
        score = Decimal(score_raw)
        row_id = uuid.UUID(id_raw)
    except (ValueError, InvalidOperation, binascii.Error, UnicodeDecodeError):
        raise InvalidOpportunityCursorError from None
    if not score.is_finite():
        # NaN/Infinity survive Decimal() and then break (or silently empty) the
        # keyset comparison in Postgres — a 422, never a 500.
        raise InvalidOpportunityCursorError
    return score, row_id


@dataclass(frozen=True, slots=True)
class OpportunityListRow:
    """One row of the list. Carries no ``decomposition`` on purpose (MF-2):
    that is a per-row JSONB blob only the detail view needs — see the module
    docstring."""

    id: uuid.UUID
    market_id: uuid.UUID
    exchange: str
    symbol: str
    market_type: MarketType
    direction: TradeDirection
    score: Decimal
    confidence: Decimal
    status: OpportunityStatus
    stage: OpportunityStage
    regime: MarketRegime | None
    weights_version: str | None
    first_seen_at: datetime
    last_updated_at: datetime


@dataclass(frozen=True, slots=True)
class OpportunityDetailRow:
    id: uuid.UUID
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
    regime_id: uuid.UUID | None
    weights_version: str | None
    decomposition: dict[str, Any]
    explanation: dict[str, Any]
    feature_snapshot: dict[str, Any]
    below_40_since: datetime | None
    expired_at: datetime | None
    first_seen_at: datetime
    last_updated_at: datetime


def build_list_statement(
    *,
    score_min: Decimal | None,
    statuses: Sequence[OpportunityStatus],
    stages: Sequence[OpportunityStage],
    exchange: str | None,
    symbol_query: str | None,
    cursor: tuple[Decimal, uuid.UUID] | None,
    limit: int,
) -> Select[Any]:
    """The one statement ``list_page`` runs: filters, keyset seek and
    ``LIMIT limit + 1`` (the extra row is how "is there a next page?" is
    answered without a second ``COUNT``).

    Module-level rather than a private method so the two properties that
    matter can be asserted by compiling it, with no database:
    ``decomposition`` is never selected, and there is always a ``LIMIT``.
    """
    stmt = (
        select(
            Opportunity.id,
            Opportunity.market_id,
            Exchange.code.label("exchange"),
            Market.symbol,
            Market.market_type,
            Opportunity.direction,
            Opportunity.score,
            Opportunity.confidence,
            Opportunity.status,
            Opportunity.stage,
            MarketRegimeRow.regime.label("regime"),
            Opportunity.weights_version,
            Opportunity.first_seen_at,
            Opportunity.last_updated_at,
        )
        .join(Market, Market.id == Opportunity.market_id)
        .join(Exchange, Exchange.id == Market.exchange_id)
        .outerjoin(MarketRegimeRow, MarketRegimeRow.id == Opportunity.regime_id)
    )
    if score_min is not None:
        stmt = stmt.where(Opportunity.score >= score_min)
    if statuses:
        stmt = stmt.where(Opportunity.status.in_(statuses))
    if stages:
        stmt = stmt.where(Opportunity.stage.in_(stages))
    if exchange:
        stmt = stmt.where(Exchange.code == exchange)
    if symbol_query:
        stmt = stmt.where(Market.symbol.ilike(like_contains(symbol_query), escape=LIKE_ESCAPE))
    if cursor is not None:
        stmt = stmt.where(tuple_(Opportunity.score, Opportunity.id) < cursor)
    return stmt.order_by(Opportunity.score.desc(), Opportunity.id.desc()).limit(limit + 1)


class OpportunityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        score_min: Decimal | None,
        statuses: Sequence[OpportunityStatus],
        stages: Sequence[OpportunityStage],
        exchange: str | None,
        symbol_query: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[OpportunityListRow], str | None]:
        """One page, ordered ``(score desc, id desc)``, plus the cursor for the
        next one (``None`` when this was the last page).
        """
        stmt = build_list_statement(
            score_min=score_min,
            statuses=statuses,
            stages=stages,
            exchange=exchange,
            symbol_query=symbol_query,
            cursor=decode_opportunity_cursor(cursor),
            limit=limit,
        )
        rows = (await self.session.execute(stmt)).all()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [
            OpportunityListRow(
                id=row.id,
                market_id=row.market_id,
                exchange=row.exchange,
                symbol=row.symbol,
                market_type=row.market_type,
                direction=row.direction,
                score=row.score,
                confidence=row.confidence,
                status=row.status,
                stage=row.stage,
                regime=row.regime,
                weights_version=row.weights_version,
                first_seen_at=row.first_seen_at,
                last_updated_at=row.last_updated_at,
            )
            for row in page
        ]
        next_cursor = (
            encode_opportunity_cursor(page[-1].score, page[-1].id) if has_more and page else None
        )
        return items, next_cursor

    async def get_detail(self, opportunity_id: uuid.UUID) -> OpportunityDetailRow | None:
        stmt = (
            select(
                Opportunity.id,
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
                Opportunity.regime_id,
                Opportunity.weights_version,
                Opportunity.decomposition,
                Opportunity.explanation,
                Opportunity.feature_snapshot,
                Opportunity.below_40_since,
                Opportunity.expired_at,
                Opportunity.first_seen_at,
                Opportunity.last_updated_at,
            )
            .join(Market, Market.id == Opportunity.market_id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .outerjoin(MarketRegimeRow, MarketRegimeRow.id == Opportunity.regime_id)
            .where(Opportunity.id == opportunity_id)
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return None
        return OpportunityDetailRow(
            id=row.id,
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
            regime_id=row.regime_id,
            weights_version=row.weights_version,
            decomposition=row.decomposition,
            explanation=row.explanation,
            feature_snapshot=row.feature_snapshot,
            below_40_since=row.below_40_since,
            expired_at=row.expired_at,
            first_seen_at=row.first_seen_at,
            last_updated_at=row.last_updated_at,
        )

    async def list_active_anomalies(self, market_id: uuid.UUID) -> Sequence[Anomaly]:
        stmt = (
            select(Anomaly)
            .where(Anomaly.market_id == market_id, Anomaly.status == AnomalyStatus.ACTIVE)
            .order_by(Anomaly.detected_at.desc())
        )
        return (await self.session.execute(stmt)).scalars().all()

    async def list_history(
        self, opportunity_id: uuid.UUID, *, limit: int = DEFAULT_HISTORY_LIMIT
    ) -> Sequence[OpportunityHistory]:
        stmt = (
            select(OpportunityHistory)
            .where(OpportunityHistory.opportunity_id == opportunity_id)
            .order_by(OpportunityHistory.ts.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(rows))
