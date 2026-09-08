"""``GET /api/v1/lab/shadow/{scoreboard,curve}`` — brief T3.18, extended T3.18b.

Global, no-RLS reads, same as ``routers/lab.py`` (DATABASE.md §16): any
authenticated user, no organization — Shadow Lab tables carry no
``organization_id`` and there is no schema change in this brief's scope to
add one. New router file rather than growing ``routers/lab.py`` past the
350-line budget; ``LabSession``/``resolve_as_of`` are shared verbatim from
there rather than duplicated.

T3.18b adds two blocks per scoreboard row (``replay``, ``replication``,
D14/D15 — the verdict and maturity stay computed on ``prospective`` alone,
untouched by either) and a ``cohort`` query param on the curve so the web can
draw a replay line dashed beside the live one.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, status

from hunter_api.errors import HunterError
from hunter_api.repositories.lab_replication import LabReplicationRepository
from hunter_api.repositories.lab_scoreboard import REPLAY_COHORT_WILDCARD, LabScoreboardRepository
from hunter_api.routers.lab import LabSession, resolve_as_of
from hunter_api.schemas.lab_curve import CurveOut
from hunter_api.schemas.lab_scoreboard import ScoreboardOut, ScoreboardRowOut
from hunter_api.services.lab_curve import build_curve
from hunter_api.services.lab_replication import build_replication_block
from hunter_api.services.lab_scoreboard import build_scoreboard, build_scoreboard_row
from hunter_api.services.lab_scoreboard_replay import build_replay_block
from hunter_core.domain.enums import ShadowCohort

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/lab/shadow", tags=["lab"])


class InvalidCohortError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="invalid-cohort",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="'cohort' must be 'prospective', 'replay', or one exact shadow cohort.",
        )


def _resolve_curve_cohort(cohort: str) -> str:
    """``prospective`` (default), ``replay`` (every run of this version at
    once — brief T3.18b, item 3) or one exact cohort
    (``ShadowCohort.is_valid``: ``replay:<uuid>`` or
    ``replication:<parent>:<k>``). Anything else is a ``422``, the same shape
    ``InvalidAsOfError`` uses for a malformed ``as_of``.
    """
    if cohort in (ShadowCohort.PROSPECTIVE, REPLAY_COHORT_WILDCARD) or ShadowCohort.is_valid(
        cohort
    ):
        return cohort
    raise InvalidCohortError


@router.get("/scoreboard", response_model=ScoreboardOut, summary="Shadow Lab version scoreboard")
async def get_scoreboard(session: LabSession, as_of: datetime | None = None) -> ScoreboardOut:
    resolved_as_of = resolve_as_of(as_of)
    repo = LabScoreboardRepository(session)
    replication_repo = LabReplicationRepository(session)
    versions = await repo.versions_with_signals(resolved_as_of)
    rows: list[ScoreboardRowOut] = []
    for meta in versions:
        version_rows = await repo.rows_for(meta.id, resolved_as_of)

        replay_rows = await repo.rows_for(meta.id, resolved_as_of, cohort=REPLAY_COHORT_WILDCARD)
        runs_summary = await repo.replay_runs_summary(meta.id)
        replay_block = build_replay_block(rows=replay_rows, runs=runs_summary, as_of=resolved_as_of)

        promising_at = await replication_repo.promising_at(meta.id)
        parent_outcomes = await replication_repo.parent_outcomes(meta.id, as_of=resolved_as_of)
        siblings_meta = await replication_repo.siblings(meta.id)
        siblings = [
            await replication_repo.sibling_population(sibling, meta.id, as_of=resolved_as_of)
            for sibling in siblings_meta
        ]
        replication_block = build_replication_block(
            version_id=meta.id,
            promising_at=promising_at,
            parent_outcomes=parent_outcomes,
            siblings=siblings,
        )

        rows.append(
            build_scoreboard_row(
                meta,
                version_rows,
                resolved_as_of,
                replay=replay_block,
                replication=replication_block,
            )
        )
    return build_scoreboard(as_of=resolved_as_of, rows=rows)


@router.get("/curve", response_model=CurveOut, summary="Shadow Lab cumulative net-R curve")
async def get_curve(
    session: LabSession,
    version_id: uuid.UUID,
    as_of: datetime | None = None,
    cohort: str = ShadowCohort.PROSPECTIVE,
) -> CurveOut:
    resolved_as_of = resolve_as_of(as_of)
    resolved_cohort = _resolve_curve_cohort(cohort)
    repo = LabScoreboardRepository(session)
    rows = await repo.rows_for(version_id, resolved_as_of, cohort=resolved_cohort)
    return build_curve(strategy_version_id=version_id, rows=rows, as_of=resolved_as_of)
