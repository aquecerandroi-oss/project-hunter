"""Counts behind ``GET /api/v1/radar/coverage`` — global, no-RLS reads over
``markets``, ``anomalies``, ``opportunity_history``, ``opportunity_weights``
and ``feature_baselines`` (T3.46, ``.claude/state/notes-T3.46.md``).

Cost note (review of T3.46c): ``MAX(opportunity_history.score)``,
``MIN(anomalies.detected_at)`` and the ``COUNT`` over ``feature_baselines`` have
no covering index today and run uncached on every ``/radar`` and
``/opportunities`` load; the three tables only grow. Cheap now (2e5 rows);
when coverage reaches the whole universe, add ``opportunity_history(score)``
and ``anomalies(detected_at)`` (brief T3.46d) or cache the block for 60 s.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import func, select

from hunter_core.db.models.analysis import Anomaly, OpportunityHistory, OpportunityWeights
from hunter_core.db.models.analysis_baselines import FeatureBaseline
from hunter_core.db.models.markets import Market
from hunter_core.domain.enums import AnomalyType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["ANOMALY_LOOKBACK", "BaselineGateProgress", "RadarCoverageRepository"]

ANOMALY_LOOKBACK = timedelta(days=31)
"""Window for ``RadarDetectorOut.rows_31d`` — long enough to show a rare
detector without pretending the whole 1.8-day history (T3.46) is a stable
rate."""


@dataclass(frozen=True, slots=True)
class BaselineGateProgress:
    passing: int
    total: int
    gate_version: str


class RadarCoverageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def markets_monitored(self) -> int:
        stmt = select(func.count()).select_from(Market).where(Market.is_monitored.is_(True))
        return (await self.session.execute(stmt)).scalar_one()

    async def markets_with_anomaly(self) -> int:
        stmt = select(func.count(func.distinct(Anomaly.market_id)))
        return (await self.session.execute(stmt)).scalar_one()

    async def first_anomaly_at(self) -> datetime | None:
        stmt = select(func.min(Anomaly.detected_at))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def max_score_ever(self) -> Decimal | None:
        """The ceiling ``opportunity_history``'s full series ever recorded —
        the same read T3.46's inventory query used (``OpportunityHistory``,
        not ``Opportunity.peak_score``, so a sample from an episode that has
        since expired still counts, unlike a per-episode column that stops
        mattering once the row itself is gone)."""
        stmt = select(func.max(OpportunityHistory.score))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def anomaly_rows_by_type(self, *, since: datetime) -> dict[AnomalyType, int]:
        stmt = (
            select(Anomaly.type, func.count())
            .where(Anomaly.detected_at >= since)
            .group_by(Anomaly.type)
        )
        rows = (await self.session.execute(stmt)).all()
        return {row[0]: row[1] for row in rows}

    async def baseline_gate_progress(self) -> BaselineGateProgress | None:
        """``None`` when no ``opportunity_weights`` row is active, or the
        active row carries no usable ``baseline_gate`` block — a fact
        distinct from "0 %", which would claim a gate exists and nothing
        clears it.
        """
        weights_stmt = select(OpportunityWeights.version, OpportunityWeights.weights).where(
            OpportunityWeights.is_active.is_(True)
        )
        active = (await self.session.execute(weights_stmt)).first()
        if active is None:
            return None
        version = cast(str, active[0])
        weights_raw: Any = active[1]
        gate_raw: Any = None
        if isinstance(weights_raw, dict):
            gate_raw = cast("dict[str, Any]", weights_raw).get("baseline_gate")
        if not isinstance(gate_raw, dict):
            return None
        gate = cast("dict[str, Any]", gate_raw)
        try:
            min_distinct_days = int(gate["min_distinct_days"])
            min_valid_observations = int(gate["min_valid_observations"])
        except (KeyError, TypeError, ValueError):
            return None
        stmt = select(
            func.count(),
            func.count().filter(
                FeatureBaseline.distinct_days >= min_distinct_days,
                FeatureBaseline.sample_size >= min_valid_observations,
            ),
        )
        total, passing = (await self.session.execute(stmt)).one()
        return BaselineGateProgress(passing=passing, total=total, gate_version=version)
