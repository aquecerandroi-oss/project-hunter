"""The B3 robot's identity, authority and kill switch — DATABASE.md §74,
``docs/RISK_ENGINE_B3.md`` §2, §4.3, §7, §10.2.

The **robot account** row is the stable lock of the robot scope (§3.3: locks in
the order system → organization → robot): grant, revoke, arm, disarm, every
robot kill-switch move and the claim of an entry all lock it ``FOR UPDATE``
(the guard triggers take the lock themselves). It also holds the robot scope's
kill switch: the effective state plus the **set** of latched causes, so a
session turnover that releases ``daily_loss_limit`` cannot release a
``broker_reject_breaker`` latched on top of it (Astra, R3 design review).

``b3_robot_authority`` is **one row per account** (§2): a new grant replaces
``authority_id`` and bumps ``fencing_token``; the trigger anchors ``granted_at``
on the database clock and refuses renewals.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY, org_fk, pg_enum
from hunter_core.db.models.b3 import hex64
from hunter_core.domain.b3_enums import B3AuthorityPhase, B3AuthorityStatus, B3KillCause
from hunter_core.domain.enums import KillSwitchState

LATCHED = "('TRADING_DISABLED', 'EMERGENCY')"
"""The two kill states that only a named cause holds (§7.1)."""

_CAUSES: ARRAY[Any] = ARRAY(pg_enum("b3_kill_cause"))
"""``b3_kill_cause[]`` — the latched set (one object, shared by the three columns)."""


def account_fk(column: str = "account_hash") -> ForeignKeyConstraint:
    """``(organization_id, <column>)`` -> the robot account (DATABASE.md §15.4)."""
    return ForeignKeyConstraint(
        ["organization_id", column],
        ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
        ondelete="CASCADE",
    )


def instance_fk(column: str = "instance_id") -> ForeignKeyConstraint:
    """``(organization_id, <column>)`` -> the instance, never across tenants."""
    return ForeignKeyConstraint(
        ["organization_id", column],
        ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
        ondelete="CASCADE",
    )


class B3RobotAccount(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """``b3_robot_accounts`` — the registered account, the authorized host and the
    robot scope's kill switch (``kill_switch_state``, the SPOT enum, §1.2)."""

    __tablename__ = "b3_robot_accounts"
    __table_args__ = (
        org_fk(),
        UniqueConstraint(
            "organization_id", "registered_account_hash", name="uq_b3_robot_accounts_account"
        ),
        hex64("registered_account_hash"),
        hex64("authorized_host_hash"),
        CheckConstraint(
            f"(kill_state IN {LATCHED}) = (cardinality(active_causes) > 0)",
            name="latched_iff_a_cause_holds",
        ),
    )

    registered_account_hash: Mapped[str] = mapped_column(Text)
    authorized_host_hash: Mapped[str] = mapped_column(Text)
    kill_state: Mapped[KillSwitchState] = mapped_column(
        pg_enum("kill_switch_state"), server_default=KillSwitchState.ACTIVE.value
    )
    active_causes: Mapped[list[B3KillCause]] = mapped_column(
        _CAUSES, server_default=text("'{}'::b3_kill_cause[]")
    )
    kill_changed_at: Mapped[datetime | None]


