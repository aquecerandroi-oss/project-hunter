"""``GET /api/v1/lab/shadow/strategies`` reads — brief T3.25.

Global, no-RLS reads, same as every other Shadow Lab repository (DATABASE.md
§16): every ``strategies``/``strategy_versions`` row, catalogue-wide, plus one
extra query for the signal counts per cohort family (DATABASE.md §24.1).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from hunter_api.repositories.lab_common import COHORT
from hunter_core.db.models.agents import AgentSignal, Strategy, StrategyVersion
from hunter_core.domain.enums import StrategyVersionStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["StrategyRow", "VersionDetailRow", "LabStrategiesRepository"]

COHORT_FAMILIES = ("prospective", "replay", "replication")
"""The three branches ``SHADOW_COHORT_PATTERN`` allows (DATABASE.md §24.1),
keyed by the segment before the first ``:``."""


@dataclass(frozen=True, slots=True)
class StrategyRow:
    id: uuid.UUID
    key: str
    name: str
    description: str | None
    category: str | None


@dataclass(frozen=True, slots=True)
class VersionDetailRow:
    id: uuid.UUID
    strategy_id: uuid.UUID
    version: str
    status: StrategyVersionStatus
    purpose: str
    code_ref: str | None
    activated_at: datetime | None
    deprecated_at: datetime | None
    parameters_schema: dict[str, Any]
    default_parameters: dict[str, Any]
    replication_parent_id: uuid.UUID | None
    replication_index: int | None
    promising_at: datetime | None
    promising_by: str | None


class LabStrategiesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_strategies(self) -> list[StrategyRow]:
        rows = (await self.session.execute(select(Strategy).order_by(Strategy.key))).scalars()
        return [
            StrategyRow(
                id=row.id,
                key=row.key,
                name=row.name,
                description=row.description,
                category=row.category,
            )
            for row in rows
        ]

    async def list_versions(self) -> list[VersionDetailRow]:
        rows = (
            await self.session.execute(
                select(StrategyVersion).order_by(
                    StrategyVersion.strategy_id, StrategyVersion.version
                )
            )
        ).scalars()
        return [
            VersionDetailRow(
                id=row.id,
                strategy_id=row.strategy_id,
                version=row.version,
                status=row.status,
                purpose=row.purpose,
                code_ref=row.code_ref,
                activated_at=row.activated_at,
                deprecated_at=row.deprecated_at,
                parameters_schema=dict(row.parameters_schema or {}),
                default_parameters=dict(row.default_parameters or {}),
                replication_parent_id=row.replication_parent_id,
                replication_index=row.replication_index,
                promising_at=row.promising_at,
                promising_by=row.promising_by,
            )
            for row in rows
        ]

    async def signal_counts_by_version(self) -> dict[uuid.UUID, dict[str, int]]:
        """``{version_id: {"prospective": n, "replay": n, "replication": n}}``.

        One row per ``(version, cohort)`` pair, low cardinality (SHADOW-LAB.md's
        experiment volume is in the low hundreds) — bucketed in Python by the
        cohort's family segment rather than a second SQL expression, since the
        three families are already the ones ``COHORT_FAMILIES`` names.
        """
        rows = (
            await self.session.execute(
                select(AgentSignal.strategy_version_id, COHORT, func.count()).group_by(
                    AgentSignal.strategy_version_id, COHORT
                )
            )
        ).all()
        counts: dict[uuid.UUID, dict[str, int]] = defaultdict(
            lambda: dict.fromkeys(COHORT_FAMILIES, 0)
        )
        for version_id, cohort, n in rows:
            family = cohort.split(":", 1)[0]
            if family in COHORT_FAMILIES:
                counts[version_id][family] += n
        return counts
