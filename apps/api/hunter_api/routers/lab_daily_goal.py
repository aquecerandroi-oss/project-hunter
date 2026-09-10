"""``GET /api/v1/orgs/{org_id}/lab/daily-goal`` — brief T3.78.

Tenant route (ARCHITECTURE.md §9), unlike the rest of the Shadow Lab API
(``routers/lab*.py``, global/no-RLS): the question "how far is this
organization from R$9.000 today" mixes the shared research (Shadow Lab
tables, no ``organization_id``) with the organization's own real principal
paper wallet (``portfolios``, RLS-scoped). ``OrgSession`` sets
``app.current_org`` for the one tenant read
(``LabDailyGoalRepository.principal_portfolio_equity_usdt``); every other
read in this module is the same global research read every other Lab router
already does under an authenticated, organization-less session — reading it
here, under the tenant transaction, changes nothing about its visibility
(DATABASE.md §16: no RLS policy applies to those tables regardless of
``app.current_org``).

VIEWER floor, same as every other read under ``/orgs/{org_id}``
(SECURITY.md §2).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, get_settings
from hunter_api.repositories.lab_daily_goal import LabDailyGoalRepository
from hunter_api.schemas.lab_daily_goal import DailyGoalOut
from hunter_api.services.lab_daily_goal import build_daily_goal
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from hunter_api.settings import ApiSettings

router = APIRouter(prefix="/api/v1/orgs/{org_id}/lab", tags=["lab"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
Settings = Annotated["ApiSettings", Depends(get_settings)]


@router.get(
    "/daily-goal",
    response_model=DailyGoalOut,
    summary="How far the Lab is from the day's R$ profit goal, and why",
)
async def get_daily_goal(
    context: ViewerOrg,
    session: OrgSession,
    settings: Settings,
    day: date | None = None,
) -> DailyGoalOut:
    repo = LabDailyGoalRepository(session, context.org_id)
    return await build_daily_goal(repo, day=day, as_of=utcnow(), goal_brl=settings.daily_goal_brl)
