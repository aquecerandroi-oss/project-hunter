"""b3 robot: the schema of Everton's MT5 robot at Rico (R3)

Revision ID: 0071_b3_robot
Revises: 0069_meme_absorb_semdump_arm

Task R3 of ``docs/design/robo-b3-mt5.md`` §9, against the frozen contract
``docs/RISK_ENGINE_B3.md`` v1.0 (commit ``5e71f345``). Described in DATABASE.md §74.

In the order Postgres accepts it:

1. the thirteen ``b3_*`` enum types of the contract's §1.2, verbatim
   (``ddl/enums.py`` ``B3_ENUMS``); ``b3_kill_state`` reuses ``kill_switch_state``
   ("mesmo enum do SPOT") and the side reuses ``order_side``;
2. ``b3_client_order_id(uuid)``, the §1.1 formula as an ``IMMUTABLE`` SQL function,
   so ``b3_entry_intents.client_order_id`` is a stored generated column (I-E-4);
3. the twenty-four tenant tables (models in ``hunter_core/db/models/b3*.py``);
4. RLS enabled, forced and ``tenant_isolation`` on every one; grants in three
   classes, no ``DELETE`` for anyone (``ddl/b3_robot.py``);
5. the shared triggers — never deleted, append-only, retire-only, audited at
   COMMIT — and the state-machine guards (``ddl/b3_robot_guards.py``).

**Numbering.** ``0070_meme_mature_chart_arms`` exists uncommitted in the tree and
is HELD (EXP-M26, DATABASE.md §69/§72); this revision does not depend on it and
takes the next free number. Both descend from ``0069``: with the held file
present the tree has two heads until the orchestrator re-chains the seed on top
of this revision (the §72 precedent), and ``upgrade head`` is ambiguous there.

Nothing depends on session state: no session-level prepared statement, no
``LISTEN``/``NOTIFY``, no session advisory lock (the guards' advisory locks are
``pg_advisory_xact_lock``). The downgrade refuses while any ``b3_*`` row exists.
The slug is 13 characters (§17.6).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ddl.b3_robot import (
    create_client_order_id_function,
    create_shared_triggers,
    drop_client_order_id_function,
    drop_shared_functions,
    enable_b3_row_level_security,
    grant_b3_privileges,
    refuse_a_populated_downgrade,
)
from ddl.b3_robot_guards import create_b3_guards, drop_b3_guard_functions
from ddl.enums import B3_ENUMS, create_enum_types, drop_enum_types
from sqlalchemy.dialects import postgresql

revision: str = "0071_b3_robot"
down_revision: str | None = "0069_meme_absorb_semdump_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_enum_types(B3_ENUMS)
    create_client_order_id_function()
    _create_tables()
    enable_b3_row_level_security()
    grant_b3_privileges()
    create_shared_triggers()
    create_b3_guards()


def downgrade() -> None:
    refuse_a_populated_downgrade()
    _drop_tables()
    drop_b3_guard_functions()
    drop_shared_functions()
    drop_client_order_id_function()
    drop_enum_types(B3_ENUMS)


def _create_tables() -> None:
    op.create_table(
        "b3_contracts",
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("root", sa.Text(), nullable=False),
        sa.Column("expiry_date", sa.Date(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(source_note)) > 0", name=op.f("ck_b3_contracts_source_note_present")
        ),
        sa.CheckConstraint(
            "retired_at IS NULL OR retired_at >= created_at",
            name=op.f("ck_b3_contracts_retired_at_after"),
        ),
        sa.CheckConstraint(
            "valid_until <= expiry_date", name=op.f("ck_b3_contracts_current_until_expiry_at_most")
        ),
        sa.CheckConstraint(
            "valid_until >= valid_from", name=op.f("ck_b3_contracts_validity_order")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_contracts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_contracts")),
    )
    op.create_index(
        "ix_b3_contracts_lookup",
        "b3_contracts",
        ["organization_id", "root", "valid_from"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_contracts_organization_id"), "b3_contracts", ["organization_id"], unique=False
    )
    op.create_table(
        "b3_fee_schedules",
        sa.Column("symbol_root", sa.Text(), nullable=False),
        sa.Column("per_leg_brl", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_date", sa.Date(), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(source)) > 0", name=op.f("ck_b3_fee_schedules_source_present")
        ),
        sa.CheckConstraint(
            "per_leg_brl >= 0", name=op.f("ck_b3_fee_schedules_fee_is_not_negative")
        ),
        sa.CheckConstraint(
            "retired_at IS NULL OR retired_at >= created_at",
            name=op.f("ck_b3_fee_schedules_retired_at_after"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name=op.f("ck_b3_fee_schedules_validity_order"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_fee_schedules_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_fee_schedules")),
    )
    op.create_index(
        "ix_b3_fee_schedules_lookup",
        "b3_fee_schedules",
        ["organization_id", "symbol_root", "valid_from"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_fee_schedules_organization_id"),
        "b3_fee_schedules",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_holidays",
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("is_shortened", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "length(btrim(source_note)) > 0", name=op.f("ck_b3_holidays_source_note_present")
        ),
        sa.CheckConstraint(
            "retired_at IS NULL OR retired_at >= created_at",
            name=op.f("ck_b3_holidays_retired_at_after"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_holidays_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_holidays")),
    )
    op.create_index(
        op.f("ix_b3_holidays_organization_id"), "b3_holidays", ["organization_id"], unique=False
    )
    op.create_index(
        "uq_b3_holidays_current",
        "b3_holidays",
        ["organization_id", "holiday_date"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.create_table(
        "b3_risk_profiles",
        sa.Column("limits_version", sa.Integer(), nullable=False),
        sa.Column("limits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(limits) = 'object'", name=op.f("ck_b3_risk_profiles_limits_is_an_object")
        ),
        sa.CheckConstraint(
            "NOT jsonb_path_exists(limits, 'strict $.** ? (@.type() == \"number\")')",
            name=op.f("ck_b3_risk_profiles_limits_has_no_json_number"),
        ),
        sa.CheckConstraint(
            "limits_version >= 1", name=op.f("ck_b3_risk_profiles_version_is_positive")
        ),
        sa.CheckConstraint(
            "superseded_at IS NULL OR superseded_at >= created_at",
            name=op.f("ck_b3_risk_profiles_superseded_at_after"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_risk_profiles_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_risk_profiles")),
        sa.UniqueConstraint(
            "organization_id", "limits_version", name="uq_b3_risk_profiles_version"
        ),
    )
    op.create_index(
        op.f("ix_b3_risk_profiles_organization_id"),
        "b3_risk_profiles",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_b3_risk_profiles_current",
        "b3_risk_profiles",
        ["organization_id"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "b3_robot_accounts",
        sa.Column("registered_account_hash", sa.Text(), nullable=False),
        sa.Column("authorized_host_hash", sa.Text(), nullable=False),
        sa.Column(
            "kill_state",
            postgresql.ENUM(
                "ACTIVE",
                "WARNING",
                "TRADING_DISABLED",
                "EMERGENCY",
                name="kill_switch_state",
                create_type=False,
            ),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column(
            "active_causes",
            postgresql.ARRAY(
                postgresql.ENUM(
                    "daily_loss_limit",
                    "broker_reject_breaker",
                    "reversal_detected",
                    "manual_route",
                    "agent_command",
                    "owner_command",
                    "owner_button",
                    name="b3_kill_cause",
                    create_type=False,
                )
            ),
            server_default=sa.text("'{}'::b3_kill_cause[]"),
            nullable=False,
        ),
        sa.Column("kill_changed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(kill_state IN ('TRADING_DISABLED', 'EMERGENCY')) = (cardinality(active_causes) > 0)",
            name=op.f("ck_b3_robot_accounts_latched_iff_a_cause_holds"),
        ),
        sa.CheckConstraint(
            "authorized_host_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_robot_accounts_authorized_host_hash_is_sha256_hex"),
        ),
        sa.CheckConstraint(
            "registered_account_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_robot_accounts_registered_account_hash_is_sha256_hex"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_robot_accounts_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_robot_accounts")),
        sa.UniqueConstraint(
            "organization_id", "registered_account_hash", name="uq_b3_robot_accounts_account"
        ),
    )
    op.create_index(
        op.f("ix_b3_robot_accounts_organization_id"),
        "b3_robot_accounts",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_robot_instances",
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("host_hash", sa.Text(), nullable=False),
        sa.Column("account_hash_seen", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "account_hash_seen ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_robot_instances_account_hash_seen_is_sha256_hex"),
        ),
        sa.CheckConstraint(
            "host_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_robot_instances_host_hash_is_sha256_hex"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_robot_instances_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instance_id", name=op.f("pk_b3_robot_instances")),
        sa.UniqueConstraint("organization_id", "instance_id", name="uq_b3_robot_instances_org"),
    )
    op.create_index(
        "ix_b3_robot_instances_org_started",
        "b3_robot_instances",
        ["organization_id", "started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_robot_instances_organization_id"),
        "b3_robot_instances",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_session_grids",
        sa.Column("symbol_root", sa.Text(), nullable=False),
        sa.Column("grid_version", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("special_day", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("open_local", sa.Time(), nullable=False),
        sa.Column("close_local", sa.Time(), nullable=False),
        sa.Column("session_end_local", sa.Time(), nullable=False),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("retired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "NOT special_day OR valid_until = valid_from",
            name=op.f("ck_b3_session_grids_special_day_is_one_day"),
        ),
        sa.CheckConstraint(
            "close_local <= session_end_local",
            name=op.f("ck_b3_session_grids_closes_before_it_ends"),
        ),
        sa.CheckConstraint(
            "grid_version >= 1", name=op.f("ck_b3_session_grids_version_is_positive")
        ),
        sa.CheckConstraint(
            "length(btrim(source_note)) > 0", name=op.f("ck_b3_session_grids_source_note_present")
        ),
        sa.CheckConstraint(
            "open_local < close_local", name=op.f("ck_b3_session_grids_opens_before_it_closes")
        ),
        sa.CheckConstraint(
            "retired_at IS NULL OR retired_at >= created_at",
            name=op.f("ck_b3_session_grids_retired_at_after"),
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name=op.f("ck_b3_session_grids_validity_order"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_session_grids_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_session_grids")),
        sa.UniqueConstraint(
            "organization_id", "symbol_root", "grid_version", name="uq_b3_session_grids_version"
        ),
    )
    op.create_index(
        "ix_b3_session_grids_lookup",
        "b3_session_grids",
        ["organization_id", "symbol_root", "valid_from"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_session_grids_organization_id"),
        "b3_session_grids",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_strategy_magics",
        sa.Column("strategy_key", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("magic", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("magic > 0", name=op.f("ck_b3_strategy_magics_magic_is_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_strategy_magics_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_strategy_magics")),
        sa.UniqueConstraint("organization_id", "magic", name="uq_b3_strategy_magics_magic"),
        sa.UniqueConstraint(
            "organization_id",
            "strategy_key",
            "strategy_version",
            name="uq_b3_strategy_magics_strategy",
        ),
    )
    op.create_index(
        op.f("ix_b3_strategy_magics_organization_id"),
        "b3_strategy_magics",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_bracket_learning",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("k", sa.SmallInteger(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("k >= 0", name=op.f("ck_b3_bracket_learning_k_not_negative")),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_bracket_learning_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_bracket_learning_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_bracket_learning")),
        sa.UniqueConstraint(
            "organization_id",
            "account_hash",
            "session_date",
            "symbol",
            name="uq_b3_bracket_learning_session",
        ),
    )
    op.create_index(
        op.f("ix_b3_bracket_learning_organization_id"),
        "b3_bracket_learning",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_deals",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("deal_ticket", sa.BigInteger(), nullable=False),
        sa.Column("order_ticket", sa.BigInteger(), nullable=True),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column(
            "side",
            postgresql.ENUM("buy", "sell", name="order_side", create_type=False),
            nullable=False,
        ),
        sa.Column("entry", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("volume", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("commission", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("fee", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("swap", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("profit", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("magic", sa.BigInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("time_msc", sa.BigInteger(), nullable=False),
        sa.Column("deal_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "observed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("price > 0", name=op.f("ck_b3_deals_price_is_positive")),
        sa.CheckConstraint("volume > 0", name=op.f("ck_b3_deals_volume_is_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_deals_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_deals_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_deals")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "deal_ticket", name="uq_b3_deals_ticket"
        ),
    )
    op.create_index(
        "ix_b3_deals_org_time", "b3_deals", ["organization_id", "deal_time"], unique=False
    )
    op.create_index(
        op.f("ix_b3_deals_organization_id"), "b3_deals", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_b3_deals_position",
        "b3_deals",
        ["organization_id", "account_hash", "position_id"],
        unique=False,
    )
    op.create_table(
        "b3_entry_proposals",
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("strategy_key", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("params_hash", sa.Text(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("window_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column(
            "side",
            postgresql.ENUM("buy", "sell", name="order_side", create_type=False),
            nullable=False,
        ),
        sa.Column("requested_contracts", sa.Integer(), nullable=False),
        sa.Column("ref_price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("stop_price", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("exit_at_utc", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("signal_published_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("signal_deadline_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("entry_window_start_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("entry_window_end_utc", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "entry_window_start_utc <= entry_window_end_utc",
            name=op.f("ck_b3_entry_proposals_entry_window_order"),
        ),
        sa.CheckConstraint(
            "ref_price > 0 AND stop_price > 0",
            name=op.f("ck_b3_entry_proposals_prices_are_positive"),
        ),
        sa.CheckConstraint(
            "requested_contracts >= 1",
            name=op.f("ck_b3_entry_proposals_requested_contracts_positive"),
        ),
        sa.CheckConstraint(
            "target_price IS NULL OR target_price > 0",
            name=op.f("ck_b3_entry_proposals_target_is_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_entry_proposals_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "instance_id"],
            ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
            name=op.f("fk_b3_entry_proposals_organization_id_b3_robot_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_entry_proposals_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("proposal_id", name=op.f("pk_b3_entry_proposals")),
        sa.UniqueConstraint(
            "organization_id",
            "proposal_id",
            "instance_id",
            "account_hash",
            name="uq_b3_entry_proposals_identity",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "strategy_key",
            "strategy_version",
            "session_date",
            "window_id",
            name="uq_b3_entry_proposals_window",
        ),
    )
    op.create_index(
        "ix_b3_entry_proposals_account",
        "b3_entry_proposals",
        ["organization_id", "account_hash", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_b3_entry_proposals_instance",
        "b3_entry_proposals",
        ["organization_id", "instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_entry_proposals_organization_id"),
        "b3_entry_proposals",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_b3_entry_proposals_session",
        "b3_entry_proposals",
        ["organization_id", "session_date"],
        unique=False,
    )
    op.create_table(
        "b3_kill_switch_transitions",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column(
            "from_state",
            postgresql.ENUM(
                "ACTIVE",
                "WARNING",
                "TRADING_DISABLED",
                "EMERGENCY",
                name="kill_switch_state",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "to_state",
            postgresql.ENUM(
                "ACTIVE",
                "WARNING",
                "TRADING_DISABLED",
                "EMERGENCY",
                name="kill_switch_state",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "from_causes",
            postgresql.ARRAY(
                postgresql.ENUM(
                    "daily_loss_limit",
                    "broker_reject_breaker",
                    "reversal_detected",
                    "manual_route",
                    "agent_command",
                    "owner_command",
                    "owner_button",
                    name="b3_kill_cause",
                    create_type=False,
                )
            ),
            nullable=False,
        ),
        sa.Column(
            "causes_after",
            postgresql.ARRAY(
                postgresql.ENUM(
                    "daily_loss_limit",
                    "broker_reject_breaker",
                    "reversal_detected",
                    "manual_route",
                    "agent_command",
                    "owner_command",
                    "owner_button",
                    name="b3_kill_cause",
                    create_type=False,
                )
            ),
            nullable=False,
        ),
        sa.Column(
            "cause",
            postgresql.ENUM(
                "daily_loss_limit",
                "broker_reject_breaker",
                "reversal_detected",
                "manual_route",
                "agent_command",
                "owner_command",
                "owner_button",
                name="b3_kill_cause",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "changed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(to_state IN ('TRADING_DISABLED', 'EMERGENCY')) = (cardinality(causes_after) > 0)",
            name=op.f("ck_b3_kill_switch_transitions_latched_iff_a_cause_holds"),
        ),
        sa.CheckConstraint(
            "actor_type <> 'agent' OR (to_state = 'TRADING_DISABLED' AND from_state < 'TRADING_DISABLED' AND cause = 'agent_command')",
            name=op.f("ck_b3_kill_switch_transitions_an_agent_only_disables"),
        ),
        sa.CheckConstraint(
            "actor_type = 'user' OR NOT (from_state = 'EMERGENCY' AND to_state <> 'EMERGENCY')",
            name=op.f("ck_b3_kill_switch_transitions_only_the_owner_leaves_emergency"),
        ),
        sa.CheckConstraint(
            "actor_type = 'user' OR from_causes <@ (causes_after || ARRAY['daily_loss_limit']::b3_kill_cause[])",
            name=op.f("ck_b3_kill_switch_transitions_only_the_owner_releases_a_latch"),
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'agent', 'robot', 'system')",
            name=op.f("ck_b3_kill_switch_transitions_actor_type_is_known"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'object'",
            name=op.f("ck_b3_kill_switch_transitions_evidence_is_an_object"),
        ),
        sa.CheckConstraint(
            "from_state <> to_state OR from_causes IS DISTINCT FROM causes_after",
            name=op.f("ck_b3_kill_switch_transitions_a_transition_moves"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_kill_switch_transitions_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_kill_switch_transitions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_kill_switch_transitions")),
    )
    op.create_index(
        "ix_b3_kill_switch_transitions_account_changed",
        "b3_kill_switch_transitions",
        ["organization_id", "account_hash", "changed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_kill_switch_transitions_organization_id"),
        "b3_kill_switch_transitions",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_management_epochs",
        sa.Column("epoch_id", sa.UUID(), nullable=False),
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("authority_id", sa.UUID(), nullable=False),
        sa.Column("host_hash", sa.Text(), nullable=False),
        sa.Column(
            "opened_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closed_clean", sa.Boolean(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "host_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_management_epochs_host_hash_is_sha256_hex"),
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL) = (closed_clean IS NULL)",
            name=op.f("ck_b3_management_epochs_closed_is_whole"),
        ),
        sa.CheckConstraint(
            "closed_at IS NULL OR closed_at >= opened_at",
            name=op.f("ck_b3_management_epochs_closes_after_open"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_management_epochs_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "instance_id"],
            ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
            name=op.f("fk_b3_management_epochs_organization_id_b3_robot_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_management_epochs_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("epoch_id", name=op.f("pk_b3_management_epochs")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "epoch_id", name="uq_b3_management_epochs_account"
        ),
    )
    op.create_index(
        "ix_b3_management_epochs_account",
        "b3_management_epochs",
        ["organization_id", "account_hash", "opened_at"],
        unique=False,
    )
    op.create_index(
        "ix_b3_management_epochs_instance",
        "b3_management_epochs",
        ["organization_id", "instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_management_epochs_organization_id"),
        "b3_management_epochs",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "uq_b3_management_epochs_open",
        "b3_management_epochs",
        ["organization_id", "account_hash"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.create_table(
        "b3_positions",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("position_ticket", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column(
            "side",
            postgresql.ENUM("buy", "sell", name="order_side", create_type=False),
            nullable=False,
        ),
        sa.Column("volume", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("price_open", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(
                "unprotected",
                "protected",
                "degraded",
                "exiting",
                "exit_overdue",
                "closed",
                "unattributed",
                name="b3_position_state",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "degraded_reason",
            postgresql.ENUM(
                "naked_after_grace",
                "repair_rejected",
                "floor_unplaceable",
                "protection_unknown",
                name="b3_degraded_reason",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "sltp_slot",
            postgresql.ENUM("idle", "in_flight", "unknown", name="b3_sltp_slot", create_type=False),
            server_default="idle",
            nullable=False,
        ),
        sa.Column(
            "attribution",
            postgresql.ENUM(
                "attributed",
                "foreign",
                "ambiguous",
                "unreadable",
                name="b3_attribution",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("sl_confirmed", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("tp_confirmed", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("floor_sl", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("first_deal_time_msc", sa.BigInteger(), nullable=True),
        sa.Column(
            "exit_reason",
            postgresql.ENUM(
                "time_exit",
                "session_flatten",
                "emergency",
                "reversal",
                "overnight_carry",
                name="b3_exit_reason",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("exit_intended_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("exit_effective_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("exit_effective_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column(
            "close_cause",
            postgresql.ENUM(
                "server_sl",
                "server_tp",
                "bracket_sl",
                "bracket_tp",
                "manual",
                "broker_compulsory",
                "unexplained",
                name="b3_close_cause",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(state = 'closed') = (close_cause IS NOT NULL) AND (state = 'closed') = (closed_at IS NOT NULL)",
            name=op.f("ck_b3_positions_closed_is_whole"),
        ),
        sa.CheckConstraint(
            "(state = 'degraded') = (degraded_reason IS NOT NULL)",
            name=op.f("ck_b3_positions_degraded_iff_reason"),
        ),
        sa.CheckConstraint(
            "state <> 'unattributed' OR attribution <> 'attributed'",
            name=op.f("ck_b3_positions_unattributed_is_not_attributed"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('exiting', 'exit_overdue') OR exit_reason IS NOT NULL",
            name=op.f("ck_b3_positions_an_exit_has_a_reason"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('unprotected', 'protected', 'degraded', 'exiting', 'exit_overdue') OR attribution = 'attributed'",
            name=op.f("ck_b3_positions_only_attributed_is_managed"),
        ),
        sa.CheckConstraint(
            "(sl_confirmed IS NULL OR sl_confirmed > 0) AND (floor_sl IS NULL OR floor_sl > 0)",
            name=op.f("ck_b3_positions_stops_are_positive"),
        ),
        sa.CheckConstraint("price_open > 0", name=op.f("ck_b3_positions_price_open_is_positive")),
        sa.CheckConstraint("volume >= 0", name=op.f("ck_b3_positions_volume_is_not_negative")),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_positions_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_positions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_positions")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "position_id", name="uq_b3_positions_position"
        ),
    )
    op.create_index(
        "ix_b3_positions_open",
        "b3_positions",
        ["organization_id", "account_hash"],
        unique=False,
        postgresql_where=sa.text("state <> 'closed'"),
    )
    op.create_index(
        op.f("ix_b3_positions_organization_id"), "b3_positions", ["organization_id"], unique=False
    )
    op.create_table(
        "b3_reconciliations",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("reconciled_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("clean", sa.Boolean(), nullable=False),
        sa.Column("consistent_passes", sa.Integer(), nullable=False),
        sa.Column(
            "divergences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(divergences) = 'array'",
            name=op.f("ck_b3_reconciliations_divergences_is_an_array"),
        ),
        sa.CheckConstraint(
            "clean = (jsonb_array_length(divergences) = 0)",
            name=op.f("ck_b3_reconciliations_clean_iff_no_divergence"),
        ),
        sa.CheckConstraint(
            "consistent_passes >= 0", name=op.f("ck_b3_reconciliations_passes_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_reconciliations_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "instance_id"],
            ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
            name=op.f("fk_b3_reconciliations_organization_id_b3_robot_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_reconciliations_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_reconciliations")),
    )
    op.create_index(
        "ix_b3_reconciliations_account_at",
        "b3_reconciliations",
        ["organization_id", "account_hash", "reconciled_at"],
        unique=False,
    )
    op.create_index(
        "ix_b3_reconciliations_instance",
        "b3_reconciliations",
        ["organization_id", "instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_reconciliations_organization_id"),
        "b3_reconciliations",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_robot_events",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.Text(), nullable=False),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_robot_events_payload_sha256_is_hex"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_robot_events_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "instance_id"],
            ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
            name=op.f("fk_b3_robot_events_organization_id_b3_robot_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_robot_events_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_robot_events")),
        sa.UniqueConstraint("organization_id", "event_id", name="uq_b3_robot_events_event"),
    )
    op.create_index(
        "ix_b3_robot_events_account",
        "b3_robot_events",
        ["organization_id", "account_hash", "received_at"],
        unique=False,
    )
    op.create_index(
        "ix_b3_robot_events_instance",
        "b3_robot_events",
        ["organization_id", "instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_robot_events_organization_id"),
        "b3_robot_events",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_robot_heartbeats",
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name=op.f("ck_b3_robot_heartbeats_payload_is_an_object"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_robot_heartbeats_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "instance_id"],
            ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
            name=op.f("fk_b3_robot_heartbeats_organization_id_b3_robot_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_robot_heartbeats_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("instance_id", name=op.f("pk_b3_robot_heartbeats")),
    )
    op.create_index(
        "ix_b3_robot_heartbeats_account_as_of",
        "b3_robot_heartbeats",
        ["organization_id", "account_hash", "as_of"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_robot_heartbeats_organization_id"),
        "b3_robot_heartbeats",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_session_anchors",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("anchor_equity", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("anchor_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "anchor_equity >= 0", name=op.f("ck_b3_session_anchors_anchor_is_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_session_anchors_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_session_anchors_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_session_anchors")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "session_date", name="uq_b3_session_anchors_day"
        ),
    )
    op.create_index(
        op.f("ix_b3_session_anchors_organization_id"),
        "b3_session_anchors",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_spec_pins",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("trade_tick_size", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("trade_tick_value", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("point", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("digits", sa.SmallInteger(), nullable=False),
        sa.Column("volume_min", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("volume_step", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("volume_max", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("trade_mode", sa.Text(), nullable=False),
        sa.Column("filling_mode", sa.Text(), nullable=False),
        sa.Column("expiration_mode", sa.Text(), nullable=False),
        sa.Column("account_margin_mode", sa.Text(), nullable=False),
        sa.Column("terminal_version", sa.Text(), nullable=False),
        sa.Column("package_version", sa.Text(), nullable=False),
        sa.Column("order_lifecycle_proven", sa.Boolean(), nullable=False),
        sa.Column("comment_preserved", sa.Boolean(), nullable=False),
        sa.Column("stale_ticket_rejection_proven", sa.Boolean(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "pinned_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "account_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_spec_pins_account_hash_is_sha256_hex"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'object'", name=op.f("ck_b3_spec_pins_evidence_is_an_object")
        ),
        sa.CheckConstraint(
            "trade_tick_size > 0 AND trade_tick_value > 0 AND point > 0",
            name=op.f("ck_b3_spec_pins_tick_is_positive"),
        ),
        sa.CheckConstraint(
            "volume_min > 0 AND volume_step > 0 AND volume_max >= volume_min",
            name=op.f("ck_b3_spec_pins_volume_bounds"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_spec_pins_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_spec_pins_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_spec_pins")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "id", name="uq_b3_spec_pins_account"
        ),
    )
    op.create_index(
        "ix_b3_spec_pins_account_pinned",
        "b3_spec_pins",
        ["organization_id", "account_hash", "pinned_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_spec_pins_organization_id"), "b3_spec_pins", ["organization_id"], unique=False
    )
    op.create_table(
        "b3_entry_intents",
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "proposed",
                "rejected",
                "approved",
                "expired",
                "submitting",
                "aborted_before_send",
                "working",
                "partially_filled",
                "filled",
                "cancel_requested",
                "canceled",
                "broker_rejected",
                "unknown",
                "resolved_manual",
                name="b3_entry_intent_status",
                create_type=False,
            ),
            server_default="proposed",
            nullable=False,
        ),
        sa.Column("decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("limits_version", sa.Integer(), nullable=True),
        sa.Column("grid_version", sa.Integer(), nullable=True),
        sa.Column("spec_pin_id", sa.UUID(), nullable=True),
        sa.Column("n_final", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("limit_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("claimed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("claim_instance_id", sa.UUID(), nullable=True),
        sa.Column("claim_fencing_token", sa.BigInteger(), nullable=True),
        sa.Column("send_deadline_utc", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "client_order_id",
            sa.Text(),
            sa.Computed("b3_client_order_id(proposal_id)", persisted=True),
            nullable=False,
        ),
        sa.Column("broker_order_ticket", sa.BigInteger(), nullable=True),
        sa.Column("filled_volume", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column(
            "unknown_cause",
            postgresql.ENUM(
                "claim_ack_lost",
                "send_no_result",
                "send_timeout",
                "ipc_hang",
                "process_died",
                "cancel_no_result",
                "result_not_persisted",
                "journal_lost",
                "heartbeat_in_flight",
                name="b3_unknown_cause",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("terminal_reason", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(status = 'resolved_manual') = (resolved_at IS NOT NULL) AND (resolved_at IS NULL) = (resolved_by IS NULL) AND (resolved_at IS NULL OR (resolved_note IS NOT NULL AND length(btrim(resolved_note)) > 0))",
            name=op.f("ck_b3_entry_intents_manual_resolution_is_whole"),
        ),
        sa.CheckConstraint(
            "(status IN ('submitting', 'aborted_before_send', 'working', 'partially_filled', 'filled', 'cancel_requested', 'canceled', 'broker_rejected', 'unknown', 'resolved_manual')) = (claimed_at IS NOT NULL)",
            name=op.f("ck_b3_entry_intents_claimed_iff_post_claim"),
        ),
        sa.CheckConstraint(
            "approved_at IS NULL OR expires_at = approved_at + interval '30 seconds'",
            name=op.f("ck_b3_entry_intents_approval_lives_30_seconds"),
        ),
        sa.CheckConstraint(
            "decision IS NULL OR (decision ?& ARRAY['proposal_id', 'approved', 'reasons', 'checks', 'sizing', 'kill_switch_effective', 'triggers', 'limits_version', 'grid_version', 'spec_pin_id', 'as_of', 'approved_at', 'expires_at'] AND jsonb_array_length(decision -> 'checks') = 25 AND decision ->> 'proposal_id' = proposal_id::text AND (decision ->> 'approved')::boolean = (approved_at IS NOT NULL) AND (approved_at IS NULL OR (decision ->> 'limits_version' = limits_version::text AND decision ->> 'grid_version' = grid_version::text AND decision ->> 'spec_pin_id' = spec_pin_id::text AND (decision #>> '{sizing,n_final}')::numeric = n_final AND (decision #>> '{sizing,limit_price}')::numeric = limit_price AND (decision ->> 'as_of')::timestamptz = approved_at AND (decision ->> 'approved_at')::timestamptz = approved_at AND (decision ->> 'expires_at')::timestamptz = expires_at))) IS TRUE",
            name=op.f("ck_b3_entry_intents_decision_matches_its_columns"),
        ),
        sa.CheckConstraint(
            "decision IS NULL OR jsonb_typeof(decision) = 'object'",
            name=op.f("ck_b3_entry_intents_decision_is_an_object"),
        ),
        sa.CheckConstraint(
            "status <> 'proposed' OR decided_at IS NULL",
            name=op.f("ck_b3_entry_intents_proposed_undecided"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR (decided_at IS NOT NULL AND approved_at IS NULL)",
            name=op.f("ck_b3_entry_intents_rejected_is_decided_unapproved"),
        ),
        sa.CheckConstraint(
            "status <> 'unknown' OR unknown_cause IS NOT NULL",
            name=op.f("ck_b3_entry_intents_unknown_cause"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('submitting', 'aborted_before_send', 'working', 'partially_filled', 'filled', 'cancel_requested', 'canceled', 'broker_rejected', 'unknown', 'resolved_manual', 'approved') OR approved_at IS NOT NULL",
            name=op.f("ck_b3_entry_intents_approved_before_claim"),
        ),
        sa.CheckConstraint(
            "(approved_at IS NULL) = (expires_at IS NULL) AND (approved_at IS NULL) = (limits_version IS NULL) AND (approved_at IS NULL) = (grid_version IS NULL) AND (approved_at IS NULL) = (spec_pin_id IS NULL) AND (approved_at IS NULL) = (n_final IS NULL) AND (approved_at IS NULL) = (limit_price IS NULL)",
            name=op.f("ck_b3_entry_intents_approval_is_whole"),
        ),
        sa.CheckConstraint(
            "(claimed_at IS NULL) = (claim_instance_id IS NULL) AND (claimed_at IS NULL) = (claim_fencing_token IS NULL) AND (claimed_at IS NULL) = (send_deadline_utc IS NULL)",
            name=op.f("ck_b3_entry_intents_claim_is_whole"),
        ),
        sa.CheckConstraint(
            "(decided_at IS NULL) = (decision IS NULL)",
            name=op.f("ck_b3_entry_intents_decision_is_whole"),
        ),
        sa.CheckConstraint(
            "approved_at IS NULL OR decided_at IS NOT NULL",
            name=op.f("ck_b3_entry_intents_approval_is_a_decision"),
        ),
        sa.CheckConstraint(
            "claim_instance_id IS NULL OR claim_instance_id = instance_id",
            name=op.f("ck_b3_entry_intents_claimed_by_the_proposing_instance"),
        ),
        sa.CheckConstraint(
            "filled_volume IS NULL OR (filled_volume >= 0 AND filled_volume <= n_final)",
            name=op.f("ck_b3_entry_intents_filled_within_approval"),
        ),
        sa.CheckConstraint(
            "limit_price IS NULL OR limit_price > 0",
            name=op.f("ck_b3_entry_intents_limit_price_positive"),
        ),
        sa.CheckConstraint(
            "n_final IS NULL OR n_final >= 1", name=op.f("ck_b3_entry_intents_n_final_at_least_one")
        ),
        sa.CheckConstraint(
            "send_deadline_utc IS NULL OR send_deadline_utc <= expires_at",
            name=op.f("ck_b3_entry_intents_send_deadline_within_approval"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash", "spec_pin_id"],
            ["b3_spec_pins.organization_id", "b3_spec_pins.account_hash", "b3_spec_pins.id"],
            name=op.f("fk_b3_entry_intents_organization_id_b3_spec_pins"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "proposal_id", "instance_id", "account_hash"],
            [
                "b3_entry_proposals.organization_id",
                "b3_entry_proposals.proposal_id",
                "b3_entry_proposals.instance_id",
                "b3_entry_proposals.account_hash",
            ],
            name=op.f("fk_b3_entry_intents_organization_id_b3_entry_proposals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_entry_intents_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("proposal_id", name=op.f("pk_b3_entry_intents")),
        sa.UniqueConstraint("client_order_id", name="uq_b3_entry_intents_client_order_id"),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "proposal_id", name="uq_b3_entry_intents_account"
        ),
    )
    op.create_index(
        "ix_b3_entry_intents_open",
        "b3_entry_intents",
        ["organization_id", "account_hash"],
        unique=False,
        postgresql_where=sa.text(
            "status IN ('proposed', 'approved', 'submitting', 'working', 'partially_filled', 'cancel_requested', 'unknown')"
        ),
    )
    op.create_index(
        "ix_b3_entry_intents_org_status",
        "b3_entry_intents",
        ["organization_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_entry_intents_organization_id"),
        "b3_entry_intents",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_b3_entry_intents_spec_pin",
        "b3_entry_intents",
        ["organization_id", "account_hash", "spec_pin_id"],
        unique=False,
    )
    op.create_table(
        "b3_exit_intents",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "exit_reason",
            postgresql.ENUM(
                "time_exit",
                "session_flatten",
                "emergency",
                "reversal",
                "overnight_carry",
                name="b3_exit_reason",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("exit_due_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "deadline_at > exit_due_at", name=op.f("ck_b3_exit_intents_deadline_after_due")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash", "position_id"],
            [
                "b3_positions.organization_id",
                "b3_positions.account_hash",
                "b3_positions.position_id",
            ],
            name=op.f("fk_b3_exit_intents_organization_id_b3_positions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_exit_intents_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_exit_intents_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_exit_intents")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "position_id", name="uq_b3_exit_intents_position"
        ),
    )
    op.create_index(
        op.f("ix_b3_exit_intents_organization_id"),
        "b3_exit_intents",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "b3_robot_authority",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("authority_id", sa.UUID(), nullable=False),
        sa.Column("host_hash", sa.Text(), nullable=False),
        sa.Column("instance_id", sa.UUID(), nullable=False),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column(
            "granted_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("authority_expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "revoked", "expired", name="b3_authority_status", create_type=False
            ),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "phase",
            postgresql.ENUM(
                "read_only", "management", "entries", name="b3_authority_phase", create_type=False
            ),
            server_default="management",
            nullable=False,
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expired_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("armed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("armed_strategy_key", sa.Text(), nullable=True),
        sa.Column("armed_strategy_version", sa.Integer(), nullable=True),
        sa.Column("armed_params_hash", sa.Text(), nullable=True),
        sa.Column("limits_version", sa.Integer(), nullable=True),
        sa.Column("spec_pin_id", sa.UUID(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(phase = 'entries') = (armed_at IS NOT NULL)",
            name=op.f("ck_b3_robot_authority_entries_iff_armed"),
        ),
        sa.CheckConstraint(
            "(status = 'expired') = (expired_at IS NOT NULL)",
            name=op.f("ck_b3_robot_authority_expired_iff_at"),
        ),
        sa.CheckConstraint(
            "(status = 'revoked') = (revoked_at IS NOT NULL)",
            name=op.f("ck_b3_robot_authority_revoked_iff_at"),
        ),
        sa.CheckConstraint(
            "host_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_b3_robot_authority_host_hash_is_sha256_hex"),
        ),
        sa.CheckConstraint(
            "phase <> 'read_only'", name=op.f("ck_b3_robot_authority_read_only_has_no_row")
        ),
        sa.CheckConstraint(
            "(armed_at IS NULL) = (armed_strategy_key IS NULL) AND (armed_at IS NULL) = (armed_strategy_version IS NULL) AND (armed_at IS NULL) = (armed_params_hash IS NULL) AND (armed_at IS NULL) = (limits_version IS NULL) AND (armed_at IS NULL) = (spec_pin_id IS NULL)",
            name=op.f("ck_b3_robot_authority_arming_is_whole"),
        ),
        sa.CheckConstraint(
            "authority_expires_at > granted_at",
            name=op.f("ck_b3_robot_authority_expires_after_the_grant"),
        ),
        sa.CheckConstraint(
            "fencing_token >= 1", name=op.f("ck_b3_robot_authority_fencing_token_is_positive")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash", "spec_pin_id"],
            ["b3_spec_pins.organization_id", "b3_spec_pins.account_hash", "b3_spec_pins.id"],
            name=op.f("fk_b3_robot_authority_organization_id_b3_spec_pins"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_robot_authority_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "instance_id"],
            ["b3_robot_instances.organization_id", "b3_robot_instances.instance_id"],
            name=op.f("fk_b3_robot_authority_organization_id_b3_robot_instances"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_robot_authority_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_robot_authority")),
        sa.UniqueConstraint("authority_id", name="uq_b3_robot_authority_authority_id"),
        sa.UniqueConstraint(
            "organization_id", "account_hash", name="uq_b3_robot_authority_account"
        ),
    )
    op.create_index(
        "ix_b3_robot_authority_instance",
        "b3_robot_authority",
        ["organization_id", "instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_robot_authority_organization_id"),
        "b3_robot_authority",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_b3_robot_authority_spec_pin",
        "b3_robot_authority",
        ["organization_id", "account_hash", "spec_pin_id"],
        unique=False,
    )
    op.create_table(
        "b3_sltp_requests",
        sa.Column("sltp_request_id", sa.UUID(), nullable=False),
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("epoch_id", sa.UUID(), nullable=False),
        sa.Column("request_position_ticket", sa.BigInteger(), nullable=False),
        sa.Column("sl", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("tp", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("built_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "intended",
                "not_sent",
                "done",
                "rejected",
                "unknown",
                "moot",
                "resolved_manual",
                name="b3_sltp_request_status",
                create_type=False,
            ),
            server_default="intended",
            nullable=False,
        ),
        sa.Column("retcode", sa.Text(), nullable=True),
        sa.Column("result_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("p4_evidence", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'resolved_manual') = (resolved_at IS NOT NULL) AND (resolved_at IS NULL) = (resolved_by IS NULL) AND (resolved_at IS NULL OR (p4_evidence IS NOT NULL AND length(btrim(p4_evidence)) > 0))",
            name=op.f("ck_b3_sltp_requests_manual_resolution_carries_the_journal_line"),
        ),
        sa.CheckConstraint(
            "purpose IN ('repair', 'bracket')",
            name=op.f("ck_b3_sltp_requests_purpose_is_a_known_label"),
        ),
        sa.CheckConstraint("sl > 0", name=op.f("ck_b3_sltp_requests_never_without_a_stop")),
        sa.CheckConstraint("tp >= 0", name=op.f("ck_b3_sltp_requests_tp_zero_or_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash", "epoch_id"],
            [
                "b3_management_epochs.organization_id",
                "b3_management_epochs.account_hash",
                "b3_management_epochs.epoch_id",
            ],
            name=op.f("fk_b3_sltp_requests_organization_id_b3_management_epochs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash", "position_id"],
            [
                "b3_positions.organization_id",
                "b3_positions.account_hash",
                "b3_positions.position_id",
            ],
            name=op.f("fk_b3_sltp_requests_organization_id_b3_positions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_sltp_requests_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_sltp_requests_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sltp_request_id", name=op.f("pk_b3_sltp_requests")),
    )
    op.create_index(
        "ix_b3_sltp_requests_epoch",
        "b3_sltp_requests",
        ["organization_id", "account_hash", "epoch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_b3_sltp_requests_organization_id"),
        "b3_sltp_requests",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        "ix_b3_sltp_requests_position",
        "b3_sltp_requests",
        ["organization_id", "account_hash", "position_id", "built_at"],
        unique=False,
    )
    op.create_index(
        "uq_b3_sltp_requests_one_in_flight",
        "b3_sltp_requests",
        ["organization_id", "account_hash", "position_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('intended', 'unknown')"),
    )
    op.create_table(
        "b3_orders",
        sa.Column("account_hash", sa.Text(), nullable=False),
        sa.Column("proposal_id", sa.UUID(), nullable=True),
        sa.Column("ticket", sa.BigInteger(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column(
            "side",
            postgresql.ENUM("buy", "sell", name="order_side", create_type=False),
            nullable=False,
        ),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("volume_initial", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("volume_current", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("sl", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("tp", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("magic", sa.BigInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("last_retcode", sa.Text(), nullable=True),
        sa.Column("setup_time_msc", sa.BigInteger(), nullable=True),
        sa.Column("done_time_msc", sa.BigInteger(), nullable=True),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "volume_current >= 0 AND volume_current <= volume_initial",
            name=op.f("ck_b3_orders_volume_current_bounds"),
        ),
        sa.CheckConstraint("volume_initial > 0", name=op.f("ck_b3_orders_volume_is_positive")),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash", "proposal_id"],
            [
                "b3_entry_intents.organization_id",
                "b3_entry_intents.account_hash",
                "b3_entry_intents.proposal_id",
            ],
            name=op.f("fk_b3_orders_organization_id_b3_entry_intents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "account_hash"],
            ["b3_robot_accounts.organization_id", "b3_robot_accounts.registered_account_hash"],
            name=op.f("fk_b3_orders_organization_id_b3_robot_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_b3_orders_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b3_orders")),
        sa.UniqueConstraint(
            "organization_id", "account_hash", "ticket", name="uq_b3_orders_ticket"
        ),
    )
    op.create_index(
        op.f("ix_b3_orders_organization_id"), "b3_orders", ["organization_id"], unique=False
    )
    op.create_index(
        "ix_b3_orders_proposal",
        "b3_orders",
        ["organization_id", "account_hash", "proposal_id"],
        unique=False,
    )


def _drop_tables() -> None:
    op.drop_index("ix_b3_orders_proposal", table_name="b3_orders")
    op.drop_index(op.f("ix_b3_orders_organization_id"), table_name="b3_orders")
    op.drop_table("b3_orders")
    op.drop_index(
        "uq_b3_sltp_requests_one_in_flight",
        table_name="b3_sltp_requests",
        postgresql_where=sa.text("status IN ('intended', 'unknown')"),
    )
    op.drop_index("ix_b3_sltp_requests_position", table_name="b3_sltp_requests")
    op.drop_index(op.f("ix_b3_sltp_requests_organization_id"), table_name="b3_sltp_requests")
    op.drop_index("ix_b3_sltp_requests_epoch", table_name="b3_sltp_requests")
    op.drop_table("b3_sltp_requests")
    op.drop_index("ix_b3_robot_authority_spec_pin", table_name="b3_robot_authority")
    op.drop_index(op.f("ix_b3_robot_authority_organization_id"), table_name="b3_robot_authority")
    op.drop_index("ix_b3_robot_authority_instance", table_name="b3_robot_authority")
    op.drop_table("b3_robot_authority")
    op.drop_index(op.f("ix_b3_exit_intents_organization_id"), table_name="b3_exit_intents")
    op.drop_table("b3_exit_intents")
    op.drop_index("ix_b3_entry_intents_spec_pin", table_name="b3_entry_intents")
    op.drop_index(op.f("ix_b3_entry_intents_organization_id"), table_name="b3_entry_intents")
    op.drop_index("ix_b3_entry_intents_org_status", table_name="b3_entry_intents")
    op.drop_index(
        "ix_b3_entry_intents_open",
        table_name="b3_entry_intents",
        postgresql_where=sa.text(
            "status IN ('proposed', 'approved', 'submitting', 'working', 'partially_filled', 'cancel_requested', 'unknown')"
        ),
    )
    op.drop_table("b3_entry_intents")
    op.drop_index(op.f("ix_b3_spec_pins_organization_id"), table_name="b3_spec_pins")
    op.drop_index("ix_b3_spec_pins_account_pinned", table_name="b3_spec_pins")
    op.drop_table("b3_spec_pins")
    op.drop_index(op.f("ix_b3_session_anchors_organization_id"), table_name="b3_session_anchors")
    op.drop_table("b3_session_anchors")
    op.drop_index(op.f("ix_b3_robot_heartbeats_organization_id"), table_name="b3_robot_heartbeats")
    op.drop_index("ix_b3_robot_heartbeats_account_as_of", table_name="b3_robot_heartbeats")
    op.drop_table("b3_robot_heartbeats")
    op.drop_index(op.f("ix_b3_robot_events_organization_id"), table_name="b3_robot_events")
    op.drop_index("ix_b3_robot_events_instance", table_name="b3_robot_events")
    op.drop_index("ix_b3_robot_events_account", table_name="b3_robot_events")
    op.drop_table("b3_robot_events")
    op.drop_index(op.f("ix_b3_reconciliations_organization_id"), table_name="b3_reconciliations")
    op.drop_index("ix_b3_reconciliations_instance", table_name="b3_reconciliations")
    op.drop_index("ix_b3_reconciliations_account_at", table_name="b3_reconciliations")
    op.drop_table("b3_reconciliations")
    op.drop_index(op.f("ix_b3_positions_organization_id"), table_name="b3_positions")
    op.drop_index(
        "ix_b3_positions_open",
        table_name="b3_positions",
        postgresql_where=sa.text("state <> 'closed'"),
    )
    op.drop_table("b3_positions")
    op.drop_index(
        "uq_b3_management_epochs_open",
        table_name="b3_management_epochs",
        postgresql_where=sa.text("closed_at IS NULL"),
    )
    op.drop_index(
        op.f("ix_b3_management_epochs_organization_id"), table_name="b3_management_epochs"
    )
    op.drop_index("ix_b3_management_epochs_instance", table_name="b3_management_epochs")
    op.drop_index("ix_b3_management_epochs_account", table_name="b3_management_epochs")
    op.drop_table("b3_management_epochs")
    op.drop_index(
        op.f("ix_b3_kill_switch_transitions_organization_id"),
        table_name="b3_kill_switch_transitions",
    )
    op.drop_index(
        "ix_b3_kill_switch_transitions_account_changed", table_name="b3_kill_switch_transitions"
    )
    op.drop_table("b3_kill_switch_transitions")
    op.drop_index("ix_b3_entry_proposals_session", table_name="b3_entry_proposals")
    op.drop_index(op.f("ix_b3_entry_proposals_organization_id"), table_name="b3_entry_proposals")
    op.drop_index("ix_b3_entry_proposals_instance", table_name="b3_entry_proposals")
    op.drop_index("ix_b3_entry_proposals_account", table_name="b3_entry_proposals")
    op.drop_table("b3_entry_proposals")
    op.drop_index("ix_b3_deals_position", table_name="b3_deals")
    op.drop_index(op.f("ix_b3_deals_organization_id"), table_name="b3_deals")
    op.drop_index("ix_b3_deals_org_time", table_name="b3_deals")
    op.drop_table("b3_deals")
    op.drop_index(op.f("ix_b3_bracket_learning_organization_id"), table_name="b3_bracket_learning")
    op.drop_table("b3_bracket_learning")
    op.drop_index(op.f("ix_b3_strategy_magics_organization_id"), table_name="b3_strategy_magics")
    op.drop_table("b3_strategy_magics")
    op.drop_index(op.f("ix_b3_session_grids_organization_id"), table_name="b3_session_grids")
    op.drop_index("ix_b3_session_grids_lookup", table_name="b3_session_grids")
    op.drop_table("b3_session_grids")
    op.drop_index(op.f("ix_b3_robot_instances_organization_id"), table_name="b3_robot_instances")
    op.drop_index("ix_b3_robot_instances_org_started", table_name="b3_robot_instances")
    op.drop_table("b3_robot_instances")
    op.drop_index(op.f("ix_b3_robot_accounts_organization_id"), table_name="b3_robot_accounts")
    op.drop_table("b3_robot_accounts")
    op.drop_index(
        "uq_b3_risk_profiles_current",
        table_name="b3_risk_profiles",
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_index(op.f("ix_b3_risk_profiles_organization_id"), table_name="b3_risk_profiles")
    op.drop_table("b3_risk_profiles")
    op.drop_index(
        "uq_b3_holidays_current",
        table_name="b3_holidays",
        postgresql_where=sa.text("retired_at IS NULL"),
    )
    op.drop_index(op.f("ix_b3_holidays_organization_id"), table_name="b3_holidays")
    op.drop_table("b3_holidays")
    op.drop_index(op.f("ix_b3_fee_schedules_organization_id"), table_name="b3_fee_schedules")
    op.drop_index("ix_b3_fee_schedules_lookup", table_name="b3_fee_schedules")
    op.drop_table("b3_fee_schedules")
    op.drop_index(op.f("ix_b3_contracts_organization_id"), table_name="b3_contracts")
    op.drop_index("ix_b3_contracts_lookup", table_name="b3_contracts")
    op.drop_table("b3_contracts")
