"""``/api/v1/orgs/{org_id}/meme`` — Meme Radar (T4.3), monitoring only.

Nested under the organization per brief T4.3 ("VIEWER+ under the org
session") even though the underlying ``meme_*`` tables carry no
``organization_id`` — same global-data-under-a-tenant-route shape as
``routers/portfolio.py`` structurally, but ``repositories/meme.py`` never
filters by ``org_id`` (there is nothing to filter by): the org path segment
and ``require_org`` only gate *who* may see the radar, exactly like
``ARCHITECTURE.md`` §9's "Repositorios globais... so leitura para tenants",
applied here to an org-scoped path instead of a bare one.

No order, no wallet, no ``RiskDecision`` anywhere in this file
(``docs/plans/T4-MEME-RADAR.md`` §0) — every route is a ``GET``.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession
from hunter_api.errors import HunterError
from hunter_api.repositories.base import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    decode_cursor,
    encode_cursor,
)
from hunter_api.repositories.meme import MemeRepository
from hunter_api.repositories.meme_cursor import decode_token_cursor, encode_token_cursor
from hunter_api.schemas.meme import (
    MemeGapListOut,
    MemeOverviewOut,
    MemeTokenDetailOut,
    MemeTokenListOut,
    MemeTokenSort,
    MemeTokenState,
)
from hunter_api.services.meme import (
    build_gap_out,
    build_overview,
    build_token_detail,
    build_token_out,
)
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow
from hunter_exchanges.pumpfun.rest import PumpFunRestClient

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/orgs/{org_id}/meme", tags=["meme"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
_Limit = Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)]
DEFAULT_SNAPSHOT_LIMIT = 500
MAX_SNAPSHOT_LIMIT = 1500
DEFAULT_FEATURE_LIMIT = 1440
"""24h of 1-minute rows — the detail chart's default window."""
MAX_FEATURE_LIMIT = 4320


class MemeTokenNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="meme-token-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meme token not found.",
        )


@router.get(
    "/overview",
    response_model=MemeOverviewOut,
    summary="Meme Radar overview: creation and Mayhem activity",
)
async def get_overview(context: ViewerOrg, session: OrgSession) -> MemeOverviewOut:
    repo = MemeRepository(session)
    rest_client = PumpFunRestClient()
    try:
        return await build_overview(repo, rest_client)
    finally:
        await rest_client.aclose()


@router.get("/tokens", response_model=MemeTokenListOut, summary="List tracked meme tokens")
async def list_tokens(
    context: ViewerOrg,
    session: OrgSession,
    state: MemeTokenState | None = None,
    sort: MemeTokenSort = "mcap",
    limit: _Limit = None,
    cursor: str | None = None,
) -> MemeTokenListOut:
    page_size = limit or DEFAULT_PAGE_SIZE
    decoded_cursor = decode_token_cursor(cursor)
    repo = MemeRepository(session)
    rows = await repo.list_tokens(
        state=state, sort=sort, limit=page_size + 1, cursor=decoded_cursor
    )
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    now = utcnow()
    items = [build_token_out(row, now=now) for row in page_rows]
    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        sort_value: Decimal | None = (
            last.mcap_sol
            if sort == "mcap"
            else last.curve_progress_pct
            if sort == "progress"
            else None
        )
        cursor_value = last.created_at if sort == "age" else sort_value
        next_cursor = encode_token_cursor(sort, cursor_value, last.mint)
    return MemeTokenListOut(items=items, next_cursor=next_cursor)


@router.get(
    "/tokens/{mint}", response_model=MemeTokenDetailOut, summary="One meme token: curve + features"
)
async def get_token(
    mint: str,
    context: ViewerOrg,
    session: OrgSession,
    snapshot_limit: Annotated[int, Query(ge=1, le=MAX_SNAPSHOT_LIMIT)] = DEFAULT_SNAPSHOT_LIMIT,
    feature_limit: Annotated[int, Query(ge=1, le=MAX_FEATURE_LIMIT)] = DEFAULT_FEATURE_LIMIT,
) -> MemeTokenDetailOut:
    repo = MemeRepository(session)
    token = await repo.get_token(mint)
    if token is None:
        raise MemeTokenNotFoundError
    snapshots = await repo.list_snapshots(mint, limit=snapshot_limit)
    features = await repo.list_features(mint, limit=feature_limit)
    return build_token_detail(token, snapshots, features, now=utcnow())


@router.get("/gaps", response_model=MemeGapListOut, summary="List ingestion gaps")
async def list_gaps(
    context: ViewerOrg,
    session: OrgSession,
    limit: _Limit = None,
    cursor: str | None = None,
) -> MemeGapListOut:
    page_size = limit or DEFAULT_PAGE_SIZE
    decoded_cursor = decode_cursor(cursor)
    repo = MemeRepository(session)
    rows = await repo.list_gaps(limit=page_size + 1, cursor=decoded_cursor)
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    items = [build_gap_out(row) for row in page_rows]
    next_cursor: str | None = None
    if has_more and page_rows:
        last = page_rows[-1]
        next_cursor = encode_cursor(last.detected_at, uuid.UUID(str(last.id)))
    return MemeGapListOut(items=items, next_cursor=next_cursor)
