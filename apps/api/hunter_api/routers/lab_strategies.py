"""``GET /api/v1/lab/shadow/strategies`` — brief T3.25.

Global, no-RLS read, same as ``routers/lab.py`` (DATABASE.md §16): any
authenticated user, no organization. ``LabSession``/``resolve_as_of`` are
shared verbatim from there, per the convention ``routers/lab_scoreboard.py``
already set.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from hunter_api.repositories.lab_strategies import LabStrategiesRepository
from hunter_api.routers.lab import LabSession, resolve_as_of
from hunter_api.schemas.lab_strategies import StrategiesOut
from hunter_api.services.lab_strategies import build_strategies

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/lab/shadow", tags=["lab"])


@router.get(
    "/strategies",
    response_model=StrategiesOut,
    summary="Shadow Lab strategy catalogue: versions, parameters, lineage and verdict",
)
async def list_strategies(session: LabSession, as_of: datetime | None = None) -> StrategiesOut:
    resolved_as_of = resolve_as_of(as_of)
    repo = LabStrategiesRepository(session)
    return await build_strategies(session, repo, as_of=resolved_as_of)
