"""``GET /api/v1/anomalies`` — PIPELINE.md §3. Global, no-RLS read: any
authenticated principal may read every row, same as ``routers/markets.py``.

Takes no ``org_id`` (nothing here is derived per organization), but opens its
session through ``routers/radar_common.py::analysis_scope`` like the other
three T2.6 routers, so the transaction's first round trip is inside the
Postgres-failure translator too.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.repositories.anomalies import AnomalyRepository
from hunter_api.repositories.base import MAX_PAGE_SIZE, clamp_page_size
from hunter_api.routers.radar_common import analysis_scope
from hunter_api.schemas.anomalies import AnomalyPage
from hunter_api.schemas.radar import MAX_SCORE
from hunter_api.services.anomalies import build_anomaly_page
from hunter_core.domain.enums import AnomalyStatus, AnomalyType
from hunter_core.domain.types import utcnow

router = APIRouter(prefix="/api/v1/anomalies", tags=["anomalies"])

DEFAULT_WINDOW_HOURS = 24
MAX_WINDOW_HOURS = 24 * 30


@router.get("", response_model=AnomalyPage, summary="List anomalies")
async def list_anomalies(
    request: Request,
    principal: CurrentPrincipal,
    window_hours: Annotated[int, Query(ge=1, le=MAX_WINDOW_HOURS)] = DEFAULT_WINDOW_HOURS,
    type_filter: Annotated[AnomalyType | None, Query(alias="type")] = None,
    status_filter: Annotated[AnomalyStatus | None, Query(alias="status")] = None,
    market_id: uuid.UUID | None = None,
    min_severity: Annotated[Decimal | None, Query(ge=0, le=MAX_SCORE)] = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    cursor: str | None = None,
) -> AnomalyPage:
    since = utcnow() - timedelta(hours=window_hours)
    async with analysis_scope(request, principal) as scope:
        rows, next_cursor = await AnomalyRepository(scope.session).list_page(
            since=since,
            anomaly_type=type_filter,
            anomaly_status=status_filter,
            market_id=market_id,
            min_severity=min_severity,
            limit=clamp_page_size(limit),
            cursor=cursor,
        )
    return build_anomaly_page(rows, next_cursor, window_start=since)
