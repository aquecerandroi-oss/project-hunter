"""``GET /api/v1/lab/shadow/signals`` — one row per decision, snapshot of its
tracked outcome. Global, no-RLS read (DATABASE.md §16).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_api.repositories.lab_common import (
    COHORT,
    DECISION_AT,
    decode_lab_cursor,
    encode_lab_cursor,
)
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SignalRow", "LabSignalsRepository"]


@dataclass(frozen=True, slots=True)
class SignalRow:
    signal_id: uuid.UUID
    strategy_version_id: uuid.UUID
    market: str
    cohort: str
    decision_at: datetime
    stop: Decimal | None
    targets: list[Any]
    supporting_features: dict[str, Any]
    virtual_entry: Decimal | None
    entry_ts: datetime | None
    exit_price: Decimal | None
    exit_ts: datetime | None
    result: OutcomeResult
    tracking_state: ShadowTrackingState
    no_entry_reason: str | None
    censored_reason: str | None
    r_multiple: Decimal | None
    meta: dict[str, Any]


class LabSignalsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_page(
        self,
        *,
        strategy_version_id: uuid.UUID | None,
        market: str | None,
        tracking_state: ShadowTrackingState | None,
        result: OutcomeResult | None,
        cohort: str,
        cursor: str | None,
        limit: int,
    ) -> tuple[list[SignalRow], str | None]:
        after = decode_lab_cursor(cursor)
        stmt = (
            select(AgentSignal, SignalOutcome, Market.symbol, DECISION_AT.label("decision_at"))
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(COHORT == cohort)
        )
        if strategy_version_id is not None:
            stmt = stmt.where(AgentSignal.strategy_version_id == strategy_version_id)
        if market is not None:
            stmt = stmt.where(Market.symbol == market)
        if tracking_state is not None:
            stmt = stmt.where(SignalOutcome.tracking_state == tracking_state)
        if result is not None:
            stmt = stmt.where(SignalOutcome.result == result)
        if after is not None:
            after_decision_at, after_id = after
            stmt = stmt.where(
                (DECISION_AT < after_decision_at)
                | ((DECISION_AT == after_decision_at) & (AgentSignal.id < after_id))
            )
        stmt = stmt.order_by(DECISION_AT.desc(), AgentSignal.id.desc()).limit(limit + 1)
        rows = (await self.session.execute(stmt)).all()
        has_more = len(rows) > limit
        page = rows[:limit]
        items = [
            _row_from(signal, outcome, symbol, decision_at)
            for signal, outcome, symbol, decision_at in page
        ]
        next_cursor = (
            encode_lab_cursor(items[-1].decision_at, items[-1].signal_id) if has_more else None
        )
        return items, next_cursor


def _row_from(
    signal: AgentSignal, outcome: SignalOutcome, symbol: str, decision_at: datetime
) -> SignalRow:
    return SignalRow(
        signal_id=signal.id,
        strategy_version_id=signal.strategy_version_id,
        market=symbol,
        cohort=signal.supporting_features.get("cohort", ""),
        decision_at=decision_at,
        stop=signal.stop,
        targets=list(signal.targets or []),
        supporting_features=signal.supporting_features,
        virtual_entry=outcome.virtual_entry,
        entry_ts=outcome.entry_ts,
        exit_price=outcome.exit_price,
        exit_ts=outcome.exit_ts,
        result=outcome.result,
        tracking_state=outcome.tracking_state,
        no_entry_reason=outcome.no_entry_reason,
        censored_reason=outcome.censored_reason,
        r_multiple=outcome.r_multiple,
        meta=outcome.meta,
    )
