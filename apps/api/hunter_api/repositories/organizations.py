"""Organization and membership repositories."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Row, Select, func, select, tuple_, update

from hunter_api.repositories.base import TenantRepository, clamp_page_size, decode_cursor
from hunter_core.db.models.identity import Organization, OrganizationMember, User
from hunter_core.domain.enums import MemberStatus, OrganizationRole

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime


class OrganizationRepository(TenantRepository):
    """The organization this request acts for. There is exactly one row it can
    reach: RLS on ``organizations`` matches ``id = app.current_org``.
    """

    async def get(self) -> Organization | None:
        return await self.session.get(Organization, self.org_id)

    async def rename(self, name: str) -> None:
        await self.session.execute(
            update(Organization)
            .where(Organization.id == self.org_id, Organization.deleted_at.is_(None))
            .values(name=name)
        )


class MemberRepository(TenantRepository):
    """``organization_members`` joined to ``users`` for display.

    The join is safe under RLS: ``users`` is visible through the
    ``user_visible_to_co_members`` policy, which is itself scoped to
    ``app.current_org`` — so this returns the members of this organization and
    nobody else's users, even though ``users`` has no ``organization_id``.
    """

    async def page(
        self, *, limit: int | None = None, cursor: str | None = None
    ) -> tuple[Sequence[Row[Any]], int]:
        size = clamp_page_size(limit)
        statement = self._select().order_by(
            OrganizationMember.created_at, OrganizationMember.user_id
        )
        statement = _after(statement, decode_cursor(cursor))
        rows = (await self.session.execute(statement.limit(size + 1))).all()
        return rows[:size], size

    def _select(self) -> Select[Any]:
        return (
            select(
                OrganizationMember.user_id,
                OrganizationMember.role,
                OrganizationMember.status,
                OrganizationMember.joined_at,
                OrganizationMember.created_at,
                User.email,
                User.display_name,
                User.avatar_url,
            )
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == self.org_id)
        )

    async def get(self, user_id: uuid.UUID) -> OrganizationMember | None:
        return await self.session.get(OrganizationMember, (self.org_id, user_id))

    async def detail(self, user_id: uuid.UUID) -> Row[Any] | None:
        """One member, with the same columns :meth:`page` returns."""
        statement = self._select().where(OrganizationMember.user_id == user_id)
        return (await self.session.execute(statement)).first()

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        role: OrganizationRole,
        status: MemberStatus,
        invited_by: uuid.UUID | None,
        joined_at: datetime | None,
    ) -> OrganizationMember:
        member = OrganizationMember(
            organization_id=self.org_id,
            user_id=user_id,
            role=role,
            status=status,
            invited_by=invited_by,
            joined_at=joined_at,
        )
        self.session.add(member)
        await self.session.flush()
        return member

    async def set_role(self, user_id: uuid.UUID, role: OrganizationRole) -> None:
        await self.session.execute(
            update(OrganizationMember)
            .where(
                OrganizationMember.organization_id == self.org_id,
                OrganizationMember.user_id == user_id,
            )
            .values(role=role)
        )

    async def remove(self, user_id: uuid.UUID) -> None:
        member = await self.get(user_id)
        if member is not None:
            await self.session.delete(member)
            await self.session.flush()

    async def count_active_owners(self) -> int:
        """How many people can still administer this organization.

        The last-OWNER guard reads this. ``status`` matters: a suspended or
        merely invited owner cannot act, so counting them would let an
        organization end up with an owner seat nobody can sit in — locked out
        of billing, ownership transfer and deletion (SECURITY.md §2).
        """
        total = await self.session.scalar(
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == self.org_id,
                OrganizationMember.role == OrganizationRole.OWNER,
                OrganizationMember.status == MemberStatus.ACTIVE,
            )
        )
        return total or 0


def _after(statement: Select[Any], cursor: tuple[datetime, uuid.UUID] | None) -> Select[Any]:
    if cursor is None:
        return statement
    created_at, row_id = cursor
    # a row comparison, not two ANDed predicates: ``(created_at, user_id) >
    # (:ts, :id)`` is one index-ordered seek and gets the tie-break right when
    # several members were created in the same transaction
    return statement.where(
        tuple_(OrganizationMember.created_at, OrganizationMember.user_id) > (created_at, row_id)
    )
