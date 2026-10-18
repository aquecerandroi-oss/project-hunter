"""The B3 robot's protection and exit records — DATABASE.md §74,
``docs/RISK_ENGINE_B3.md`` §4.3, §5.2–§5.3.

``b3_sltp_requests`` is written **before** the ``order_send`` (status
``intended``, §4.3, I-SL-5) and its status never downgrades a terminal one;
``b3_exit_intents`` is the exit obligation with its original deadline, written
before the first SLTP of the exit and never recalculated (I-X-3, I-X-4);
``b3_bracket_learning`` is the per-session ``k`` of §5.3, which only grows.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import org_fk, pg_enum
from hunter_core.db.models.b3_robot import account_fk
from hunter_core.domain.b3_enums import B3ExitReason, B3SltpRequestStatus


def position_fk() -> ForeignKeyConstraint:
    """``(organization_id, account_hash, position_id)`` -> machine C's row."""
    return ForeignKeyConstraint(
        ["organization_id", "account_hash", "position_id"],
        ["b3_positions.organization_id", "b3_positions.account_hash", "b3_positions.position_id"],
        ondelete="CASCADE",
    )


class B3SltpRequest(Base, TenantMixin, TimestampMixin):
    """``b3_sltp_requests`` — one ``TRADE_ACTION_SLTP`` request (§4.3).

    ``sl > 0`` is I-SL-1 in the schema; ``request_position_ticket`` is the ticket
    actually sent (I-SL-4); ``resolved_manual`` needs the P4 evidence — the
    terminal's Journal line of *that* request, not "I checked the Journal".
    """

    __tablename__ = "b3_sltp_requests"
    __table_args__ = (
        org_fk(),
        account_fk(),
        position_fk(),
        ForeignKeyConstraint(
            ["organization_id", "account_hash", "epoch_id"],
            [
                "b3_management_epochs.organization_id",
                "b3_management_epochs.account_hash",
                "b3_management_epochs.epoch_id",
            ],
            ondelete="CASCADE",
        ),
        Index(
            "ix_b3_sltp_requests_position",
            "organization_id",
            "account_hash",
            "position_id",
            "built_at",
        ),
        Index("ix_b3_sltp_requests_epoch", "organization_id", "account_hash", "epoch_id"),
        # §4.3: one SLTP request at a time per position — a second may not be
        # recorded while one is still intended or uncertain (the slot, in the schema).
        Index(
            "uq_b3_sltp_requests_one_in_flight",
            "organization_id",
            "account_hash",
            "position_id",
            unique=True,
            postgresql_where=text("status IN ('intended', 'unknown')"),
        ),
        CheckConstraint("sl > 0", name="never_without_a_stop"),
        CheckConstraint("tp >= 0", name="tp_zero_or_positive"),
        CheckConstraint("purpose IN ('repair', 'bracket')", name="purpose_is_a_known_label"),
        CheckConstraint(
            "(status = 'resolved_manual') = (resolved_at IS NOT NULL) "
            "AND (resolved_at IS NULL) = (resolved_by IS NULL) "
            "AND (resolved_at IS NULL OR (p4_evidence IS NOT NULL "
            "AND length(btrim(p4_evidence)) > 0))",
            name="manual_resolution_carries_the_journal_line",
        ),
    )

    sltp_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    account_hash: Mapped[str] = mapped_column(Text)
    position_id: Mapped[int] = mapped_column(BigInteger)
    epoch_id: Mapped[uuid.UUID]
    request_position_ticket: Mapped[int] = mapped_column(BigInteger)
    sl: Mapped[Decimal]
    tp: Mapped[Decimal]
    purpose: Mapped[str] = mapped_column(Text)
    built_at: Mapped[datetime]
    status: Mapped[B3SltpRequestStatus] = mapped_column(
        pg_enum("b3_sltp_request_status"), server_default=B3SltpRequestStatus.INTENDED.value
    )
    retcode: Mapped[str | None] = mapped_column(Text)
    result_at: Mapped[datetime | None]
    p4_evidence: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None]
    resolved_by: Mapped[uuid.UUID | None]


class B3ExitIntent(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_exit_intents`` — the exit obligation of a position (§5.2), append-only.

    One per position: an exit started only ends in ``closed`` and a new trigger
    never extends the deadline, so there is never a second one to write.
    """

    __tablename__ = "b3_exit_intents"
    __table_args__ = (
        org_fk(),
        account_fk(),
        position_fk(),
        UniqueConstraint(
            "organization_id", "account_hash", "position_id", name="uq_b3_exit_intents_position"
        ),
        CheckConstraint("deadline_at > exit_due_at", name="deadline_after_due"),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    position_id: Mapped[int] = mapped_column(BigInteger)
    exit_reason: Mapped[B3ExitReason] = mapped_column(pg_enum("b3_exit_reason"))
    exit_due_at: Mapped[datetime]
    started_at: Mapped[datetime]
    deadline_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class B3BracketLearning(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """``b3_bracket_learning`` — ``k`` learned per session and symbol (§5.3); only grows."""

    __tablename__ = "b3_bracket_learning"
    __table_args__ = (
        org_fk(),
        account_fk(),
        UniqueConstraint(
            "organization_id",
            "account_hash",
            "session_date",
            "symbol",
            name="uq_b3_bracket_learning_session",
        ),
        CheckConstraint("k >= 0", name="k_not_negative"),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    session_date: Mapped[date]
    symbol: Mapped[str] = mapped_column(Text)
    k: Mapped[int] = mapped_column(SmallInteger)
