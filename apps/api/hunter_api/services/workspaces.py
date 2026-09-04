"""Workspaces and the onboarding flow (PRODUCT.md §3).

Where onboarding is stored, and why: ``workspaces`` in M0 has ``objective``,
``default_risk_profile_id`` and a ``settings`` JSONB. The virtual capital, the
monitored exchanges and the completion timestamp live in ``settings`` because
no column exists for them and T06 does not change the schema. They are read as
a unit, never filtered on, which is exactly what DATABASE.md §1 says JSONB is
for. ``docs/DATABASE.md`` §2 lists ``settings JSONB (monitored_exchanges,
base_currency, timezone)``, so this is the intended home; the follow-up, if a
query ever needs to filter on capital, is a real column in a later migration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from fastapi import status

from hunter_api.errors import HunterError
from hunter_api.repositories.workspaces import (
    RiskProfileRepository,
    WorkspaceRepository,
    exchange_codes,
)
from hunter_core.audit import audited
from hunter_core.domain.types import utcnow

if TYPE_CHECKING:
    from collections.abc import Mapping

    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.schemas.workspaces import OnboardingUpdate, WorkspaceCreate, WorkspaceUpdate
    from hunter_core.db.models.identity import Workspace

CAPITAL_KEY = "default_initial_capital"
EXCHANGES_KEY = "monitored_exchanges"
COMPLETED_KEY = "onboarding_completed_at"
RISK_PRESET_KEY = "risk_preset"


class WorkspaceNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="workspace-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        )


class UnknownExchangeError(HunterError):
    def __init__(self, codes: list[str]) -> None:
        super().__init__(
            type_slug="unknown-exchange",
            title="Validation Error",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown exchange code(s): {', '.join(sorted(codes))}.",
        )


@audited("workspace.created", "workspace")
async def create_workspace(
    *, session: AsyncSession, org_id: uuid.UUID, payload: WorkspaceCreate, **_audit: Any
) -> dict[str, Any]:
    workspace = await WorkspaceRepository(session, org_id).create(
        name=payload.name, objective=payload.objective
    )
    return {"id": str(workspace.id), "name": workspace.name, "objective": workspace.objective.value}


async def _workspace_before(**kwargs: Any) -> dict[str, Any] | None:
    session: AsyncSession = kwargs["session"]
    org_id: uuid.UUID = kwargs["org_id"]
    workspace_id: uuid.UUID = kwargs["workspace_id"]
    workspace = await WorkspaceRepository(session, org_id).get(workspace_id)
    return None if workspace is None else _snapshot(workspace)


@audited("workspace.updated", "workspace", before=_workspace_before)
async def update_workspace(
    *,
    session: AsyncSession,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    **_audit: Any,
) -> dict[str, Any]:
    workspace = await _require(session, org_id, workspace_id)
    if payload.name is not None:
        workspace.name = payload.name
    if payload.objective is not None:
        workspace.objective = payload.objective
    await session.flush()
    return _snapshot(workspace)


@audited("workspace.onboarded", "workspace", before=_workspace_before)
async def complete_onboarding(
    *,
    session: AsyncSession,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    payload: OnboardingUpdate,
    actor: uuid.UUID,
    **_audit: Any,
) -> dict[str, Any]:
    """Persist the onboarding answers. Idempotent by construction.

    A PUT is a statement of the desired state, and re-submitting it must not
    change the answer — so ``onboarding_completed_at`` keeps its **first**
    value. That timestamp is a fact about when this organization finished
    onboarding, and a re-save from the settings screen months later must not
    rewrite it.
    """
    workspace = await _require(session, org_id, workspace_id)
    await _validate_exchanges(session, payload.monitored_exchanges)
    profile = await RiskProfileRepository(session, org_id).copy_preset_for_org(
        payload.risk_preset, actor
    )

    settings = dict(workspace.settings)
    settings[CAPITAL_KEY] = _capital(payload.virtual_capital)
    settings[EXCHANGES_KEY] = list(payload.monitored_exchanges)
    settings[RISK_PRESET_KEY] = payload.risk_preset.value
    settings.setdefault(COMPLETED_KEY, utcnow().isoformat())

    workspace.objective = payload.objective
    workspace.settings = settings
    workspace.default_risk_profile_id = profile.id
    await session.flush()
    return _snapshot(workspace)


async def _require(session: AsyncSession, org_id: uuid.UUID, workspace_id: uuid.UUID) -> Workspace:
    workspace = await WorkspaceRepository(session, org_id).get(workspace_id)
    if workspace is None:
        raise WorkspaceNotFoundError
    return workspace


async def _validate_exchanges(session: AsyncSession, codes: list[str]) -> None:
    """Only codes that exist in the seeded ``exchanges`` catalogue.

    Without this, a typo would be persisted and the market worker would
    silently monitor nothing — the failure would surface weeks later as "the
    radar is empty", with no error anywhere.
    """
    if not codes:
        return
    known = await exchange_codes(session)
    unknown = [code for code in codes if code not in known]
    if unknown:
        raise UnknownExchangeError(unknown)


def completed_at(settings: Mapping[str, Any]) -> datetime | None:
    """When this workspace finished onboarding, or ``None``.

    Tolerant of a malformed value rather than raising: the field is JSONB, and
    an unparseable timestamp should read as "not finished" instead of taking
    down ``/me`` for everyone in the organization.
    """
    raw = settings.get(COMPLETED_KEY)
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _capital(value: Decimal) -> str:
    """Money crosses into JSONB as a string. ``json`` has one numeric type and
    it is a float; ``10000.10`` would come back as ``10000.099999999999``.
    """
    return str(value)


def _snapshot(workspace: Workspace) -> dict[str, Any]:
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "objective": workspace.objective.value,
        "settings": dict(workspace.settings),
        "default_risk_profile_id": str(workspace.default_risk_profile_id)
        if workspace.default_risk_profile_id
        else None,
    }
