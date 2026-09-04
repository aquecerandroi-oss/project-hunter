"""Invitation repository."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, tuple_

from hunter_api.repositories.base import TenantRepository, clamp_page_size, decode_cursor
from hunter_core.db.models.identity import OrganizationInvitation
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from hunter_core.domain.enums import OrganizationRole


class InvitationRepository(TenantRepository):
    async def create(
        self,
        *,
        email: str,
        role: OrganizationRole,
        token_hash: str,
        expires_at: datetime,
        created_by: uuid.UUID,
    ) -> OrganizationInvitation:
        invitation = OrganizationInvitation(
            id=uuid7(),
            organization_id=self.org_id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
            created_by=created_by,
        )
        self.session.add(invitation)
        await self.session.flush()
        # created_at is a server default; refresh so the caller can return it
        # without a second query
        await self.session.refresh(invitation)
        return invitation

    async def get(self, invitation_id: uuid.UUID) -> OrganizationInvitation | None:
        invitation = await self.session.get(OrganizationInvitation, invitation_id)
        # belt to the RLS braces: a row from another tenant cannot reach here,
        # and if one ever did it would not be returned
        if invitation is None or invitation.organization_id != self.org_id:
            return None
        return invitation

    async def page(
        self, *, limit: int | None = None, cursor: str | None = None
    ) -> tuple[Sequence[OrganizationInvitation], int]:
        size = clamp_page_size(limit)
        statement = (
            select(OrganizationInvitation)
            .where(OrganizationInvitation.organization_id == self.org_id)
            .order_by(OrganizationInvitation.created_at, OrganizationInvitation.id)
        )
        after = decode_cursor(cursor)
        if after is not None:
            statement = statement.where(
                tuple_(OrganizationInvitation.created_at, OrganizationInvitation.id) > after
            )
        rows = (await self.session.execute(statement.limit(size + 1))).scalars().all()
        return rows[:size], size

    async def delete(self, invitation: OrganizationInvitation) -> None:
        await self.session.delete(invitation)
        await self.session.flush()
