"""The B3 robot's configuration — DATABASE.md §74, ``docs/RISK_ENGINE_B3.md`` §8–§9.

Everything here is **data the Everton edits through the API** (OWNER + step-up is
checked in the API, R4): the versioned limits, the session grids with their
validity, the holidays, the current contracts, the cost table, the spec pinned
at arming and the magic of each strategy version. All tenant tables
(``organization_id``, RLS forced, ``tenant_isolation``), and no row is ever
deleted: a change is a new row and the old one is retired (``superseded_at`` /
``retired_at``), so a decision can always name the version it used.

The robot's own state is in :mod:`hunter_core.db.models.b3_robot`, the entry
chain in :mod:`.b3_entries` and what the broker shows in :mod:`.b3_broker`.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, UUIDPrimaryKeyMixin
from hunter_core.db.models._common import SQL_FALSE, org_fk

NO_JSON_NUMBER = """NOT jsonb_path_exists(limits, 'strict $.** ? (@.type() == "number")')"""
"""§9: "todo número como string decimal no JSON (número JSON recusado)" — anywhere
in the document, nested ``fee_schedule`` included."""


def hex64(column: str) -> CheckConstraint:
    """``account_hash``/``host_hash`` are lowercase hex sha256 (§1.1), never a login."""
    return CheckConstraint(f"{column} ~ '^[0-9a-f]{{64}}$'", name=f"{column}_is_sha256_hex")


def _retired_once(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} IS NULL OR {column} >= created_at", name=f"{column}_after")


class B3RiskProfile(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_risk_profiles`` — the limits of §9 as data, one version per row.

    ``limits_version`` is contiguous per organization (a trigger), at most one row
    is current (``superseded_at IS NULL``), and a row is immutable except for
    being superseded once — the claim (§3.3) compares the version a decision used
    with the current one.
    """

    __tablename__ = "b3_risk_profiles"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("organization_id", "limits_version", name="uq_b3_risk_profiles_version"),
        Index(
            "uq_b3_risk_profiles_current",
            "organization_id",
            unique=True,
            postgresql_where=text("superseded_at IS NULL"),
        ),
        CheckConstraint("limits_version >= 1", name="version_is_positive"),
        CheckConstraint("jsonb_typeof(limits) = 'object'", name="limits_is_an_object"),
        CheckConstraint(NO_JSON_NUMBER, name="limits_has_no_json_number"),
        _retired_once("superseded_at"),
    )

    limits_version: Mapped[int]
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    superseded_at: Mapped[datetime | None]


