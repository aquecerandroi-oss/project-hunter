"""``GET /api/v1/regime`` and ``/regime/history`` — PIPELINE.md §4. Global,
no-RLS read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Depends, Query, Request

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.deps import get_redis
from hunter_api.repositories.base import MAX_PAGE_SIZE, clamp_page_size
from hunter_api.repositories.regime import RegimeRepository
from hunter_api.routers.radar_common import analysis_scope
from hunter_api.schemas.regime import RegimeCurrentOut, RegimeHistoryPage
from hunter_api.schemas.system import WorkerLivenessStatus
from hunter_api.services.regime import build_current, build_history_page
from hunter_api.services.system_status import scan_heartbeats
from hunter_core.domain.enums import RegimeScope
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/regime", tags=["regime"])

Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]


async def _scanner_alive(redis: redis_asyncio.Redis) -> bool:
    """Whether an ``hb:scanner:*`` heartbeat reads ``alive`` right now.

    A Redis failure here is reported as "not alive" — this staleness signal
    fails safe (a regime shown without confirmation of a live classifier is
    marked stale) rather than raising a 503 for an endpoint whose core data
    came back from Postgres just fine.
    """
    try:
        heartbeats = await scan_heartbeats(redis)
    except redis_exceptions.RedisError:
        logger.warning("regime_scanner_heartbeat_redis_error")
        return False
    return any(h.role == "scanner" and h.status is WorkerLivenessStatus.ALIVE for h in heartbeats)


@router.get("", response_model=RegimeCurrentOut, summary="Current market regime per scope")
async def get_current_regime(
    request: Request, principal: CurrentPrincipal, redis: Redis
) -> RegimeCurrentOut:
    async with analysis_scope(request, principal) as scope:
        rows = await RegimeRepository(scope.session).current_per_scope()
    return build_current(rows, scanner_alive=await _scanner_alive(redis))


@router.get("/history", response_model=RegimeHistoryPage, summary="Regime history")
async def get_regime_history(
    request: Request,
    principal: CurrentPrincipal,
    redis: Redis,
    scope: RegimeScope | None = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    cursor: str | None = None,
) -> RegimeHistoryPage:
    async with analysis_scope(request, principal) as db:
        rows, next_cursor = await RegimeRepository(db.session).history(
            scope=scope, limit=clamp_page_size(limit), cursor=cursor
        )
    return build_history_page(rows, next_cursor, scanner_alive=await _scanner_alive(redis))
