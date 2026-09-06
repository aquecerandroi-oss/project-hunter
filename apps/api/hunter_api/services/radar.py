"""Assembling ``GET /api/v1/radar`` — merges :class:`RadarRow` (Postgres) with
the optional per-organization derivation (``services/radar_org_derivation.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status

from hunter_api.errors import HunterError
from hunter_api.repositories.base import clamp_page_size
from hunter_api.repositories.radar import RadarFilters, RadarRepository, RadarRow
from hunter_api.schemas.radar import DERIVED_STATUS_VALUES, RadarItemOut, RadarPage
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.schemas.radar import RadarStatusFilter
    from hunter_api.services.radar_org_derivation import OrgDerivation

__all__ = ["StatusRequiresOrgError", "build_radar_page", "resolve_status_tokens"]


class StatusRequiresOrgError(HunterError):
    """``?status=IN_POSITION``/``RISK_BLOCKED`` without ``org_id``.

    422, not a silent no-op: the caller asked for a status this API cannot
    derive without an organization, and returning an empty/unfiltered page
    instead would look like "nobody is in position" rather than "you did not
    say whose position to check".
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="radar-status-requires-org",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Filtering by IN_POSITION or RISK_BLOCKED requires org_id.",
        )


def resolve_status_tokens(
    statuses: list[RadarStatusFilter] | None, *, has_org: bool
) -> tuple[str, ...]:
    if not statuses:
        return ()
    tokens = tuple(status_filter.value for status_filter in statuses)
    if not has_org and any(token in DERIVED_STATUS_VALUES for token in tokens):
        raise StatusRequiresOrgError
    return tokens


def _to_item(row: RadarRow, org_derivation: OrgDerivation | None) -> RadarItemOut:
    in_position = None
    risk_blocked = None
    risk_blocked_reason = None
    if org_derivation is not None:
        in_position = row.market_id in org_derivation.in_position_market_ids
        risk_blocked = org_derivation.risk_blocked
        risk_blocked_reason = org_derivation.risk_blocked_reason
    return RadarItemOut(
        opportunity_id=row.opportunity_id,
        market_id=row.market_id,
        exchange=row.exchange,
        symbol=row.symbol,
        market_type=row.market_type,
        direction=row.direction,
        score=row.score,
        confidence=row.confidence,
        peak_score=row.peak_score,
        status=row.status,
        stage=row.stage,
        regime=row.regime,
        change=row.change,
        first_seen_at=row.first_seen_at,
        last_updated_at=row.last_updated_at,
        below_40_since=row.below_40_since,
        in_position=in_position,
        risk_blocked=risk_blocked,
        risk_blocked_reason=risk_blocked_reason,
    )


async def build_radar_page(
    session: AsyncSession,
    filters: RadarFilters,
    *,
    limit: int | None,
    cursor: str | None,
    org_derivation: OrgDerivation | None,
) -> RadarPage:
    size = clamp_page_size(limit)
    rows, next_cursor = await RadarRepository(session).list_page(
        filters,
        limit=size,
        cursor=cursor,
        in_position_market_ids=(
            org_derivation.in_position_market_ids if org_derivation else frozenset()
        ),
        risk_blocked=org_derivation.risk_blocked if org_derivation else False,
    )
    items = [_to_item(row, org_derivation) for row in rows]
    return RadarPage(
        items=items,
        next_cursor=next_cursor,
        as_of=utcnow(),
        org_scoped=org_derivation is not None,
    )
