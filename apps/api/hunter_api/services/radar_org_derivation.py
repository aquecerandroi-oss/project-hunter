"""``IN_POSITION``/``RISK_BLOCKED`` — PIPELINE.md §5's "derived per organization
at read time", for the global radar/opportunities endpoints.

Opens its own ``tenant_session`` (RLS, ``app.current_org`` set) independent of
the caller's ``PrincipalSession`` — the radar/opportunities routes are global,
no-RLS reads (``repositories/radar.py``'s module docstring), and the
positions/kill-switch tables this reads are tenant tables governed by RLS
(``hunter_core/db/models/execution.py``'s ``Position``,
``hunter_core/db/models/portfolios.py``'s ``Portfolio``). A single connection
cannot be both at once, so this is a second, short-lived transaction.

**``risk_blocked`` is scoped to the kill switch only, and only to the states
that actually block entries.** M2 ships no Risk Engine (that is M3/M4,
``RISK_ENGINE.md``): there is no exposure/limit check this API could honestly
run yet. ``RISK_ENGINE.md`` §5 (kill switch table): ``WARNING`` still allows
entries — half-sized (``ks_multiplier`` 0.5) — so it must **not** read as
blocked here; only ``TRADING_DISABLED`` and ``EMERGENCY`` do (its RiskCheck
#1, "``kill_switch``", is defined as `efetivo ∈ {TRADING_DISABLED,
EMERGENCY}`). ``true`` is definitive (one of those two states really is
stopping new entries) and it is **org-wide**: any one blocked portfolio (or
the organization's own switch) marks every opportunity blocked for that org,
even one a blocked portfolio would never have traded — a finer, per-portfolio
answer needs a portfolio in the request, which the radar/opportunities
endpoints do not take. ``false`` means only "no ``TRADING_DISABLED``/
``EMERGENCY`` kill switch was found" — a narrower claim than "this trade
clears every risk check", which M2 cannot evaluate at all; the field's
docstring (``schemas/radar.py``/``schemas/opportunities.py``) says so and
must not be read as the latter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from hunter_api.auth.rbac import OrganizationNotFoundError
from hunter_core.db.models.execution import Position
from hunter_core.db.models.identity import Organization
from hunter_core.db.models.portfolios import Portfolio
from hunter_core.db.session import tenant_session
from hunter_core.domain.enums import KillSwitchState, PositionStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from hunter_api.auth.principal import Membership, Principal

_OPEN_POSITION_STATUSES = (PositionStatus.OPEN, PositionStatus.CLOSING)
_BLOCKING_KILL_SWITCH_STATES = (KillSwitchState.TRADING_DISABLED, KillSwitchState.EMERGENCY)
"""RISK_ENGINE.md §5: ``WARNING`` still allows entries (half-sized) — only
these two states actually block new entries."""


def resolve_optional_org(principal: Principal, org_id: uuid.UUID | None) -> Membership | None:
    """The caller's membership of ``org_id``, or ``None`` when no ``org_id``
    was supplied at all.

    Same 404-not-403 shape as ``auth.rbac.get_org_context`` (an organization
    id the caller has no active membership of must be indistinguishable from
    one that does not exist) — reused rather than duplicated, since this is a
    query parameter here instead of a path parameter.
    """
    if org_id is None:
        return None
    membership = principal.membership(org_id)
    if membership is None:
        raise OrganizationNotFoundError
    return membership


@dataclass(frozen=True, slots=True)
class OrgDerivation:
    in_position_market_ids: frozenset[uuid.UUID]
    risk_blocked: bool
    risk_blocked_reason: str | None


async def load_org_derivation(
    session_factory: async_sessionmaker[AsyncSession],
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> OrgDerivation:
    async with tenant_session(session_factory, org_id, user_id) as session:
        market_ids = await _open_position_market_ids(session, org_id)
        blocked, reason = await _kill_switch_block(session, org_id)
    return OrgDerivation(
        in_position_market_ids=frozenset(market_ids),
        risk_blocked=blocked,
        risk_blocked_reason=reason,
    )


async def _open_position_market_ids(session: AsyncSession, org_id: uuid.UUID) -> set[uuid.UUID]:
    rows = (
        await session.execute(
            select(Position.market_id).where(
                Position.organization_id == org_id,
                Position.status.in_(_OPEN_POSITION_STATUSES),
            )
        )
    ).scalars()
    return set(rows)


async def _kill_switch_block(session: AsyncSession, org_id: uuid.UUID) -> tuple[bool, str | None]:
    org_row = (
        await session.execute(
            select(Organization.kill_switch_state, Organization.kill_switch_reason).where(
                Organization.id == org_id, Organization.deleted_at.is_(None)
            )
        )
    ).first()
    if org_row is not None and org_row.kill_switch_state in _BLOCKING_KILL_SWITCH_STATES:
        return True, org_row.kill_switch_reason
    portfolio_row = (
        await session.execute(
            select(Portfolio.kill_switch_state, Portfolio.kill_switch_reason).where(
                Portfolio.organization_id == org_id,
                Portfolio.kill_switch_state.in_(_BLOCKING_KILL_SWITCH_STATES),
                Portfolio.deleted_at.is_(None),
            )
        )
    ).first()
    if portfolio_row is not None:
        return True, portfolio_row.kill_switch_reason
    return False, None
