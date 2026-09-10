"""``/api/v1/orgs/{org_id}/portfolios/{portfolio_id}/order-requests`` — T3.68.

The write half T3.8's definition of done calls **ordem manual paper**:
``docs/plans/M3.md`` names it the only thing that exercises the M3 wallet
besides tests, and until this router existed nothing in ``apps/api`` called
``hunter_api.services.admission.file_manual_order`` (T3.12) — the service
existed, tested, unreachable.

**Path, not ``.../orders``: see ``hunter_api.schemas.orders``'s module
docstring** for why (``routers/portfolio.py`` already serves a different
resource at that exact path). Role floor is TRADER for the write (SECURITY.md
§2, "ordem manual paper (TRADER+)") and VIEWER for both reads, matching every
other wallet read in ``routers/portfolio.py``/``routers/risk.py``.

Every write here goes through ``file_manual_order`` alone, inside the org
session (RLS) that already carries the audit sink — no SQL write happens in
this file or in ``services/orders.py``. ``ENABLE_PAPER_AUTONOMY`` is
irrelevant to this router: that flag gates the M4 signal-to-proposal bridge,
never the operator's own route (RISK_ENGINE.md §8).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Header, Query, status

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, get_redis
from hunter_api.errors import HunterError
from hunter_api.repositories.base import MAX_PAGE_SIZE
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.orders import (
    MAX_IDEMPOTENCY_KEY_LENGTH,
    MIN_IDEMPOTENCY_KEY_LENGTH,
    ManualOrderCreate,
    ManualOrderDetailOut,
    ManualOrderOut,
)
from hunter_api.services.orders import file_order, get_manual_order_detail, list_manual_orders
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/portfolios/{portfolio_id}/order-requests", tags=["orders"]
)

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
TraderOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.TRADER))]
Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]
_IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9_.:-]+$"
"""T3.68b finding 7: a restricted charset, no whitespace. Without it a caller
could send a key padded with leading/trailing spaces that ``admission_key``
(``hunter_core.admission.sources``) then ``.strip()``s before minting the
idempotency key — two HTTP requests whose headers disagree byte-for-byte would
mint the *same* key, which is a correct de-dupe for a genuine retry but an
easy way to make two callers' intent silently merge if the header ever leaks
between them (a proxy log, a copy-pasted curl). Restricting the charset to
the same conservative one most idempotency-key conventions use makes the
``.strip()`` a no-op for anything that validates at all."""

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=MIN_IDEMPOTENCY_KEY_LENGTH,
        max_length=MAX_IDEMPOTENCY_KEY_LENGTH,
        pattern=_IDEMPOTENCY_KEY_PATTERN,
    ),
]
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


class OrderRequestNotFoundError(HunterError):
    """404: no manual request with this id on this wallet."""

    def __init__(self) -> None:
        super().__init__(
            type_slug="order-request-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order request not found.",
        )


async def _owned(session: AsyncSession, context: OrgContext, portfolio_id: uuid.UUID) -> None:
    """Refuse early, with a 404, for a wallet this organization does not own —
    ``routers/portfolio.py``'s own ``_owned``, restated here (the two files do
    not share a private helper, matching the existing convention between
    ``portfolio.py`` and ``risk.py``)."""
    found = await session.scalar(
        Portfolio.__table__.select()
        .with_only_columns(Portfolio.id)
        .where(Portfolio.id == portfolio_id, Portfolio.organization_id == context.org_id)
    )
    if found is None:
        raise PortfolioNotFoundError


@router.post(
    "",
    response_model=ManualOrderOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="File a manual paper order (TRADER+)",
)
async def file_manual_order_route(
    context: TraderOrg,
    session: OrgSession,
    redis: Redis,
    portfolio_id: uuid.UUID,
    body: ManualOrderCreate,
    idempotency_key: IdempotencyKey,
) -> ManualOrderOut:
    """202 always — including a replay of the same key, decided or not
    (documented deviation from "200 or 202": one status keeps the response
    shape the only thing a caller has to branch on). A *different* order under
    the same key is a 409 (``OrderReplayConflictError``); the wallet never
    opened is a 409 (``WalletNotOpenError``); anything about the market or the
    direction that keeps this from ever becoming a proposal is a 422
    (``OrderRefusedError``, reason named in ``detail``). None of these reach
    this function as anything but the ``HunterError`` the global handler
    already renders as problem+json.
    """
    await _owned(session, context, portfolio_id)
    return await file_order(
        session,
        redis,
        context=context,
        portfolio_id=portfolio_id,
        idempotency_key=idempotency_key,
        body=body,
        now=utcnow(),
    )


@router.get(
    "/{request_id}",
    response_model=ManualOrderDetailOut,
    summary="Read one manual order request, with its outcome if it has one",
)
async def get_manual_order_route(
    context: ViewerOrg, session: OrgSession, portfolio_id: uuid.UUID, request_id: uuid.UUID
) -> ManualOrderDetailOut:
    await _owned(session, context, portfolio_id)
    detail = await get_manual_order_detail(
        session, org_id=context.org_id, portfolio_id=portfolio_id, request_id=request_id
    )
    if detail is None:
        raise OrderRequestNotFoundError
    return detail


@router.get(
    "",
    response_model=CursorPage[ManualOrderOut],
    summary="List this wallet's manual order requests, newest first",
)
async def list_manual_orders_route(
    context: ViewerOrg,
    session: OrgSession,
    portfolio_id: uuid.UUID,
    limit: _Limit = None,
    cursor: str | None = None,
) -> CursorPage[ManualOrderOut]:
    await _owned(session, context, portfolio_id)
    items, next_cursor = await list_manual_orders(
        session, org_id=context.org_id, portfolio_id=portfolio_id, limit=limit, cursor=cursor
    )
    return CursorPage(items=items, next_cursor=next_cursor)
