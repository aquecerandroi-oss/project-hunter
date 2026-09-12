"""``/api/v1/orgs/{org_id}/meme/{desk,proposals,bets}`` — the operator desk
(T4.7). Contract ``.claude/state/contrato-T4.6-T4.7-mesa-meme.md`` §Rotas.

VIEWER+ reads the desk; TRADER+ — the role that already files
``order-requests`` (``routers/orders.py``) — decides and commands. Every POST
requires ``Idempotency-Key`` (the exact header validation ``orders.py``
declares, imported rather than restated) and writes ``audit_logs``.

Paper only: nothing here signs, submits or reads a key. The loop (T4.6)
fills and sells on the next snapshot; a ``sell_now`` is therefore a 202 —
accepted, applied later, never "sold at this price".
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, status

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, get_redis, get_settings
from hunter_api.repositories.base import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from hunter_api.repositories.meme_desk import MemeDeskRepository
from hunter_api.repositories.meme_desk_rows import decode_desk_cursor, encode_desk_cursor
from hunter_api.repositories.meme_wallets import MemeWalletsRepository
from hunter_api.routers.orders import IdempotencyKey
from hunter_api.schemas.meme_desk import (
    ApproveProposalIn,
    CommandOut,
    DeskListOut,
    ManualProposalIn,
    ProposalOut,
    ProposalStatus,
    RejectProposalIn,
)
from hunter_api.services.meme_desk import (
    approve_proposal,
    cancel_proposal,
    file_manual_proposal,
    reject_proposal,
    sell_now,
)
from hunter_api.services.meme_desk_idempotency import RedisIdempotencyStore
from hunter_api.services.meme_desk_out import build_desk_row_out, build_summary
from hunter_api.services.meme_lab import day_bounds_brt
from hunter_api.services.meme_wallets import SolUsdQuote, build_real_observed
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_api.settings import ApiSettings

__all__ = ["router"]

router = APIRouter(prefix="/api/v1/orgs/{org_id}/meme", tags=["meme"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
OperatorOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.TRADER))]
Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]
Settings = Annotated["ApiSettings", Depends(get_settings)]
"""T4.14: only ``enable_meme_live_trading`` is read here — whether ``mode = "live"``
may be filed. The API never signs."""
_Limit = Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)]


@router.get(
    "/desk",
    response_model=DeskListOut,
    summary="The operator desk: proposals, open bets, history — paper only",
)
async def get_desk(
    context: ViewerOrg,
    session: OrgSession,
    status_filter: Annotated[ProposalStatus | None, Query(alias="status")] = None,
    limit: _Limit = None,
    cursor: str | None = None,
) -> DeskListOut:
    page_size = limit or DEFAULT_PAGE_SIZE
    repo = MemeDeskRepository(session)
    now = utcnow()
    rows = await repo.list_desk(
        status=status_filter, limit=page_size + 1, cursor=decode_desk_cursor(cursor)
    )
    has_more = len(rows) > page_size
    page = rows[:page_size]
    next_cursor: str | None = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_desk_cursor(last.rank, last.proposal.proposed_at, last.proposal.id)
    summary = build_summary(await repo.rule_set_balances(now), await repo.latest_sol_usd_quote())
    # T4.12: the observed wallets' real fills, priced with the desk's own quote.
    _, day_start, day_end = day_bounds_brt(now)
    quote = summary.sol_usd
    real_observed = await build_real_observed(
        MemeWalletsRepository(session),
        day_start=day_start,
        day_end=day_end,
        quote=None
        if quote is None
        else SolUsdQuote(quote.rate, quote.source or "unknown", quote.observed_at),
        watched=None,
        watched_reason="heartbeat_not_read",
    )
    return DeskListOut(
        server_now=now,
        summary=summary,
        items=[build_desk_row_out(row) for row in page],
        next_cursor=next_cursor,
        real_observed=real_observed,
    )


@router.post(
    "/proposals/{proposal_id}/approve",
    response_model=ProposalOut,
    summary="Approve a proposal with the operator's four parameters (TRADER+)",
)
async def approve_proposal_route(
    context: OperatorOrg,
    session: OrgSession,
    redis: Redis,
    proposal_id: uuid.UUID,
    body: ApproveProposalIn,
    idempotency_key: IdempotencyKey,
    settings: Settings,
) -> ProposalOut:
    """200 with the proposal; 409 unless ``proposed`` (or past ``expires_at``);
    422 ``exceeds_max_sol_per_bet`` / ``meme_live_disabled`` (``mode = "live"``
    without ``ENABLE_MEME_LIVE_TRADING`` on the API, T4.14); 409
    ``idempotency-key-conflict`` for a reused key naming a different intent."""
    return await approve_proposal(
        MemeDeskRepository(session),
        RedisIdempotencyStore(redis),
        context=context,
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        body=body,
        now=utcnow(),
        live_enabled=settings.enable_meme_live_trading,
    )


@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=ProposalOut,
    summary="Reject a proposal (TRADER+)",
)
async def reject_proposal_route(
    context: OperatorOrg,
    session: OrgSession,
    redis: Redis,
    proposal_id: uuid.UUID,
    body: RejectProposalIn,
    idempotency_key: IdempotencyKey,
) -> ProposalOut:
    return await reject_proposal(
        MemeDeskRepository(session),
        RedisIdempotencyStore(redis),
        context=context,
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        body=body,
        now=utcnow(),
    )


@router.post(
    "/proposals/manual",
    response_model=ProposalOut,
    status_code=status.HTTP_201_CREATED,
    summary="File a manual buy: a proposal born approved under operator/2 (TRADER+)",
)
async def manual_proposal_route(
    context: OperatorOrg,
    session: OrgSession,
    redis: Redis,
    body: ManualProposalIn,
    idempotency_key: IdempotencyKey,
    settings: Settings,
) -> ProposalOut:
    """201 (also on a replay of the same key); 422 ``mint_unknown`` /
    ``curve_completed`` / ``operator_rule_set_missing`` / ``exceeds_max_sol_per_bet``
    / ``meme_live_disabled`` (T4.14)."""
    return await file_manual_proposal(
        MemeDeskRepository(session),
        RedisIdempotencyStore(redis),
        context=context,
        idempotency_key=idempotency_key,
        body=body,
        now=utcnow(),
        live_enabled=settings.enable_meme_live_trading,
    )


@router.post(
    "/bets/{bet_id}/sell-now",
    response_model=CommandOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask the loop to sell an open paper bet on the next snapshot (TRADER+)",
)
async def sell_now_route(
    context: OperatorOrg,
    session: OrgSession,
    redis: Redis,
    bet_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
) -> CommandOut:
    """202: the command is filed, the sale happens on the next snapshot, not at
    this price. 409 ``bet_not_open`` / ``sell_now_already_pending``."""
    return await sell_now(
        MemeDeskRepository(session),
        RedisIdempotencyStore(redis),
        context=context,
        bet_id=bet_id,
        idempotency_key=idempotency_key,
        now=utcnow(),
    )


@router.post(
    "/proposals/{proposal_id}/cancel",
    response_model=CommandOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Cancel a proposal that has not been filled yet (TRADER+)",
)
async def cancel_proposal_route(
    context: OperatorOrg,
    session: OrgSession,
    redis: Redis,
    proposal_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
) -> CommandOut:
    """202; 409 ``already_filled`` once a bet exists, ``not_cancellable`` for a
    proposal already rejected/expired/unfilled."""
    return await cancel_proposal(
        MemeDeskRepository(session),
        RedisIdempotencyStore(redis),
        context=context,
        proposal_id=proposal_id,
        idempotency_key=idempotency_key,
        now=utcnow(),
    )
