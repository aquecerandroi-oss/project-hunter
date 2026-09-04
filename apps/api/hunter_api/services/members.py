"""Membership changes, with the last-OWNER guard.

SECURITY.md §2 puts billing, ownership transfer and deleting the organization
behind OWNER. An organization with no active OWNER can therefore do none of
those, ever, and no route exists to appoint one — so both mutations here refuse
to remove the last one. This is a rule, not a warning: it is enforced in the
service, inside the transaction, not in the router where a second entry point
could miss it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from fastapi import status

from hunter_api.errors import HunterError
from hunter_api.repositories.organizations import MemberRepository
from hunter_core.audit import audited
from hunter_core.domain.enums import OrganizationRole

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class MemberNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="member-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That person is not a member of this organization.",
        )


class LastOwnerError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="last-owner",
            title="Conflict",
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This is the organization's last owner. Promote another member to OWNER first."
            ),
        )


async def _member_before(**kwargs: Any) -> dict[str, Any] | None:
    session: AsyncSession = kwargs["session"]
    org_id: uuid.UUID = kwargs["org_id"]
    user_id: uuid.UUID = kwargs["user_id"]
    member = await MemberRepository(session, org_id).get(user_id)
    if member is None:
        return None
    return {"user_id": str(user_id), "role": member.role.value, "status": member.status.value}


@audited("member.role_changed", "organization_member", before=_member_before)
async def change_member_role(
    *,
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    role: OrganizationRole,
    **_audit: Any,
) -> dict[str, Any]:
    repository = MemberRepository(session, org_id)
    member = await repository.get(user_id)
    if member is None:
        raise MemberNotFoundError
    if member.role is OrganizationRole.OWNER and role is not OrganizationRole.OWNER:
        await _guard_last_owner(repository)
    await repository.set_role(user_id, role)
    await session.flush()
    return {"user_id": str(user_id), "role": role.value}


@audited("member.removed", "organization_member", before=_member_before)
async def remove_member(
    *, session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, **_audit: Any
) -> dict[str, Any]:
    repository = MemberRepository(session, org_id)
    member = await repository.get(user_id)
    if member is None:
        raise MemberNotFoundError
    if member.role is OrganizationRole.OWNER:
        await _guard_last_owner(repository)
    await repository.remove(user_id)
    return {"user_id": str(user_id), "removed": True}


async def _guard_last_owner(repository: MemberRepository) -> None:
    if await repository.count_active_owners() <= 1:
        raise LastOwnerError
