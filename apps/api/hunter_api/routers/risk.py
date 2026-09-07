"""``/api/v1/orgs/{org_id}/portfolios/{portfolio_id}/risk`` — the kill switch.

**Who may resume.** SECURITY.md §2 puts "Kill switch de portfolio" at TRADER and
above (the organization-wide switch is ADMIN, and it is not exposed here), so the
resume declares ``require_org(TRADER)`` and the read declares ``VIEWER``. The
joint M3 decision (``docs/plans/M3.md`` §5) is stricter than the RBAC matrix —
"ato autenticado **da identidade autorizada do Everton** — não qualquer rótulo
ADMIN" — and nothing in the codebase names that identity today. The gap is
recorded in ``.claude/state/notes-T3.6.md`` (finding 3) rather than closed here
by inventing an allowlist: this route enforces the documented floor, and the
schema records *which* person acted, on every resume.

**What the resume cannot do.** It never writes ``portfolio_risk_state``, so it
cannot move the peak or the day's opening; and it is refused outright while the
automatic assessment still blocks, which is the v2.1 rule the pure core added —
a transition the next evaluation would undo is worse in the log than no
transition at all.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession
from hunter_api.errors import HunterError
from hunter_api.schemas.risk import (
    DailyReferenceOut,
    KillSwitchOut,
    PeakOut,
    ResumeOut,
    ResumeRequest,
    ScopeStatesOut,
    TransitionOut,
)
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow
from hunter_core.risk import (
    ResumeRefused,
    RiskStateMissing,
    effective_state,
    latest_transition,
    load_locked_state,
    resume,
)
from hunter_risk import sao_paulo_day_start_utc

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}/portfolios/{portfolio_id}/risk", tags=["risk"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
TraderOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.TRADER))]


class PortfolioNotFoundError(HunterError):
    """404, and the same 404 for "another tenant's wallet" — SECURITY.md §3.3."""

    def __init__(self) -> None:
        super().__init__(
            type_slug="portfolio-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found.",
        )


class ResumeRefusedError(HunterError):
    """409: the wallet exists, the caller may act, and the switch still bites."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            type_slug="kill-switch-resume-refused",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=reason,
        )


async def _owned(session: AsyncSession, context: OrgContext, portfolio_id: uuid.UUID) -> None:
    """Refuse early, with a 404, for a wallet this organization does not own.

    RLS would already return no rows, but the explicit check is what turns that
    into the documented 404 instead of whatever the first query happens to raise.
    """
    found = await session.scalar(
        select(Portfolio.id).where(
            Portfolio.id == portfolio_id, Portfolio.organization_id == context.org_id
        )
    )
    if found is None:
        raise PortfolioNotFoundError


@router.get(
    "/kill-switch",
    response_model=KillSwitchOut,
    summary="Read the portfolio kill switch, with its motive and evidence",
)
async def read_kill_switch(
    context: ViewerOrg, session: OrgSession, portfolio_id: uuid.UUID
) -> KillSwitchOut:
    await _owned(session, context, portfolio_id)
    try:
        scopes = await effective_state(session, portfolio_id)
        row = await load_locked_state(session, portfolio_id)
    except RiskStateMissing as missing:
        raise PortfolioNotFoundError from missing
    reason = await session.scalar(
        select(Portfolio.kill_switch_reason).where(Portfolio.id == portfolio_id)
    )
    transition = await latest_transition(session, portfolio_id)
    # Available means "for **today**". A worker stopped across the turn leaves
    # yesterday's opening filled in; reporting that as available would publish a
    # daily loss measured against the wrong day (Astra, second round).
    reference_available = (
        row.equity_day_start is not None
        and row.trading_day_start_utc == sao_paulo_day_start_utc(utcnow())
    )
    return KillSwitchOut(
        portfolio_id=portfolio_id,
        effective=scopes.effective,
        # Entries are blocked by the switch **or** by a daily reference that could
        # not be rebuilt: without it the day's loss is not measurable, and §5 says
        # the wallet blocks entries and keeps its protections. Reporting only the
        # switch would announce "entries allowed" for a wallet the engine will not
        # let trade (Astra, review of this diff).
        blocks_entries=scopes.blocks_entries or not reference_available,
        scopes=ScopeStatesOut(
            system=scopes.system, organization=scopes.organization, portfolio=scopes.portfolio
        ),
        reason=reason,
        daily_reference=DailyReferenceOut(
            trading_day=row.trading_day,
            trading_day_timezone=row.trading_day_timezone,
            trading_day_start_utc=row.trading_day_start_utc,
            equity_day_start=row.equity_day_start,
            observed_at=row.day_reference_observed_at,
            available=reference_available,
        ),
        peak=PeakOut(
            equity=row.peak_equity,
            observed_at=row.peak_equity_at,
            sampling_interval_s=row.peak_sampling_interval_s,
        ),
        last_transition=None
        if transition is None
        else TransitionOut(
            from_state=transition.from_state,
            to_state=transition.to_state,
            reason=transition.reason,
            actor_type=transition.actor_type,
            actor_id=transition.actor_id,
            evidence=transition.evidence,
            created_at=transition.created_at,
        ),
    )


@router.post(
    "/kill-switch/resume",
    response_model=ResumeOut,
    summary="Resume trading on a latched kill switch (TRADER+)",
)
async def resume_kill_switch(
    context: TraderOrg, session: OrgSession, portfolio_id: uuid.UUID, body: ResumeRequest
) -> ResumeOut:
    await _owned(session, context, portfolio_id)
    try:
        outcome = await resume(
            session,
            portfolio_id,
            actor_id=context.principal.user_id,
            reason=body.reason,
            now=utcnow(),
        )
    except RiskStateMissing as missing:
        raise PortfolioNotFoundError from missing
    except ResumeRefused as refused:
        raise ResumeRefusedError(refused.reason) from refused
    return ResumeOut(
        portfolio_id=portfolio_id,
        from_state=outcome.from_state,
        to_state=outcome.to_state,
        actor_id=outcome.actor_id,
        daily_loss_pct=outcome.assessment.daily_loss_pct,
        drawdown_pct=outcome.assessment.drawdown_pct,
        effective=outcome.scopes.effective,
    )