class B3KillSwitchTransition(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_kill_switch_transitions`` — every robot-scope move, append-only (§7).

    ``changed_at`` is the database clock: §5.2 recovers an exit obligation from
    "a durable transition to EMERGENCY with ``changed_at`` inside the position's
    life". ``causes_after`` is the latched set the move left behind.
    """

    __tablename__ = "b3_kill_switch_transitions"
    __table_args__ = (
        org_fk(),
        account_fk(),
        Index(
            "ix_b3_kill_switch_transitions_account_changed",
            "organization_id",
            "account_hash",
            "changed_at",
        ),
        CheckConstraint(
            "from_state <> to_state OR from_causes IS DISTINCT FROM causes_after",
            name="a_transition_moves",
        ),
        CheckConstraint(
            f"(to_state IN {LATCHED}) = (cardinality(causes_after) > 0)",
            name="latched_iff_a_cause_holds",
        ),
        CheckConstraint(
            "actor_type IN ('user', 'agent', 'robot', 'system')", name="actor_type_is_known"
        ),
        # §7.2: an agent credential may only ask for TRADING_DISABLED.
        CheckConstraint(
            "actor_type <> 'agent' OR (to_state = 'TRADING_DISABLED' "
            "AND from_state < 'TRADING_DISABLED' AND cause = 'agent_command')",
            name="an_agent_only_disables",
        ),
        # §7.1: leaving EMERGENCY is the Everton's rearm, never automatic; and the
        # only latch anyone else may release is daily_loss_limit (D8, next session).
        CheckConstraint(
            "actor_type = 'user' OR NOT (from_state = 'EMERGENCY' AND to_state <> 'EMERGENCY')",
            name="only_the_owner_leaves_emergency",
        ),
        CheckConstraint(
            "actor_type = 'user' OR from_causes <@ "
            "(causes_after || ARRAY['daily_loss_limit']::b3_kill_cause[])",
            name="only_the_owner_releases_a_latch",
        ),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence_is_an_object"),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    from_state: Mapped[KillSwitchState] = mapped_column(pg_enum("kill_switch_state"))
    to_state: Mapped[KillSwitchState] = mapped_column(pg_enum("kill_switch_state"))
    from_causes: Mapped[list[B3KillCause]] = mapped_column(_CAUSES)
    causes_after: Mapped[list[B3KillCause]] = mapped_column(_CAUSES)
    cause: Mapped[B3KillCause | None] = mapped_column(pg_enum("b3_kill_cause"))
    reason: Mapped[str] = mapped_column(Text)
    actor_type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[uuid.UUID | None]
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY)
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class B3RobotInstance(Base, TenantMixin):
    """``b3_robot_instances`` — one row per process start (§2.2), append-only.

    ``account_hash_seen`` is **not** a foreign key: an instance on the wrong
    account is exactly what this row has to be able to record.
    """

    __tablename__ = "b3_robot_instances"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("organization_id", "instance_id", name="uq_b3_robot_instances_org"),
        Index("ix_b3_robot_instances_org_started", "organization_id", "started_at"),
        hex64("host_hash"),
        hex64("account_hash_seen"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    host_hash: Mapped[str] = mapped_column(Text)
    account_hash_seen: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class B3RobotAuthority(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_robot_authority`` — machine A (§2), one row per account."""

    __tablename__ = "b3_robot_authority"
    __table_args__ = (
        org_fk(),
        account_fk(),
        instance_fk(),
        ForeignKeyConstraint(
            ["organization_id", "account_hash", "spec_pin_id"],
            ["b3_spec_pins.organization_id", "b3_spec_pins.account_hash", "b3_spec_pins.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "account_hash", name="uq_b3_robot_authority_account"),
        UniqueConstraint("authority_id", name="uq_b3_robot_authority_authority_id"),
        Index("ix_b3_robot_authority_instance", "organization_id", "instance_id"),
        Index("ix_b3_robot_authority_spec_pin", "organization_id", "account_hash", "spec_pin_id"),
        hex64("host_hash"),
        CheckConstraint("phase <> 'read_only'", name="read_only_has_no_row"),
        CheckConstraint("fencing_token >= 1", name="fencing_token_is_positive"),
        CheckConstraint("authority_expires_at > granted_at", name="expires_after_the_grant"),
        CheckConstraint("(status = 'revoked') = (revoked_at IS NOT NULL)", name="revoked_iff_at"),
        CheckConstraint("(status = 'expired') = (expired_at IS NOT NULL)", name="expired_iff_at"),
        CheckConstraint("(phase = 'entries') = (armed_at IS NOT NULL)", name="entries_iff_armed"),
        CheckConstraint(
            "(armed_at IS NULL) = (armed_strategy_key IS NULL) "
            "AND (armed_at IS NULL) = (armed_strategy_version IS NULL) "
            "AND (armed_at IS NULL) = (armed_params_hash IS NULL) "
            "AND (armed_at IS NULL) = (limits_version IS NULL) "
            "AND (armed_at IS NULL) = (spec_pin_id IS NULL)",
            name="arming_is_whole",
        ),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    authority_id: Mapped[uuid.UUID]
    host_hash: Mapped[str] = mapped_column(Text)
    instance_id: Mapped[uuid.UUID]
    session_date: Mapped[date]
    fencing_token: Mapped[int] = mapped_column(BigInteger)
    granted_at: Mapped[datetime] = mapped_column(server_default=func.now())
    authority_expires_at: Mapped[datetime]
    status: Mapped[B3AuthorityStatus] = mapped_column(
        pg_enum("b3_authority_status"), server_default=B3AuthorityStatus.ACTIVE.value
    )
    phase: Mapped[B3AuthorityPhase] = mapped_column(
        pg_enum("b3_authority_phase"), server_default=B3AuthorityPhase.MANAGEMENT.value
    )
    revoked_at: Mapped[datetime | None]
    expired_at: Mapped[datetime | None]
    armed_at: Mapped[datetime | None]
    armed_strategy_key: Mapped[str | None] = mapped_column(Text)
    armed_strategy_version: Mapped[int | None]
    armed_params_hash: Mapped[str | None] = mapped_column(Text)
    limits_version: Mapped[int | None]
    spec_pin_id: Mapped[uuid.UUID | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class B3ManagementEpoch(Base, TenantMixin):
    """``b3_management_epochs`` — one per grant (§4.3); at most one open per account.

    A crashed instance never closes its epoch: the next grant closes it with
    ``closed_clean = false`` — that is what makes the next instance inherit
    ``unknown`` slots (§4.3, "herança na partida").
    """

    __tablename__ = "b3_management_epochs"
    __table_args__ = (
        org_fk(),
        account_fk(),
        instance_fk(),
        UniqueConstraint(
            "organization_id", "account_hash", "epoch_id", name="uq_b3_management_epochs_account"
        ),
        Index("ix_b3_management_epochs_account", "organization_id", "account_hash", "opened_at"),
        Index("ix_b3_management_epochs_instance", "organization_id", "instance_id"),
        Index(
            "uq_b3_management_epochs_open",
            "organization_id",
            "account_hash",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        hex64("host_hash"),
        CheckConstraint("(closed_at IS NULL) = (closed_clean IS NULL)", name="closed_is_whole"),
        CheckConstraint("closed_at IS NULL OR closed_at >= opened_at", name="closes_after_open"),
    )

    epoch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    account_hash: Mapped[str] = mapped_column(Text)
    instance_id: Mapped[uuid.UUID]
    authority_id: Mapped[uuid.UUID]
    host_hash: Mapped[str] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(server_default=func.now())
    closed_at: Mapped[datetime | None]
    closed_clean: Mapped[bool | None]


class B3RobotHeartbeat(Base, TenantMixin):
    """``b3_robot_heartbeats`` — the latest ``hb:b3:robot`` of **each instance** (§10.2).

    Per instance, not per account: the first beat of a new instance must not
    overwrite the last one of the previous instance, which the inheritance of
    §4.3 reads (``heartbeat_in_flight``). Upserted; not audited (a beat every
    5 s is liveness, not a mutation).
    """

    __tablename__ = "b3_robot_heartbeats"
    __table_args__ = (
        org_fk(),
        account_fk(),
        instance_fk(),
        Index("ix_b3_robot_heartbeats_account_as_of", "organization_id", "account_hash", "as_of"),
        CheckConstraint("jsonb_typeof(payload) = 'object'", name="payload_is_an_object"),
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    account_hash: Mapped[str] = mapped_column(Text)
    as_of: Mapped[datetime]
    received_at: Mapped[datetime] = mapped_column(server_default=func.now())
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
