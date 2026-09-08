"""Assembling ``GET /api/v1/lab/shadow/strategies`` — brief T3.25.

Reuses ``lab_scoreboard``'s verdict/maturity wiring verbatim (the brief: "reuse
the lab_scoreboard service, do not recompute") and ``LabScoreboardRepository.
rows_for`` for the same ``prospective``-only population the scoreboard itself
measures — a strategy version's verdict here and on ``/scoreboard`` can never
disagree.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hunter_api.repositories.lab_scoreboard import LabScoreboardRepository, ScoreboardVersionMeta
from hunter_api.repositories.lab_strategies import COHORT_FAMILIES
from hunter_api.schemas.lab_strategies import (
    LineageOut,
    SignalCountsOut,
    StrategiesOut,
    StrategyOut,
    StrategyVersionDetailOut,
)
from hunter_api.services.lab_scoreboard import build_scoreboard_row

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.repositories.lab_strategies import LabStrategiesRepository, VersionDetailRow

OBSIDIAN_STRATEGIES_DIR = "03-TRADING/Estrategias"


def _obsidian_page(key: str, version: str) -> str:
    return f"{OBSIDIAN_STRATEGIES_DIR}/{key}-{version}.md"


async def _version_detail(
    session: AsyncSession,
    repo: LabStrategiesRepository,
    version: VersionDetailRow,
    *,
    strategy_key: str,
    counts: dict[str, int],
    as_of: datetime,
) -> StrategyVersionDetailOut:
    scoreboard_repo = LabScoreboardRepository(session)
    rows = await scoreboard_repo.rows_for(version.id, as_of)
    meta = ScoreboardVersionMeta(
        id=version.id,
        strategy_key=strategy_key,
        version=version.version,
        purpose=version.purpose,
        status=version.status,
        code_ref=version.code_ref,
        activated_at=version.activated_at,
    )
    scoreboard_row = build_scoreboard_row(meta, rows, as_of)

    lineage: LineageOut | None = None
    if version.replication_parent_id is not None:
        # DATABASE.md §24.3's CHECK is a bicondition: a parent never travels
        # without its arm, so this is never ``None`` here.
        assert version.replication_index is not None
        lineage = LineageOut(
            replication_parent_id=version.replication_parent_id,
            replication_index=version.replication_index,
        )
    return StrategyVersionDetailOut(
        strategy_version_id=version.id,
        version=version.version,
        purpose=version.purpose,
        status=version.status,
        activated_at=version.activated_at,
        deprecated_at=version.deprecated_at,
        code_ref=version.code_ref,
        parameters_schema=version.parameters_schema,
        default_parameters=version.default_parameters,
        lineage=lineage,
        promising_at=version.promising_at,
        promising_by=version.promising_by,
        verdict=scoreboard_row.verdict,
        maturity=scoreboard_row.maturity,
        signal_counts=SignalCountsOut(
            prospective=counts.get("prospective", 0),
            replay=counts.get("replay", 0),
            replication=counts.get("replication", 0),
        ),
        obsidian_page=_obsidian_page(strategy_key, version.version),
    )


async def build_strategies(
    session: AsyncSession, repo: LabStrategiesRepository, *, as_of: datetime
) -> StrategiesOut:
    strategies = await repo.list_strategies()
    versions = await repo.list_versions()
    counts = await repo.signal_counts_by_version()

    by_strategy: dict[uuid.UUID, list[VersionDetailRow]] = {}
    for version in versions:
        by_strategy.setdefault(version.strategy_id, []).append(version)

    items: list[StrategyOut] = []
    for strategy in strategies:
        details = [
            await _version_detail(
                session,
                repo,
                version,
                strategy_key=strategy.key,
                counts=counts.get(version.id, dict.fromkeys(COHORT_FAMILIES, 0)),
                as_of=as_of,
            )
            for version in by_strategy.get(strategy.id, [])
        ]
        items.append(
            StrategyOut(
                strategy_id=strategy.id,
                key=strategy.key,
                name=strategy.name,
                description=strategy.description,
                category=strategy.category,
                versions=details,
            )
        )
    return StrategiesOut(as_of=as_of, items=items)
