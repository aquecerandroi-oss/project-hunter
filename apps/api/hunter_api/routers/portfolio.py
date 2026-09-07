"""``/api/v1/orgs/{org_id}/portfolios`` — the read half of T3.8 (T3.8a).

Tenant-scoped, per ARCHITECTURE.md §9 ("Rotas com tenant:
``/api/v1/orgs/{org_id}/...``"): every route here is nested under the
organization, exactly like ``routers/risk.py`` and ``routers/workspaces.py``.

**RBAC.** SECURITY.md §2 puts every read ("Ver dashboards, radar, mercados,
oportunidades, trades, analytics") at VIEWER and above; the wallet's summary,
curve, anchor and lists are reads of the same kind, so VIEWER is the floor for
all of them here. Writing (a manual paper order, TRADER+) is T3.8b's admission
path and is not in this file.

**Isolation.** A wallet that belongs to another organization is a 404, never a
403 (SECURITY.md §3.3) — the service layer returns ``None``/an empty page for
"not this organization's" and "does not exist" alike, and the router turns
``None`` into the one ``PortfolioNotFoundError`` every route shares.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, status

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession
from hunter_api.errors import HunterError
from hunter_api.repositories.base import MAX_PAGE_SIZE
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.portfolio import AnchorOut, PortfolioListItemOut, PortfolioSummaryOut
from hunter_api.schemas.portfolio_lists import (
    AsOfPage,
    EquityCurvePointOut,
    OrderOut,
    PortfolioTradeOut,
    PositionOut,
)
from hunter_api.services.portfolio_lists import (
    DEFAULT_CURVE_RESOLUTION,
    list_equity_curve,
    list_orders,
    list_positions,
    list_trades,
)
from hunter_api.services.portfolio_queries import build_summary, get_anchor, list_portfolios
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.domain.enums import OrganizationRole, Timeframe
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}/portfolios", tags=["portfolios"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
_Limit = Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)]


class PortfolioNotFoundError(HunterError):
    """404, and the same 404 for "another tenant's wallet" — SECURITY.md §3.3."""

    def __init__(self) -> None:
        super().__init__(
            type_slug="portfolio-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )


class NaiveTimestampError(HunterError):
    """422: a query timestamp with no timezone is not a UTC instant to compare.

    Astra, review of this diff, MUST-FIX 2: an unannotated ``datetime`` query
    parameter accepts a naive value, which would otherwise reach the
    ``timestamptz`` comparison in ``services/portfolio_lists.py`` unconverted
    — asyncpg's own rejection of that is a 500, not a 422 naming the field.
    """

    def __init__(self, field: str) -> None:
        super().__init__(
            type_slug="naive-timestamp",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field!r} must carry a timezone (e.g. '2026-09-06T00:00:00Z').",
        )


def _require_utc(value: datetime | None, *, field: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise NaiveTimestampError(field)
    return value.astimezone(UTC)


async def _owned(session: AsyncSession, context: OrgContext, portfolio_id: uuid.UUID) -> None:
    """Refuse early, with a 404, for a wallet this organization does not own.

    The sub-resource lists below filter by ``organization_id`` *and*
    ``portfolio_id`` together, so a foreign ``portfolio_id`` alone would
    silently read back an honestly-empty page instead of a 404 — this is what
    turns that into the documented 404 (``routers/risk.py``'s own ``_owned``).
    """
    found = await session.scalar(
        Portfolio.__table__.select()
        .with_only_columns(Portfolio.id)
        .where(Portfolio.id == portfolio_id, Portfolio.organization_id == context.org_id)
    )
    if found is None:
        raise PortfolioNotFoundError


@router.get("", response_model=CursorPage[PortfolioListItemOut], summary="List portfolios")
async def list_portfolios_route(
    context: ViewerOrg,
    session: OrgSession,
    limit: _Limit = None,
    cursor: str | None = None,
) -> CursorPage[PortfolioListItemOut]:
    items, next_cursor = await list_portfolios(session, context.org_id, limit=limit, cursor=cursor)
    return CursorPage(items=items, next_cursor=next_cursor)


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioSummaryOut,
    summary="Read one wallet: equity, BRL decomposition and risk state",
)
async def get_portfolio(
    context: ViewerOrg, session: OrgSession, portfolio_id: uuid.UUID
) -> PortfolioSummaryOut:
    summary = await build_summary(session, context.org_id, portfolio_id, utcnow())
    if summary is None:
        raise PortfolioNotFoundError
    return summary


@router.get(
    "/{portfolio_id}/anchor",
    response_model=AnchorOut,
    summary="Read the wallet's opening conversion",
)
async def get_portfolio_anchor(
    context: ViewerOrg, session: OrgSession, portfolio_id: uuid.UUID
) -> AnchorOut:
    anchor = await get_anchor(session, context.org_id, portfolio_id)
    if anchor is None:
        raise PortfolioNotFoundError
    return anchor


@router.get(
    "/{portfolio_id}/equity-curve",
    response_model=AsOfPage[EquityCurvePointOut],
    summary="Read the equity curve, in USDT and BRL",
)
async def get_equity_curve(
    context: ViewerOrg,
    session: OrgSession,
    portfolio_id: uuid.UUID,
    resolution: Timeframe = DEFAULT_CURVE_RESOLUTION,
    since: Annotated[datetime | None, Query(alias="from")] = None,
    until: Annotated[datetime | None, Query(alias="to")] = None,
    limit: _Limit = None,
    cursor: str | None = None,
) -> AsOfPage[EquityCurvePointOut]:
    await _owned(session, context, portfolio_id)
    as_of = utcnow()
    items, next_cursor = await list_equity_curve(
        session,
        context.org_id,
        portfolio_id,
        resolution=resolution,
        since=_require_utc(since, field="from"),
        until=_require_utc(until, field="to"),
        limit=limit,
        cursor=cursor,
    )
    return AsOfPage(as_of=as_of, items=items, next_cursor=next_cursor)


@router.get(
    "/{portfolio_id}/positions",
    response_model=AsOfPage[PositionOut],
    summary="List positions — empty until T3.4/T3.5 land a writer",
)
async def get_positions(
    context: ViewerOrg,
    session: OrgSession,
    portfolio_id: uuid.UUID,
    limit: _Limit = None,
    cursor: str | None = None,
) -> AsOfPage[PositionOut]:
    await _owned(session, context, portfolio_id)
    as_of = utcnow()
    items, next_cursor = await list_positions(
        session, context.org_id, portfolio_id, limit=limit, cursor=cursor
    )
    return AsOfPage(as_of=as_of, items=items, next_cursor=next_cursor)


@router.get(
    "/{portfolio_id}/orders",
    response_model=AsOfPage[OrderOut],
    summary="List orders — empty until T3.4/T3.5 land a writer",
)
async def get_orders(
    context: ViewerOrg,
    session: OrgSession,
    portfolio_id: uuid.UUID,
    limit: _Limit = None,
    cursor: str | None = None,
) -> AsOfPage[OrderOut]:
    await _owned(session, context, portfolio_id)
    as_of = utcnow()
    items, next_cursor = await list_orders(
        session, context.org_id, portfolio_id, limit=limit, cursor=cursor
    )
    return AsOfPage(as_of=as_of, items=items, next_cursor=next_cursor)


@router.get(
    "/{portfolio_id}/trades",
    response_model=AsOfPage[PortfolioTradeOut],
    summary="List trades — empty until T3.4/T3.5 land a writer",
)
async def get_trades(
    context: ViewerOrg,
    session: OrgSession,
    portfolio_id: uuid.UUID,
    limit: _Limit = None,
    cursor: str | None = None,
) -> AsOfPage[PortfolioTradeOut]:
    await _owned(session, context, portfolio_id)
    as_of = utcnow()
    items, next_cursor = await list_trades(
        session, context.org_id, portfolio_id, limit=limit, cursor=cursor
    )
    return AsOfPage(as_of=as_of, items=items, next_cursor=next_cursor)
