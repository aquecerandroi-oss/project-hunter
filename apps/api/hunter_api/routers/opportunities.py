"""``GET /api/v1/opportunities`` and ``/{id}`` — PIPELINE.md §5's explainability
contract. Global, no-RLS reads; ``org_id`` is optional exactly like
``routers/radar.py`` (see that module's docstring for why).

Both routes open their session through ``routers/radar_common.py::
analysis_scope`` (one pooled connection per request, never two).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.errors import HunterError
from hunter_api.repositories.base import MAX_PAGE_SIZE, clamp_page_size
from hunter_api.repositories.opportunities import DEFAULT_HISTORY_LIMIT, OpportunityRepository
from hunter_api.routers.radar_common import analysis_scope
from hunter_api.schemas.common import CursorPage
from hunter_api.schemas.opportunities import (
    MAX_ENVELOPE_HISTORY_LIMIT,
    MAX_HISTORY_LIMIT,
    OpportunityDetailOut,
    OpportunitySummaryOut,
)
from hunter_api.schemas.radar import MAX_SCORE
from hunter_api.services.opportunities import build_detail, build_list_page
from hunter_core.domain.enums import OpportunityStage, OpportunityStatus

router = APIRouter(prefix="/api/v1/opportunities", tags=["opportunities"])


class OpportunityNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="opportunity-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opportunity not found.",
        )


class EnvelopeHistoryLimitError(HunterError):
    """``include_envelope=true`` asked for more history than the envelope cap.

    MF-3 (security-reviewer, 2026-09-06): ``include_envelope=true`` with
    ``history_limit=500`` ships 500 full feature envelopes — the entire
    recomputation proof of every sample — in one response, from one cheap GET.
    A 422 naming the cap is honest; silently trimming to 50 would hand back a
    truncated trajectory the caller believes is complete.
    """

    def __init__(self, requested: int) -> None:
        super().__init__(
            type_slug="envelope-history-limit",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"history_limit must be at most {MAX_ENVELOPE_HISTORY_LIMIT} when "
                f"include_envelope=true (got {requested}); it may be up to "
                f"{MAX_HISTORY_LIMIT} without the envelope."
            ),
        )


def resolve_history_limit(requested: int | None, *, include_envelope: bool) -> int:
    """How many history points to read, given what the caller asked for.

    An **explicit** ``history_limit`` above the envelope cap is a 422: the
    caller named a number and must be told it will not be honoured. An
    **omitted** one is not — the default simply adapts
    (``DEFAULT_HISTORY_LIMIT`` without the envelope,
    ``MAX_ENVELOPE_HISTORY_LIMIT`` with it), because a plain
    ``?include_envelope=true`` must keep working rather than 422 on a value
    the caller never chose.
    """
    if not include_envelope:
        return requested if requested is not None else DEFAULT_HISTORY_LIMIT
    if requested is None:
        return MAX_ENVELOPE_HISTORY_LIMIT
    if requested > MAX_ENVELOPE_HISTORY_LIMIT:
        raise EnvelopeHistoryLimitError(requested)
    return requested


@router.get("", response_model=CursorPage[OpportunitySummaryOut], summary="List opportunities")
async def list_opportunities(
    request: Request,
    principal: CurrentPrincipal,
    org_id: uuid.UUID | None = None,
    score_min: Annotated[Decimal | None, Query(ge=0, le=MAX_SCORE)] = None,
    status_filter: Annotated[list[OpportunityStatus] | None, Query(alias="status")] = None,
    stage: Annotated[list[OpportunityStage] | None, Query()] = None,
    exchange: Annotated[str | None, Query(max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    cursor: str | None = None,
) -> CursorPage[OpportunitySummaryOut]:
    async with analysis_scope(request, principal, org_id) as scope:
        rows, next_cursor = await OpportunityRepository(scope.session).list_page(
            score_min=score_min,
            statuses=tuple(status_filter) if status_filter else (),
            stages=tuple(stage) if stage else (),
            exchange=exchange,
            symbol_query=q,
            limit=clamp_page_size(limit),
            cursor=cursor,
        )
    return build_list_page(rows, next_cursor, scope.org_derivation)


@router.get(
    "/{opportunity_id}", response_model=OpportunityDetailOut, summary="Read one opportunity"
)
async def get_opportunity(
    opportunity_id: uuid.UUID,
    request: Request,
    principal: CurrentPrincipal,
    org_id: uuid.UUID | None = None,
    include_envelope: Annotated[
        bool,
        Query(
            description=(
                "Include each history point's full feature envelope. Caps "
                f"history_limit at {MAX_ENVELOPE_HISTORY_LIMIT} (422 above that)."
            )
        ),
    ] = False,
    history_limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=MAX_HISTORY_LIMIT,
            description=(
                f"How many of the newest history points to return. Maximum "
                f"{MAX_HISTORY_LIMIT}, or {MAX_ENVELOPE_HISTORY_LIMIT} when "
                f"include_envelope=true (422 above that). Omitted: "
                f"{DEFAULT_HISTORY_LIMIT}, or {MAX_ENVELOPE_HISTORY_LIMIT} with "
                f"the envelope."
            ),
        ),
    ] = None,
) -> OpportunityDetailOut:
    history_limit = resolve_history_limit(history_limit, include_envelope=include_envelope)
    async with analysis_scope(request, principal, org_id) as scope:
        repo = OpportunityRepository(scope.session)
        row = await repo.get_detail(opportunity_id)
        if row is None:
            raise OpportunityNotFoundError
        anomalies = await repo.list_active_anomalies(row.market_id)
        history = await repo.list_history(opportunity_id, limit=history_limit)
    return build_detail(
        row, anomalies, history, scope.org_derivation, include_envelope=include_envelope
    )