class B3SessionGrid(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_session_grids`` — B3's trading hours, Brasília wall clock, with validity.

    Times are ``TIME`` in ``America/Sao_Paulo`` (a recurring schedule is not an
    instant; the robot converts per date with ``zoneinfo``, design §7.4 — the
    declared deviation from "TIMESTAMPTZ always"). ``special_day`` is a one-day
    grid (a shortened session) that wins over the regular one on that date; two
    current grids of the same kind may not overlap (a trigger).
    """

    __tablename__ = "b3_session_grids"
    __table_args__ = (
        org_fk(),
        UniqueConstraint(
            "organization_id", "symbol_root", "grid_version", name="uq_b3_session_grids_version"
        ),
        Index("ix_b3_session_grids_lookup", "organization_id", "symbol_root", "valid_from"),
        CheckConstraint("grid_version >= 1", name="version_is_positive"),
        CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="validity_order"),
        CheckConstraint(
            "NOT special_day OR valid_until = valid_from", name="special_day_is_one_day"
        ),
        CheckConstraint("open_local < close_local", name="opens_before_it_closes"),
        CheckConstraint("close_local <= session_end_local", name="closes_before_it_ends"),
        CheckConstraint("length(btrim(source_note)) > 0", name="source_note_present"),
        _retired_once("retired_at"),
    )

    symbol_root: Mapped[str] = mapped_column(Text)
    grid_version: Mapped[int]
    valid_from: Mapped[date]
    valid_until: Mapped[date | None]
    special_day: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    open_local: Mapped[time]
    close_local: Mapped[time]
    session_end_local: Mapped[time]
    source_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    retired_at: Mapped[datetime | None]


class B3Holiday(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_holidays`` — a closed day, or a shortened one (which needs its own grid)."""

    __tablename__ = "b3_holidays"
    __table_args__ = (
        org_fk(),
        Index(
            "uq_b3_holidays_current",
            "organization_id",
            "holiday_date",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
        ),
        CheckConstraint("length(btrim(source_note)) > 0", name="source_note_present"),
        _retired_once("retired_at"),
    )

    holiday_date: Mapped[date]
    is_shortened: Mapped[bool] = mapped_column(server_default=SQL_FALSE)
    source_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    retired_at: Mapped[datetime | None]


class B3Contract(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_contracts`` — which contract of a root is current, and until when (check 4)."""

    __tablename__ = "b3_contracts"
    __table_args__ = (
        org_fk(),
        Index("ix_b3_contracts_lookup", "organization_id", "root", "valid_from"),
        CheckConstraint("valid_until >= valid_from", name="validity_order"),
        CheckConstraint("valid_until <= expiry_date", name="current_until_expiry_at_most"),
        CheckConstraint("length(btrim(source_note)) > 0", name="source_note_present"),
        _retired_once("retired_at"),
    )

    symbol: Mapped[str] = mapped_column(Text)
    root: Mapped[str] = mapped_column(Text)
    expiry_date: Mapped[date]
    valid_from: Mapped[date]
    valid_until: Mapped[date]
    source_note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    retired_at: Mapped[datetime | None]


class B3FeeSchedule(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_fee_schedules`` — the cost per leg with its source and date (KB-0149 §1).

    Without a current row the robot does not arm (``fee_schedule_missing``, §0).
    """

    __tablename__ = "b3_fee_schedules"
    __table_args__ = (
        org_fk(),
        Index("ix_b3_fee_schedules_lookup", "organization_id", "symbol_root", "valid_from"),
        CheckConstraint("per_leg_brl >= 0", name="fee_is_not_negative"),
        CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="validity_order"),
        CheckConstraint("length(btrim(source)) > 0", name="source_present"),
        _retired_once("retired_at"),
    )

    symbol_root: Mapped[str] = mapped_column(Text)
    per_leg_brl: Mapped[Decimal]
    valid_from: Mapped[date]
    valid_until: Mapped[date | None]
    source: Mapped[str] = mapped_column(Text)
    source_date: Mapped[date]
    conditions: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    retired_at: Mapped[datetime | None]


class B3SpecPin(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_spec_pins`` — the ``SpecPin`` fixed at arming (§8.1), with the evidence
    of T8/T13/T14 behind its three proofs. Append-only."""

    __tablename__ = "b3_spec_pins"
    __table_args__ = (
        org_fk(),
        ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "account_hash", "id", name="uq_b3_spec_pins_account"),
        Index("ix_b3_spec_pins_account_pinned", "organization_id", "account_hash", "pinned_at"),
        CheckConstraint(
            "trade_tick_size > 0 AND trade_tick_value > 0 AND point > 0", name="tick_is_positive"
        ),
        CheckConstraint(
            "volume_min > 0 AND volume_step > 0 AND volume_max >= volume_min",
            name="volume_bounds",
        ),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="evidence_is_an_object"),
        hex64("account_hash"),
    )

    account_hash: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str] = mapped_column(Text)
    trade_tick_size: Mapped[Decimal]
    trade_tick_value: Mapped[Decimal]
    point: Mapped[Decimal]
    digits: Mapped[int] = mapped_column(SmallInteger)
    volume_min: Mapped[Decimal]
    volume_step: Mapped[Decimal]
    volume_max: Mapped[Decimal]
    trade_mode: Mapped[str] = mapped_column(Text)
    filling_mode: Mapped[str] = mapped_column(Text)
    expiration_mode: Mapped[str] = mapped_column(Text)
    account_margin_mode: Mapped[str] = mapped_column(Text)
    terminal_version: Mapped[str] = mapped_column(Text)
    package_version: Mapped[str] = mapped_column(Text)
    order_lifecycle_proven: Mapped[bool]
    comment_preserved: Mapped[bool]
    stale_ticket_rejection_proven: Mapped[bool]
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB)
    pinned_at: Mapped[datetime] = mapped_column(server_default=func.now())


class B3StrategyMagic(Base, UUIDPrimaryKeyMixin, TenantMixin):
    """``b3_strategy_magics`` — ``(strategy_key, strategy_version) → magic`` (§1.1).

    Unique per organization and **never reused**: append-only, so a magic once
    given stays in ``robot_magics`` for the attribution (§4.5) for ever.
    """

    __tablename__ = "b3_strategy_magics"
    __table_args__ = (
        org_fk(),
        UniqueConstraint("organization_id", "magic", name="uq_b3_strategy_magics_magic"),
        UniqueConstraint(
            "organization_id",
            "strategy_key",
            "strategy_version",
            name="uq_b3_strategy_magics_strategy",
        ),
        CheckConstraint("magic > 0", name="magic_is_positive"),
    )

    strategy_key: Mapped[str] = mapped_column(Text)
    strategy_version: Mapped[int]
    magic: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
