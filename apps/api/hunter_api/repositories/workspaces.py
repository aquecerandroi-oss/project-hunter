"""Workspace and risk-profile repositories."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, tuple_

from hunter_api.repositories.base import TenantRepository, clamp_page_size, decode_cursor
from hunter_core.db.models.identity import Workspace
from hunter_core.db.models.markets import Exchange
from hunter_core.db.models.portfolios import RiskProfile
from hunter_core.domain.types import uuid7

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_core.domain.enums import RiskPreset, WorkspaceObjective


class WorkspaceRepository(TenantRepository):
    async def create(
        self,
        *,
        name: str,
        objective: WorkspaceObjective,
        default_risk_profile_id: uuid.UUID | None = None,
        workspace_id: uuid.UUID | None = None,
    ) -> Workspace:
        workspace = Workspace(
            id=workspace_id or uuid7(),
            organization_id=self.org_id,
            name=name,
            objective=objective,
            default_risk_profile_id=default_risk_profile_id,
            settings={},
        )
        self.session.add(workspace)
        await self.session.flush()
        return workspace

    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        workspace = await self.session.get(Workspace, workspace_id)
        if workspace is None or workspace.organization_id != self.org_id:
            return None
        return None if workspace.deleted_at is not None else workspace

    async def page(
        self, *, limit: int | None = None, cursor: str | None = None
    ) -> tuple[Sequence[Workspace], int]:
        size = clamp_page_size(limit)
        statement = (
            select(Workspace)
            .where(Workspace.organization_id == self.org_id, Workspace.deleted_at.is_(None))
            .order_by(Workspace.created_at, Workspace.id)
        )
        after = decode_cursor(cursor)
        if after is not None:
            statement = statement.where(tuple_(Workspace.created_at, Workspace.id) > after)
        rows = (await self.session.execute(statement.limit(size + 1))).scalars().all()
        return rows[:size], size

    async def first(self) -> Workspace | None:
        """The organization's oldest live workspace — the one onboarding uses
        and the one ``/me`` reports onboarding state from.
        """
        return (
            await self.session.execute(
                select(Workspace)
                .where(Workspace.organization_id == self.org_id, Workspace.deleted_at.is_(None))
                .order_by(Workspace.created_at)
                .limit(1)
            )
        ).scalar_one_or_none()


class RiskProfileRepository(TenantRepository):
    """The organization's own risk profiles, plus read access to the seeded
    system presets (``organization_id IS NULL``), which the
    ``system_presets_readable`` policy exists precisely to allow.
    """

    async def copy_preset_for_org(self, preset: RiskPreset, created_by: uuid.UUID) -> RiskProfile:
        """Return this organization's profile for ``preset``, copying the
        system one if it does not have it yet.

        A copy, not a reference: an organization must be able to tune its own
        limits without editing a row every other tenant reads, and the
        ``tenant_isolation`` ``WITH CHECK`` makes writing the system row
        impossible anyway.
        """
        existing = (
            await self.session.execute(
                select(RiskProfile).where(
                    RiskProfile.organization_id == self.org_id, RiskProfile.preset == preset
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        template = await system_preset(self.session, preset)
        profile = RiskProfile(
            id=uuid7(),
            organization_id=self.org_id,
            name=template.name if template else preset.value.title(),
            preset=preset,
            limits=dict(template.limits) if template else {},
            created_by=created_by,
        )
        self.session.add(profile)
        await self.session.flush()
        return profile


async def system_preset(session: AsyncSession, preset: RiskPreset) -> RiskProfile | None:
    """The seeded, organization-less template for ``preset`` (``infra/scripts/seed.py``)."""
    return (
        await session.execute(
            select(RiskProfile).where(
                RiskProfile.organization_id.is_(None), RiskProfile.preset == preset
            )
        )
    ).scalar_one_or_none()


async def exchange_codes(session: AsyncSession) -> set[str]:
    """Every seeded exchange code — the allowlist onboarding validates against.

    A global read-only table for ``hunter_app``: the API can check the code a
    user picked, and cannot invent a new exchange.
    """
    rows: Sequence[Any] = (await session.execute(select(Exchange.code))).scalars().all()
    return {str(code) for code in rows}
