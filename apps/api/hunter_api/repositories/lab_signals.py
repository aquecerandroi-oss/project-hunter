"""``GET /api/v1/lab/shadow/signals`` — one row per decision, snapshot of its
tracked outcome. Global, no-RLS read (DATABASE.md §16).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import ColumnElement, func, select

from hunter_api.repositories.lab_common import (
    COHORT,
    DECISION_AT,
    LabSignalState,
    decode_lab_cursor,
    encode_lab_cursor,
    tracking_states_for_lab_state,
)
from hunter_core.db.models.agents import AgentSignal, SignalOutcome
from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["SignalRow", "SignalsPageResult", "LabSignalsRepository"]


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


@dataclass(frozen=True, slots=True)
class SignalsPageResult:
    """T3.37: one page plus the numbers the segment tabs and the pager need.

    ``totals`` is computed over the whole filtered dataset with every filter
    *except* ``state`` applied (cohort/version/market/window-adjacent filters
    stay; the segment itself does not narrow it) — the brief's fix for tabs
    that used to count only the 200 rows a page happened to load. ``page_from``/
    ``page_to`` are 1-based positions within the *current state's* ordering
    (``0``/``0`` when the page is empty).
    """

    items: list[SignalRow]
    next_cursor: str | None
    totals: dict[str, int]
    page_from: int
    page_to: int


class LabSignalsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_filters(
        self,
        *,
        strategy_version_id: uuid.UUID | None,
        market: str | None,
        tracking_state: ShadowTrackingState | None,
        result: OutcomeResult | None,
        cohort: str,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [COHORT == cohort]
        if strategy_version_id is not None:
            filters.append(AgentSignal.strategy_version_id == strategy_version_id)
        if market is not None:
            filters.append(Market.symbol == market)
        if tracking_state is not None:
            filters.append(SignalOutcome.tracking_state == tracking_state)
        if result is not None:
            filters.append(SignalOutcome.result == result)
        return filters

    async def _count_totals(self, filters: list[ColumnElement[bool]]) -> dict[str, int]:
        """One aggregate query, four ``FILTER`` clauses — the segment tabs'
        real totals over ``filters`` (state not among them).
        """
        stmt = (
            select(
                func.count()
                .filter(SignalOutcome.tracking_state == ShadowTrackingState.TERMINAL)
                .label("closed"),
                func.count()
                .filter(SignalOutcome.tracking_state == ShadowTrackingState.ACTIVE)
                .label("open"),
                func.count()
                .filter(
                    SignalOutcome.tracking_state.in_(tracking_states_for_lab_state("pending") or ())
                )
                .label("pending"),
                func.count().label("total"),
            )
            .select_from(AgentSignal)
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(*filters)
        )
        row = (await self.session.execute(stmt)).one()
        return {"closed": row.closed, "open": row.open, "pending": row.pending, "all": row.total}

    async def _rank_of_cursor(
        self, filters: list[ColumnElement[bool]], after: tuple[datetime, uuid.UUID] | None
    ) -> int:
        """Position (1-based) of the cursor's row within ``filters``' ordering
        -- ``0`` when there is no cursor (first page). ``page_from`` is this
        plus one; a single indexed count, same predicate shape as the keyset
        seek itself.
        """
        if after is None:
            return 0
        after_decision_at, after_id = after
        stmt = (
            select(func.count())
            .select_from(AgentSignal)
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(
                *filters,
                (DECISION_AT > after_decision_at)
                | ((DECISION_AT == after_decision_at) & (AgentSignal.id >= after_id)),
            )
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def list_page(
        self,
        *,
        strategy_version_id: uuid.UUID | None,
        market: str | None,
        tracking_state: ShadowTrackingState | None,
        result: OutcomeResult | None,
        cohort: str,
        state: LabSignalState,
        cursor: str | None,
        page_size: int,
    ) -> SignalsPageResult:
        after = decode_lab_cursor(cursor)
        base_filters = self._base_filters(
            strategy_version_id=strategy_version_id,
            market=market,
            tracking_state=tracking_state,
            result=result,
            cohort=cohort,
        )
        totals = await self._count_totals(base_filters)

        segment_states = tracking_states_for_lab_state(state)
        segment_filters = [*base_filters]
        if segment_states is not None:
            segment_filters.append(SignalOutcome.tracking_state.in_(segment_states))

        rank_before = await self._rank_of_cursor(segment_filters, after)

        stmt = (
            select(AgentSignal, SignalOutcome, Market.symbol, DECISION_AT.label("decision_at"))
            .join(SignalOutcome, SignalOutcome.signal_id == AgentSignal.id)
            .join(Market, Market.id == AgentSignal.market_id)
            .where(*segment_filters)
        )
        if after is not None:
            after_decision_at, after_id = after
            stmt = stmt.where(
                (DECISION_AT < after_decision_at)
                | ((DECISION_AT == after_decision_at) & (AgentSignal.id < after_id))
            )
        stmt = stmt.order_by(DECISION_AT.desc(), AgentSignal.id.desc()).limit(page_size + 1)
        rows = (await self.session.execute(stmt)).all()
        has_more = len(rows) > page_size
        page = rows[:page_size]
        items = [
            _row_from(signal, outcome, symbol, decision_at)
            for signal, outcome, symbol, decision_at in page
        ]
        next_cursor = (
            encode_lab_cursor(items[-1].decision_at, items[-1].signal_id) if has_more else None
        )
        page_from = rank_before + 1 if items else 0
        page_to = page_from + len(items) - 1 if items else 0
        return SignalsPageResult(
            items=items,
            next_cursor=next_cursor,
            totals=totals,
            page_from=page_from,
            page_to=page_to,
        )


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
