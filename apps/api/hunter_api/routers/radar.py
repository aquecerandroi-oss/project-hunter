"""``GET /api/v1/radar`` — the cross-market opportunity radar (PIPELINE.md §5).

Not a tenant route: the scored opportunities are global (module docstring of
``repositories/radar.py``). ``org_id`` is an optional query parameter, not a
path segment, because the two fields it unlocks
(``in_position``/``risk_blocked``) are the only per-organization part of an
otherwise global response — see ``services/radar_org_derivation.py``.

The session is opened by ``routers/radar_common.py::analysis_scope`` in the
body rather than taken as a ``Depends``: see that module for why (one pooled
connection per request, never two).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, Request

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.deps import get_redis
from hunter_api.repositories.base import MAX_PAGE_SIZE
from hunter_api.repositories.radar import RadarFilters
from hunter_api.routers.radar_common import analysis_scope
from hunter_api.schemas.radar import (
    MAX_SCORE,
    MAX_VOLATILITY,
    RadarPage,
    RadarSortKey,
    RadarStatusFilter,
    SortOrder,
)
from hunter_api.schemas.radar_coverage import RadarCoverageOut
from hunter_api.services.radar import build_radar_page, resolve_status_tokens
from hunter_api.services.radar_coverage import build_radar_coverage
from hunter_core.domain.enums import AnomalyType, MarketRegime, OpportunityStage

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])

Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]


@router.get("", response_model=RadarPage, summary="List the opportunity radar")
async def list_radar(
    request: Request,
    principal: CurrentPrincipal,
    org_id: uuid.UUID | None = None,
    score_min: Annotated[Decimal | None, Query(ge=0, le=MAX_SCORE)] = None,
    status: Annotated[list[RadarStatusFilter] | None, Query()] = None,
    stage: Annotated[list[OpportunityStage] | None, Query()] = None,
    exchange: Annotated[str | None, Query(max_length=32)] = None,
    anomaly_type: AnomalyType | None = None,
    regime: MarketRegime | None = None,
    volatility_min: Annotated[Decimal | None, Query(ge=0, le=MAX_VOLATILITY)] = None,
    volatility_max: Annotated[Decimal | None, Query(ge=0, le=MAX_VOLATILITY)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    sort: RadarSortKey = "score",
    order: SortOrder = "desc",
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    cursor: str | None = None,
) -> RadarPage:
    async with analysis_scope(request, principal, org_id) as scope:
        statuses = resolve_status_tokens(status, has_org=scope.org_derivation is not None)
        filters = RadarFilters(
            score_min=score_min,
            statuses=statuses,
            stages=tuple(stage) if stage else (),
            exchange=exchange,
            anomaly_type=anomaly_type,
            regime=regime,
            volatility_min=volatility_min,
            volatility_max=volatility_max,
            symbol_query=q,
            sort=sort,
            order=order,
        )
        return await build_radar_page(
            scope.session,
            filters,
            limit=limit,
            cursor=cursor,
            org_derivation=scope.org_derivation,
        )


@router.get(
    "/coverage",
    response_model=RadarCoverageOut,
    summary="How much of the Radar exists yet (coverage, baselines, detectors)",
)
async def get_radar_coverage(
    request: Request, principal: CurrentPrincipal, redis: Redis
) -> RadarCoverageOut:
    """T3.46 (``.claude/state/notes-T3.46.md``): the Radar/Opportunities pages
    read this to say, in numbers, why the list has never had a candidate —
    global, not tenant-scoped (same reasoning as ``list_radar`` above), so no
    ``org_id`` is accepted here."""
    async with analysis_scope(request, principal) as scope:
        return await build_radar_coverage(scope.session, redis)
