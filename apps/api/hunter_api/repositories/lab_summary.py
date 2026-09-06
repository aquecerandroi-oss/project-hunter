"""``GET /api/v1/lab/shadow/summary`` reads — global, no-RLS (DATABASE.md §16).

Fetches raw rows and lets ``services/lab_summary.py`` do the counting: the
horizon-maturation gate (contract-S3-lab.md, Astra must-fix 2) needs
``meta.entry_plan.entry_bar_open``/``meta.horizon_s``, both JSONB, so filtering
it in SQL would mean a generated expression for a table with a few hundred
rows today — not worth it yet (declared as a pending item in the contract).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from hunter_api.repositories.lab_common import COHORT, DECISION_AT
from hunter_core.db.models.agents import AgentSignal, SignalOutcome, Strategy, StrategyVersion
from hunter_core.domain.enums import OutcomeResult, ShadowTrackingState, StrategyVersionStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["OutcomeRow", "VersionMeta", "LabSummaryRepository"]


@dataclass(frozen=True, slots=True)
class VersionMeta:
    id: uuid.UUID
    strategy_key: str
    version: str
    status: StrategyVersionStatus
    code_ref: str | None
    activated_at: datetime | None
    deprecated_at: datetime | None
    default_parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OutcomeRow:
    tracking_state: ShadowTrackingState
    result: OutcomeResult
    no_entry_reason: str | None
    censored_reason: str | None
    entry_ts: datetime | None
    exit_ts: datetime | None
    r_multiple: Decimal | None
    meta: dict[str, Any]
    market_id: uuid.UUID
    decision_at: datetime


class LabSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def activated_versions(self) -> list[VersionMeta]:
        """Every version that ever ran an experiment (``draft`` rows never did)."""
        rows = (
            await self.session.execute(
                select(StrategyVersion, Strategy.key)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(StrategyVersion.activated_at.is_not(None))
                .order_by(Strategy.key, StrategyVersion.version)
            )
        ).all()
        return [
            VersionMeta(
                id=sv.id,
                strategy_key=key,
                version=sv.version,
                status=sv.status,
                code_ref=sv.code_ref,
                activated_at=sv.activated_at,
                deprecated_at=sv.deprecated_at,
                default_parameters=dict(sv.default_parameters or {}),
            )
            for sv, key in rows
        ]

    async def outcomes_for(
        self,
        version_id: uuid.UUID,
        *,
        cohort: str,
        since: datetime | None,
        as_of: datetime,
    ) -> list[OutcomeRow]:
        stmt = (
            select(
                SignalOutcome.tracking_state,
                SignalOutcome.result,
                SignalOutcome.no_entry_reason,
                SignalOutcome.censored_reason,
                SignalOutcome.entry_ts,
                SignalOutcome.exit_ts,
                SignalOutcome.r_multiple,
                SignalOutcome.meta,
                AgentSignal.market_id,
                DECISION_AT.label("decision_at"),
            )
            .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
            .where(
                AgentSignal.strategy_version_id == version_id,
                COHORT == cohort,
                DECISION_AT <= as_of,
            )
        )
        if since is not None:
            stmt = stmt.where(DECISION_AT >= since)
        rows = (await self.session.execute(stmt)).all()
        return [
            OutcomeRow(
                tracking_state=r.tracking_state,
                result=r.result,
                no_entry_reason=r.no_entry_reason,
                censored_reason=r.censored_reason,
                entry_ts=r.entry_ts,
                exit_ts=r.exit_ts,
                r_multiple=r.r_multiple,
                meta=r.meta,
                market_id=r.market_id,
                decision_at=r.decision_at,
            )
            for r in rows
        ]
