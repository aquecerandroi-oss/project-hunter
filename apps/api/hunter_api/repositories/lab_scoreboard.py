"""``GET /api/v1/lab/shadow/{scoreboard,curve}`` reads — T3.18.

Global, no-RLS reads, same as every other Shadow Lab repository (DATABASE.md
§16): Shadow Lab tables carry no ``organization_id`` and no RLS policy by
design — research is shared across the product, never per-tenant. Reuses
``OutcomeRow`` from ``repositories/lab_summary.py`` verbatim rather than
declaring a parallel shape.

Population freeze uses ``agent_signals.emitted_at`` directly (the brief's
``as_of`` rule), not the ``supporting_features->>'decision_at'`` JSONB
expression ``lab_summary``/``lab_signals`` use: ``persist.py`` always writes
``emitted_at=record.decision_at`` (``services/strategy-worker/hunter_strategy_worker/persist.py:65``),
so the two are numerically identical for every row that exists, and the
native column has an index (``ix_agent_signals_version_emitted``) the JSONB
expression does not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_api.repositories.lab_common import COHORT
from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_core.db.models.agents import AgentSignal, SignalOutcome, Strategy, StrategyVersion
from hunter_core.domain.enums import ShadowCohort, StrategyVersionStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["ScoreboardVersionMeta", "LabScoreboardRepository"]


@dataclass(frozen=True, slots=True)
class ScoreboardVersionMeta:
    id: uuid.UUID
    strategy_key: str
    version: str
    purpose: str
    status: StrategyVersionStatus
    code_ref: str | None
    activated_at: datetime | None


class LabScoreboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def versions_with_signals(self, as_of: datetime) -> list[ScoreboardVersionMeta]:
        """One row per version that has **emitted at least one signal** by
        ``as_of`` — active, deprecated and draft-with-signals alike (brief
        T3.18, item 1). Deliberately not ``activated_at IS NOT NULL``
        (``lab_summary.LabSummaryRepository.activated_versions``): a version
        with zero signals within the frozen population would show an
        all-zero card that adds nothing, and "ever emitted" is the population
        the rest of this module actually measures.
        """
        rows = (
            await self.session.execute(
                select(StrategyVersion, Strategy.key)
                .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
                .where(
                    StrategyVersion.id.in_(
                        select(AgentSignal.strategy_version_id)
                        .where(
                            AgentSignal.emitted_at <= as_of,
                            COHORT == ShadowCohort.PROSPECTIVE,
                        )
                        .distinct()
                    )
                )
                .order_by(Strategy.key, StrategyVersion.version)
            )
        ).all()
        return [
            ScoreboardVersionMeta(
                id=sv.id,
                strategy_key=key,
                version=sv.version,
                purpose=sv.purpose,
                status=sv.status,
                code_ref=sv.code_ref,
                activated_at=sv.activated_at,
            )
            for sv, key in rows
        ]

    async def rows_for(self, version_id: uuid.UUID, as_of: datetime) -> list[OutcomeRow]:
        """Every ``prospective`` outcome row emitted by ``version_id`` at or
        before ``as_of`` — shared by both the scoreboard and the curve so the
        two endpoints never disagree on the population.
        """
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
                AgentSignal.emitted_at,
            )
            .join(AgentSignal, AgentSignal.id == SignalOutcome.signal_id)
            .where(
                AgentSignal.strategy_version_id == version_id,
                AgentSignal.emitted_at <= as_of,
                COHORT == ShadowCohort.PROSPECTIVE,
            )
        )
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
                decision_at=r.emitted_at,
            )
            for r in rows
        ]
