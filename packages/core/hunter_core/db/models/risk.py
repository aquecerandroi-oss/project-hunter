"""Risk events and kill switch history — DATABASE.md §7.

Both are append-only: ``hunter_app`` gets INSERT and SELECT and never UPDATE or
DELETE (§1.2). ``kill_switch_transitions`` carries a **nullable**
``organization_id`` — ``NULL`` exactly when the scope is ``system`` — so it is an
RLS table like every other row that belongs to a tenant. Leaving it out of RLS
and filtering on ``(scope, scope_id)`` in the repositories, as the first draft
did, made every organization's kill-switch history readable by any other.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, org_fk, pg_enum
from hunter_core.domain.enums import (
    KillSwitchScope,
    KillSwitchState,
    RiskEventSeverity,
    RiskEventType,
)


class RiskEvent(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """Something the Risk Engine wants a human to see. ``critical`` also goes to
    Sentry and to an in-app notification for OWNER/ADMIN (RISK_ENGINE.md §6).
    """

    __tablename__ = "risk_events"
    __table_args__ = (
        org_fk(),
        Index("ix_risk_events_org_created", "organization_id", "created_at"),
    )

    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[RiskEventType] = mapped_column(pg_enum("risk_event_type"))
    severity: Mapped[RiskEventSeverity] = mapped_column(
        pg_enum("event_severity"), server_default=RiskEventSeverity.INFO.value
    )
    message: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    triggered_by: Mapped[str | None] = mapped_column(Text)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    acknowledged_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class KillSwitchTransition(Base, UUIDPrimaryKeyMixin):
    """Every kill switch move, at any scope. Downward moves are always manual.

    ``organization_id`` is nullable because a ``system`` transition belongs to no
    tenant, and the CHECK ties the two together so neither can drift: system
    rows have no organization, organization/portfolio rows always have one.
    Two policies follow from that — ``tenant_isolation`` for a tenant's own
    history and ``system_scope_readable`` so every tenant can see that the
    platform-wide switch moved (they are affected by it).
    """

    __tablename__ = "kill_switch_transitions"
    __table_args__ = (
        org_fk(),
        CheckConstraint(
            "(scope = 'system') = (organization_id IS NULL)", name="system_scope_has_no_org"
        ),
        Index("ix_kill_switch_transitions_scope_created", "scope", "scope_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    scope: Mapped[KillSwitchScope] = mapped_column(pg_enum("ks_scope"))
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    from_state: Mapped[KillSwitchState] = mapped_column(pg_enum("kill_switch_state"))
    to_state: Mapped[KillSwitchState] = mapped_column(pg_enum("kill_switch_state"))
    reason: Mapped[str | None] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
