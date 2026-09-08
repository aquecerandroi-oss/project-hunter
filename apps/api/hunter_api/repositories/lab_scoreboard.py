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

from sqlalchemy import func, select

from hunter_api.repositories.lab_common import COHORT
from hunter_api.repositories.lab_summary import OutcomeRow
from hunter_core.db.models.agents import AgentSignal, SignalOutcome, Strategy, StrategyVersion
from hunter_core.db.models.replay_runs import ReplayRunRow
from hunter_core.domain.enums import ShadowCohort, StrategyVersionStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import ColumnElement

__all__ = [
    "REPLAY_COHORT_WILDCARD",
    "ReplayRunsSummary",
    "ScoreboardVersionMeta",
    "LabScoreboardRepository",
]

REPLAY_COHORT_WILDCARD = "replay"
"""Not a real cohort (``ShadowCohort.is_valid`` refuses it): a caller-facing
shorthand for "every ``replay:<uuid>`` cohort of this version", used by both
the scoreboard's replay block (brief T3.18b, item 1) and ``GET .../curve``
(item 3) so the two never define "all replay evidence" two different ways.
"""


def _cohort_condition(cohort: str) -> ColumnElement[bool]:
    """``cohort`` as a ``WHERE`` condition against the JSONB envelope's own
    ``cohort`` field: the wildcard becomes a prefix match, anything else
    (``prospective``, one exact ``replay:<uuid>``, one
    ``replication:<parent>:<k>``) is an exact match.
    """
    if cohort == REPLAY_COHORT_WILDCARD:
        return COHORT.like(f"{ShadowCohort.REPLAY_PREFIX}%")
    return COHORT == cohort


@dataclass(frozen=True, slots=True)
class ReplayRunsSummary:
    """The ``replay_runs`` receipts of one version, summed across every run
    (brief T3.18b, item 1: ``runs``/``decisions_simulated``/``window_from``/
    ``window_to``) — never per slice, since a slice is not the unit the
    scoreboard reports (DATABASE.md §25.1)."""

    runs: int
    """Count of *distinct* ``run_id`` values — the number of times a replay
    was launched for this version, not the number of slices it took."""
    bars_evaluated: int
    """Sum of every slice's ``bars_evaluated`` — the D14 mass counter."""
    window_from: datetime | None
    window_to: datetime | None


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

    async def rows_for(
        self, version_id: uuid.UUID, as_of: datetime, *, cohort: str = ShadowCohort.PROSPECTIVE
    ) -> list[OutcomeRow]:
        """Every outcome row emitted by ``version_id`` at or before ``as_of``
        under ``cohort`` — shared by the scoreboard's prospective and replay
        blocks and by the curve (brief T3.18b, items 1 and 3) so no two of
        them can disagree on what a given cohort's population is.
        ``cohort`` is ``"prospective"`` (default), one exact cohort string
        (``"replay:<uuid>"``, ``"replication:<parent>:<k>"``) or the
        ``"replay"`` wildcard (:data:`REPLAY_COHORT_WILDCARD`) meaning every
        replay run of this version at once.
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
                _cohort_condition(cohort),
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

    async def replay_runs_summary(self, version_id: uuid.UUID) -> ReplayRunsSummary:
        """Every ``replay_runs`` slice this version has, summed into the
        three numbers the replay block needs beyond its outcome rows: how
        many runs, how many bars they evaluated in total, and the window
        they span (brief T3.18b, item 1). ``runs == 0`` is how the caller
        knows there is no replay evidence at all — a version replayed but not
        yet receipted (DATABASE.md §25, concern 1 of ``notes-T3.19d.md``)
        would still show its ``operations_closed`` from the outcome rows
        alone with this block's counters at zero, never a crash.
        """
        row = (
            await self.session.execute(
                select(
                    func.count(func.distinct(ReplayRunRow.run_id)),
                    func.coalesce(func.sum(ReplayRunRow.bars_evaluated), 0),
                    func.min(ReplayRunRow.window_from),
                    func.max(ReplayRunRow.window_to),
                ).where(ReplayRunRow.strategy_version_id == version_id)
            )
        ).one()
        runs, bars_evaluated, window_from, window_to = row
        return ReplayRunsSummary(
            runs=runs,
            bars_evaluated=int(bars_evaluated),
            window_from=window_from,
            window_to=window_to,
        )
