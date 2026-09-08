"""``GET /api/v1/lab/shadow/{scoreboard,curve}`` — brief T3.18.

Global, no-RLS reads, same as ``routers/lab.py`` (DATABASE.md §16): any
authenticated user, no organization — Shadow Lab tables carry no
``organization_id`` and there is no schema change in this brief's scope to
add one. New router file rather than growing ``routers/lab.py`` past the
350-line budget; ``LabSession``/``resolve_as_of`` are shared verbatim from
there rather than duplicated.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter

from hunter_api.repositories.lab_scoreboard import LabScoreboardRepository
from hunter_api.routers.lab import LabSession, resolve_as_of
from hunter_api.schemas.lab_curve import CurveOut
from hunter_api.schemas.lab_scoreboard import ScoreboardOut, ScoreboardRowOut
from hunter_api.services.lab_curve import build_curve
from hunter_api.services.lab_scoreboard import build_scoreboard, build_scoreboard_row

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/lab/shadow", tags=["lab"])


@router.get("/scoreboard", response_model=ScoreboardOut, summary="Shadow Lab version scoreboard")
async def get_scoreboard(session: LabSession, as_of: datetime | None = None) -> ScoreboardOut:
    resolved_as_of = resolve_as_of(as_of)
    repo = LabScoreboardRepository(session)
    versions = await repo.versions_with_signals(resolved_as_of)
    rows: list[ScoreboardRowOut] = []
    for meta in versions:
        version_rows = await repo.rows_for(meta.id, resolved_as_of)
        rows.append(build_scoreboard_row(meta, version_rows, resolved_as_of))
    return build_scoreboard(as_of=resolved_as_of, rows=rows)


@router.get("/curve", response_model=CurveOut, summary="Shadow Lab cumulative net-R curve")
async def get_curve(
    session: LabSession, version_id: uuid.UUID, as_of: datetime | None = None
) -> CurveOut:
    resolved_as_of = resolve_as_of(as_of)
    repo = LabScoreboardRepository(session)
    rows = await repo.rows_for(version_id, resolved_as_of)
    return build_curve(strategy_version_id=version_id, rows=rows, as_of=resolved_as_of)
