"""``GET /api/v1/lab/shadow/replays{,/{run_id}}`` — Backtests = replay, brief T3.25.

Global, no-RLS reads over ``replay_runs`` (DATABASE.md §25.5), same pattern as
``routers/lab_scoreboard.py``: ``LabSession``/``resolve_as_of`` shared from
``routers/lab.py``. Confirms, by test, that the cohort's outcomes reuse
``GET /lab/shadow/signals?cohort=replay:<uuid>`` (already accepted since
``0012_replication`` — brief item 2).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from hunter_api.errors import HunterError
from hunter_api.repositories.base import clamp_page_size
from hunter_api.repositories.lab_replays import LabReplaysRepository
from hunter_api.routers.lab import LabSession
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.lab_replays import ReplayRunDetailOut, ReplayRunOut
from hunter_api.services.lab_replays import build_run_detail, build_runs_page

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/lab/shadow", tags=["lab"])


class ReplayRunNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="replay-run-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No replay_runs slice names this run id.",
        )


@router.get(
    "/replays",
    response_model=CursorPage[ReplayRunOut],
    summary="Replay runs (backtests), newest first — honestly empty when none ran",
)
async def list_replays(
    session: LabSession, limit: int | None = None, cursor: str | None = None
) -> CursorPage[ReplayRunOut]:
    size = clamp_page_size(limit)
    summaries, next_cursor = await LabReplaysRepository(session).list_runs_page(
        limit=size, cursor=cursor
    )
    return build_runs_page(summaries, next_cursor)


@router.get(
    "/replays/{run_id}",
    response_model=ReplayRunDetailOut,
    summary="One replay run: its slices and the population by evaluation state",
)
async def get_replay(session: LabSession, run_id: uuid.UUID) -> ReplayRunDetailOut:
    repo = LabReplaysRepository(session)
    detail = await repo.run_detail(run_id)
    if detail is None:
        raise ReplayRunNotFoundError
    summary, slices = detail
    population_by_state = await repo.population_by_state(run_id)
    return build_run_detail(summary, slices, population_by_state)
