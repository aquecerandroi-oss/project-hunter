"""``GET /api/v1/me`` — the caller and the organizations they belong to.

One request the app shell makes on every load, so it answers three questions
at once: who am I, which organizations can I switch between, and has each one
finished onboarding (PRODUCT.md §3) — which is what decides whether the shell
routes to the dashboard or back into the wizard.

**Why one transaction per organization.** Under RLS, ``organizations`` is
filtered by ``id = app.current_org`` and ``workspaces`` by
``organization_id = app.current_org``, and a transaction has exactly one
current organization. Reading N organizations therefore takes N tenant
transactions. The alternative — one query under the ``BYPASSRLS`` role — would
trade a real isolation guarantee for a round trip on a page that is already
fast at the sizes M0 has (people belong to one or two organizations). The loop
is bounded by ``MAX_ORGANIZATIONS`` so it cannot grow into a problem unnoticed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from sqlalchemy import select

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.deps import PrincipalSession, get_session_factory
from hunter_api.repositories.workspaces import WorkspaceRepository
from hunter_api.schemas.organizations import (
    MembershipOut,
    MeOut,
    OnboardingState,
    OrganizationOut,
    UserOut,
)
from hunter_api.services.workspaces import completed_at
from hunter_core.db.models.identity import Organization, User
from hunter_core.db.session import tenant_session

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.principal import Membership, Principal

router = APIRouter(prefix="/api/v1", tags=["auth"])

MAX_ORGANIZATIONS = 25


@router.get("/me", response_model=MeOut, summary="The signed-in user and their organizations")
async def read_me(
    request: Request, principal: CurrentPrincipal, session: PrincipalSession
) -> MeOut:
    user = await _read_user(session, principal)
    factory = get_session_factory(request)
    memberships: list[MembershipOut] = []
    for membership in principal.active_memberships()[:MAX_ORGANIZATIONS]:
        entry = await _read_membership(factory, principal, membership)
        if entry is not None:
            memberships.append(entry)
    return MeOut(user=user, memberships=memberships)


async def _read_user(session: AsyncSession, principal: Principal) -> UserOut:
    """The caller's own ``users`` row, reachable through ``user_reads_own_row``."""
    row = (
        await session.execute(
            select(User.email, User.display_name, User.avatar_url).where(
                User.id == principal.user_id
            )
        )
    ).first()
    if row is None:
        # the row was resolved moments ago in this same request; if it is gone
        # now, report what the principal carries rather than 500
        return UserOut(id=principal.user_id, email=principal.email or "")
    return UserOut(
        id=principal.user_id,
        email=row.email,
        display_name=row.display_name,
        avatar_url=row.avatar_url,
    )


async def _read_membership(
    factory: async_sessionmaker[AsyncSession],
    principal: Principal,
    membership: Membership,
) -> MembershipOut | None:
    async with tenant_session(factory, membership.org_id, principal.user_id) as session:
        organization = (
            await session.execute(
                select(
                    Organization.id,
                    Organization.slug,
                    Organization.name,
                    Organization.plan,
                    Organization.kill_switch_state,
                    Organization.created_at,
                ).where(Organization.id == membership.org_id, Organization.deleted_at.is_(None))
            )
        ).first()
        if organization is None:
            return None
        workspace = await WorkspaceRepository(session, membership.org_id).first()
        finished_at = completed_at(workspace.settings) if workspace else None
        workspace_id = workspace.id if workspace else None
    return MembershipOut(
        organization=OrganizationOut(
            id=organization.id,
            slug=organization.slug,
            name=organization.name,
            plan=organization.plan,
            kill_switch_state=organization.kill_switch_state,
            created_at=organization.created_at,
        ),
        role=membership.role,
        status=membership.status,
        onboarding=OnboardingState(
            completed=finished_at is not None,
            completed_at=finished_at,
            workspace_id=workspace_id,
        ),
    )
