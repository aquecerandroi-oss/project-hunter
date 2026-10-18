"""What the broker shows, as the B3 robot recorded it — DATABASE.md §74,
``docs/RISK_ENGINE_B3.md`` §3.5–§3.6, §4, §5.6, §8.3.

The broker is the truth (design §5.3); these rows are the **record**. Every
broker identity (order ticket, deal ticket, ``position_id``) is qualified by the
account (``account_hash``), because a ticket is only unique inside one account
(§1.1). Times keep the broker's raw ``time_msc`` next to the derived UTC instant
(design §7.4). Machine C (``b3_positions``) is keyed on ``position_id``, never
on the ticket, which can change (I-SL-4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import JSONB_EMPTY_LIST, org_fk, pg_enum
from hunter_core.db.models.b3_robot import account_fk, instance_fk
from hunter_core.domain.b3_enums import (
    B3Attribution,
    B3CloseCause,
    B3DegradedReason,
    B3ExitReason,
    B3PositionState,
    B3SltpSlot,
)
from hunter_core.domain.enums import OrderSide

MANAGED = "('unprotected', 'protected', 'degraded', 'exiting', 'exit_overdue')"
"""§4.1: the states of a position the robot manages — only an attributed one."""


class B3Order(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """``b3_orders`` — a broker order of the robot, by ticket (§3.5–§3.6)."""

    __tablename__ = "b3_orders"
    __table_args__ = (
        org_fk(),
        account_fk(),
        ForeignKeyConstraint(
            ["organization_id", "account_hash", "proposal_id"],
            [
                "b3_entry_intents.organization_id",
                "b3_entry_intents.account_hash",
                "b3_entry_intents.proposal_id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "account_hash", "ticket", name="uq_b3_orders_ticket"),
        Index("ix_b3_orders_proposal", "organization_id", "account_hash", "proposal_id"),
        CheckConstraint("volume_initial > 0", name="volume_is_positive"),
        CheckConstraint(
            "volume_current >= 0 AND volume_current <= volume_initial", name="volume_current_bounds"
        ),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    proposal_id: Mapped[uuid.UUID | None]
    ticket: Mapped[int] = mapped_column(BigInteger)
    symbol: Mapped[str] = mapped_column(Text)
    side: Mapped[OrderSide] = mapped_column(pg_enum("order_side"))
    order_type: Mapped[str] = mapped_column(Text)
    volume_initial: Mapped[Decimal]
    volume_current: Mapped[Decimal]
    price: Mapped[Decimal | None]
    sl: Mapped[Decimal | None]
    tp: Mapped[Decimal | None]
    magic: Mapped[int] = mapped_column(BigInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    last_retcode: Mapped[str | None] = mapped_column(Text)
    setup_time_msc: Mapped[int | None] = mapped_column(BigInteger)
    done_time_msc: Mapped[int | None] = mapped_column(BigInteger)
    observed_at: Mapped[datetime]


class B3Deal(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_deals`` — one broker deal, entered once by its ticket (§8.3), append-only.

    ``commission``/``fee`` keep the broker's sign: §8.3 charges
    ``max(modelled, |commission| + |fee|)``, so a negative commission is recorded
    as it came and never becomes a gain downstream.
    """

    __tablename__ = "b3_deals"
    __table_args__ = (
        org_fk(),
        account_fk(),
        UniqueConstraint(
            "organization_id", "account_hash", "deal_ticket", name="uq_b3_deals_ticket"
        ),
        Index("ix_b3_deals_position", "organization_id", "account_hash", "position_id"),
        Index("ix_b3_deals_org_time", "organization_id", "deal_time"),
        CheckConstraint("volume > 0", name="volume_is_positive"),
        CheckConstraint("price > 0", name="price_is_positive"),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    deal_ticket: Mapped[int] = mapped_column(BigInteger)
    order_ticket: Mapped[int | None] = mapped_column(BigInteger)
    position_id: Mapped[int] = mapped_column(BigInteger)
    symbol: Mapped[str] = mapped_column(Text)
    side: Mapped[OrderSide] = mapped_column(pg_enum("order_side"))
    entry: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    volume: Mapped[Decimal]
    price: Mapped[Decimal]
    commission: Mapped[Decimal]
    fee: Mapped[Decimal]
    swap: Mapped[Decimal]
    profit: Mapped[Decimal]
    magic: Mapped[int] = mapped_column(BigInteger)
    comment: Mapped[str | None] = mapped_column(Text)
    time_msc: Mapped[int] = mapped_column(BigInteger)
    deal_time: Mapped[datetime]
    observed_at: Mapped[datetime] = mapped_column(server_default=func.now())


class B3Position(Base, UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin):
    """``b3_positions`` — machine C (§4), one per ``position_id`` of the account.

    The SLTP slot is **the position's** and crosses instances (§4.3): a grant
    never resets it. ``closed`` is terminal and an exit, once started, only ends
    in ``closed`` (I-X-3) or leaves management as ``unattributed`` — both held by
    a trigger of ``0071``.
    """

    __tablename__ = "b3_positions"
    __table_args__ = (
        org_fk(),
        account_fk(),
        UniqueConstraint(
            "organization_id", "account_hash", "position_id", name="uq_b3_positions_position"
        ),
        Index(
            "ix_b3_positions_open",
            "organization_id",
            "account_hash",
            postgresql_where=text("state <> 'closed'"),
        ),
        CheckConstraint("volume >= 0", name="volume_is_not_negative"),
        CheckConstraint("price_open > 0", name="price_open_is_positive"),
        CheckConstraint(
            "(state = 'degraded') = (degraded_reason IS NOT NULL)", name="degraded_iff_reason"
        ),
        CheckConstraint(
            "(state = 'closed') = (close_cause IS NOT NULL) "
            "AND (state = 'closed') = (closed_at IS NOT NULL)",
            name="closed_is_whole",
        ),
        CheckConstraint(
            "state NOT IN ('exiting', 'exit_overdue') OR exit_reason IS NOT NULL",
            name="an_exit_has_a_reason",
        ),
        CheckConstraint(
            f"state NOT IN {MANAGED} OR attribution = 'attributed'",
            name="only_attributed_is_managed",
        ),
        CheckConstraint(
            "state <> 'unattributed' OR attribution <> 'attributed'",
            name="unattributed_is_not_attributed",
        ),
        CheckConstraint(
            "(sl_confirmed IS NULL OR sl_confirmed > 0) AND (floor_sl IS NULL OR floor_sl > 0)",
            name="stops_are_positive",
        ),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    position_id: Mapped[int] = mapped_column(BigInteger)
    position_ticket: Mapped[int] = mapped_column(BigInteger)
    symbol: Mapped[str] = mapped_column(Text)
    side: Mapped[OrderSide] = mapped_column(pg_enum("order_side"))
    volume: Mapped[Decimal]
    price_open: Mapped[Decimal]
    state: Mapped[B3PositionState] = mapped_column(pg_enum("b3_position_state"))
    degraded_reason: Mapped[B3DegradedReason | None] = mapped_column(pg_enum("b3_degraded_reason"))
    sltp_slot: Mapped[B3SltpSlot] = mapped_column(
        pg_enum("b3_sltp_slot"), server_default=B3SltpSlot.IDLE.value
    )
    attribution: Mapped[B3Attribution] = mapped_column(pg_enum("b3_attribution"))
    sl_confirmed: Mapped[Decimal | None]
    tp_confirmed: Mapped[Decimal | None]
    floor_sl: Mapped[Decimal | None]
    first_deal_time_msc: Mapped[int | None] = mapped_column(BigInteger)
    exit_reason: Mapped[B3ExitReason | None] = mapped_column(pg_enum("b3_exit_reason"))
    exit_intended_at: Mapped[datetime | None]
    exit_effective_at: Mapped[datetime | None]
    exit_effective_price: Mapped[Decimal | None]
    close_cause: Mapped[B3CloseCause | None] = mapped_column(pg_enum("b3_close_cause"))
    closed_at: Mapped[datetime | None]


class B3Reconciliation(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_reconciliations`` — one pass of design §5.3, append-only.

    Audited only when it is not clean (design §7.1 lists "divergência de
    reconciliação", not every 5 s pass).
    """

    __tablename__ = "b3_reconciliations"
    __table_args__ = (
        org_fk(),
        account_fk(),
        instance_fk(),
        Index(
            "ix_b3_reconciliations_account_at", "organization_id", "account_hash", "reconciled_at"
        ),
        Index("ix_b3_reconciliations_instance", "organization_id", "instance_id"),
        CheckConstraint("consistent_passes >= 0", name="passes_not_negative"),
        CheckConstraint("jsonb_typeof(divergences) = 'array'", name="divergences_is_an_array"),
        CheckConstraint(
            "clean = (jsonb_array_length(divergences) = 0)", name="clean_iff_no_divergence"
        ),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    instance_id: Mapped[uuid.UUID]
    reconciled_at: Mapped[datetime]
    clean: Mapped[bool]
    consistent_passes: Mapped[int]
    divergences: Mapped[list[Any]] = mapped_column(JSONB, server_default=JSONB_EMPTY_LIST)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class B3SessionAnchor(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_session_anchors`` — the day's equity anchor (§8.1 ``day.anchor_*``).

    Written once per account and session, append-only: a restart after a loss
    reads the anchor back instead of re-anchoring below it (Astra, R3 design
    review); without a row check 14 is ``unavailable`` (``day_anchor_missing``).
    """

    __tablename__ = "b3_session_anchors"
    __table_args__ = (
        org_fk(),
        account_fk(),
        UniqueConstraint(
            "organization_id", "account_hash", "session_date", name="uq_b3_session_anchors_day"
        ),
        CheckConstraint("anchor_equity >= 0", name="anchor_is_not_negative"),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    session_date: Mapped[date]
    anchor_equity: Mapped[Decimal]
    anchor_at: Mapped[datetime]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
