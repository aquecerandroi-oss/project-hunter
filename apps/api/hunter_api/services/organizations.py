"""Creating and updating organizations.

Sign-up is the one flow that writes rows the RLS settings are pointing at
before they exist, so it runs in a ``bootstrap_session`` with the organization
id generated up front (DATABASE.md §15.4). Everything it creates — the
organization, the OWNER membership, the org's copy of a risk preset, the first
workspace and the FREE subscription — lands in **one transaction**: a
half-created tenant (an organization with no owner, say) is not a state any
later code knows how to repair.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from hunter_api.errors import HunterError
from hunter_api.repositories.organizations import OrganizationRepository
from hunter_api.repositories.workspaces import RiskProfileRepository, WorkspaceRepository
from hunter_api.services.audit import record as record_audit
from hunter_api.services.slugs import derive_slug, suffixed_slug
from hunter_core.audit import audited
from hunter_core.db.models.billing import Subscription
from hunter_core.db.models.identity import Organization, OrganizationMember
from hunter_core.db.session import bootstrap_session
from hunter_core.domain.enums import (
    KillSwitchState,
    MemberStatus,
    OrganizationRole,
    Plan,
    RiskPreset,
    SubscriptionStatus,
)
from hunter_core.domain.types import utcnow, uuid7

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.principal import Principal
    from hunter_api.schemas.organizations import OrganizationCreate

SLUG_ATTEMPTS = 5
DEFAULT_PRESET = RiskPreset.BALANCED


class SlugUnavailableError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="slug-unavailable",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not derive a free URL for that name. Try a different one.",
        )


async def create_organization(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    payload: OrganizationCreate,
    principal: Principal,
    audit: dict[str, Any],
) -> dict[str, Any]:
    """Create an organization and everything a tenant needs to exist.

    Audited explicitly rather than through ``@audited``: the decorator reads
    its sink from the request-scoped contextvar bound by ``deps.org_session``,
    and there is no organization to open a tenant session for yet. The row is
    written on the same session, inside the same transaction, either way.
    """
    org_id = uuid7()
    async with bootstrap_session(session_factory, org_id=org_id, user_id=principal.user_id) as s:
        organization = await _insert_organization(s, org_id, payload.name, principal.user_id)
        await _add_owner(s, org_id, principal.user_id)
        profile = await RiskProfileRepository(s, org_id).copy_preset_for_org(
            DEFAULT_PRESET, principal.user_id
        )
        workspace = await WorkspaceRepository(s, org_id).create(
            name=payload.workspace_name or payload.name,
            objective=payload.objective,
            default_risk_profile_id=profile.id,
        )
        s.add(
            Subscription(
                id=uuid7(),
                organization_id=org_id,
                plan=Plan.FREE,
                status=SubscriptionStatus.ACTIVE,
            )
        )
        await s.flush()
        created = {**organization, "workspace_id": workspace.id, "risk_profile_id": profile.id}
        await record_audit(
            s,
            "organization.created",
            "organization",
            {**audit, "organization_id": org_id, "entity_id": org_id},
            after=created,
        )
    return created


async def _insert_organization(
    session: AsyncSession, org_id: uuid.UUID, name: str, created_by: uuid.UUID
) -> dict[str, Any]:
    """Insert with a derived slug, retrying on collision.

    The uniqueness check has to be the insert itself: ``organizations`` is
    filtered by ``id = app.current_org``, so a ``SELECT ... WHERE slug = :slug``
    from this transaction sees nothing and would happily report every slug as
    free. ``ON CONFLICT DO NOTHING ... RETURNING`` asks the unique index
    instead, and returns no row when the name is taken — without aborting the
    transaction the way a raised ``IntegrityError`` would.
    """
    base = derive_slug(name)
    for attempt in range(SLUG_ATTEMPTS):
        slug = base if attempt == 0 else suffixed_slug(base)
        row = (
            await session.execute(
                insert(Organization)
                .values(
                    id=org_id,
                    slug=slug,
                    name=name,
                    plan=Plan.FREE,
                    kill_switch_state=KillSwitchState.ACTIVE,
                    created_by=created_by,
                )
                .on_conflict_do_nothing(index_elements=["slug"])
                .returning(Organization.created_at)
            )
        ).first()
        if row is not None:
            return {
                "id": org_id,
                "slug": slug,
                "name": name,
                "plan": Plan.FREE,
                "kill_switch_state": KillSwitchState.ACTIVE,
                "created_at": row.created_at,
            }
    raise SlugUnavailableError


async def _add_owner(session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    session.add(
        OrganizationMember(
            organization_id=org_id,
            user_id=user_id,
            role=OrganizationRole.OWNER,
            status=MemberStatus.ACTIVE,
            joined_at=utcnow(),
        )
    )
    await session.flush()


async def _organization_before(**kwargs: Any) -> dict[str, Any] | None:
    session: AsyncSession = kwargs["session"]
    org_id: uuid.UUID = kwargs["org_id"]
    row = (
        await session.execute(select(Organization.name).where(Organization.id == org_id))
    ).first()
    return {"name": row.name} if row is not None else None


@audited("organization.updated", "organization", before=_organization_before)
async def rename_organization(
    *, session: AsyncSession, org_id: uuid.UUID, name: str, **_audit: Any
) -> dict[str, Any]:
    """Rename. The slug is not re-derived: it is a public identifier that other
    people have already bookmarked, and silently moving it would break links
    the API has no way to redirect.
    """
    await OrganizationRepository(session, org_id).rename(name)
    return {"name": name}
