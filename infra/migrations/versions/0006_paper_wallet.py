"""paper wallet: the virtual wallet, its reservations and the beta archive

The schema half of Milestone 3 (task T3.1), against ``docs/plans/M3.md`` - the
"Decisao conjunta Claude/Astra" of 2026-09-06, which prevails over the rest of
that plan - and the contract ``docs/RISK_ENGINE.md`` v2. Described in
DATABASE.md section 18.

Nine things, in the order Postgres accepts them:

1. the four new enum types (``ddl/enums.py`` owns every ``CREATE TYPE``; this
   revision's mapping is ``PAPER_ENUMS``);
2. the four new *values* on types ``0001`` already created - ``paper_v1`` on
   ``risk_preset`` and the three ``risk_event_type`` labels the v2 contract
   names. Postgres 12+ allows ``ALTER TYPE ... ADD VALUE`` inside a transaction
   but forbids *using* the value in that same transaction, so this revision adds
   them and writes none of them; ``paper_v1`` reaches the database through
   ``infra/scripts/seed.py``, after this has committed;
3. the guards: six invariants no honest backfill can produce for a row that
   already violates them, so the upgrade counts the offenders and stops with
   instructions instead of guessing (``0002``'s precedent);
4. the six new tables - ``fx_observations`` and ``market_betas`` (global,
   immutable archives) and ``portfolio_currency_anchor``,
   ``portfolio_risk_state``, ``portfolio_exit_intents`` and
   ``participation_consumptions`` (tenant);
5. what the wallet needs on the tables that already existed: the reservation and
   the ``fifo_v1`` sequence on ``trade_proposals``, ``exit_intent_id`` on
   ``orders``, ``execution_key`` on ``fills``, ``fx_observation_id`` on the
   equity curve, and the kill-switch transition's ``evidence`` plus the CHECK
   that makes leaving a latched block an authenticated act;
6. composite identity down proposal -> order -> fill, replacing the
   single-column foreign keys and preserving their ``ON DELETE`` actions;
7. the **principal wallet index**: unique on ``(organization_id, workspace_id)``
   ``WHERE type = 'paper' AND NOT is_arena``, with no mention of ``status`` and
   no exclusion of ``deleted_at``. Alembic's autogenerate does not compare index
   predicates, so this one is asserted against ``pg_indexes`` in
   ``test_schema_paper.py``;
8. RLS and grants for the new tables;
9. the triggers: immutability where the plan says immutable, a monotonic peak
   and sequence, the permanence of an anchored wallet against deletion, against
   the cascade from its workspace and against being edited out of its own scope,
   and a deferred constraint trigger tying every move of the effective kill
   switch to the transition that explains it.

``downgrade()`` reverses all nine and is tested. It refuses first whenever
reversing would silently discard an obligation or the evidence behind a number
that survives it - a live exit intention, a held reservation, participation
spent inside the rolling window, the rate a wallet opened at. Reversing the two
``ADD VALUE``s means rebuilding those types from the labels ``0001`` froze,
because Postgres cannot drop an enum label.

Nothing here depends on session state: no session-level prepared statement, no
``LISTEN``/``NOTIFY``, no session advisory lock. The one GUC involved,
``app.portfolio_teardown``, is ``SET LOCAL`` and read with ``NULLIF``, exactly
like ``app.current_org`` (section 15.4).

**Named ``0006_paper_wallet`` (17 characters).** ``alembic_version.version_num``
is ``VARCHAR(32)`` and that budget is the reason ``0005`` is short (section 17.6).

Revision ID: 0006_paper_wallet
Revises: 0005_baseline_lock_grant
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ddl.enums import (
    PAPER_ADDED_VALUES,
    PAPER_ENUMS,
    add_enum_values,
    create_enum_types,
    drop_enum_types,
)
from ddl.paper import (
    create_anchor_guards,
    create_cascade_guard,
    create_immutability,
    create_kill_switch_audit_guard,
    create_permanence_guards,
    create_risk_state_guards,
    disable_paper_row_level_security,
    drop_anchor_guards,
    drop_immutability,
    drop_permanence_guards,
    drop_risk_state_guards,
    enable_paper_row_level_security,
    grant_paper_privileges,
    refuse_a_downgrade_that_would_discard_durable_state,
    refuse_rows_the_new_invariants_cannot_describe,
    restore_frozen_enum_labels,
    revoke_paper_privileges,
)
from sqlalchemy.dialects import postgresql

revision: str = "0006_paper_wallet"
down_revision: str | None = "0005_baseline_lock_grant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_enum_types(PAPER_ENUMS)
    add_enum_values(PAPER_ADDED_VALUES)
    refuse_rows_the_new_invariants_cannot_describe()
    _add_composite_keys()
    _create_tables()
    _alter_existing_tables()
    enable_paper_row_level_security()
    grant_paper_privileges()
    create_immutability()
    create_anchor_guards()
    create_risk_state_guards()
    create_permanence_guards()
    create_cascade_guard()
    create_kill_switch_audit_guard()


def downgrade() -> None:
    refuse_a_downgrade_that_would_discard_durable_state()
    drop_permanence_guards()
    drop_risk_state_guards()
    drop_anchor_guards()
    drop_immutability()
    revoke_paper_privileges()
    disable_paper_row_level_security()
    _revert_existing_tables()
    _drop_tables()
    _drop_composite_keys()
    restore_frozen_enum_labels()
    drop_enum_types(PAPER_ENUMS)


def _add_composite_keys() -> None:
    """The unique keys the new tables point at, installed before they exist.

    A composite foreign key needs a matching unique constraint on its parent, so
    these five cannot wait their turn in :func:`_alter_existing_tables`: the exit
    intention references the position quadruple, and the participation ledger
    references the proposal, the order *and the market* of both, plus the fill
    inside its own order. Split out for that ordering alone - the statements are
    the autogenerated ones.
    """
    op.create_unique_constraint(
        "uq_trade_proposals_id_scope",
        "trade_proposals",
        ["id", "organization_id", "portfolio_id", "market_id"],
    )
    op.create_unique_constraint(
        "uq_orders_id_scope", "orders", ["id", "organization_id", "portfolio_id"]
    )
    op.create_unique_constraint(
        "uq_orders_id_market_scope",
        "orders",
        ["id", "organization_id", "portfolio_id", "market_id"],
    )
    op.create_unique_constraint(
        "uq_positions_id_scope",
        "positions",
        ["id", "organization_id", "portfolio_id", "market_id"],
    )
    op.create_unique_constraint("uq_fills_id_order", "fills", ["id", "order_id"])


def _drop_composite_keys() -> None:
    op.drop_constraint("uq_fills_id_order", "fills", type_="unique")
    op.drop_constraint("uq_positions_id_scope", "positions", type_="unique")
    op.drop_constraint("uq_orders_id_market_scope", "orders", type_="unique")
    op.drop_constraint("uq_orders_id_scope", "orders", type_="unique")
    op.drop_constraint("uq_trade_proposals_id_scope", "trade_proposals", type_="unique")


def _create_tables() -> None:
    """Autogenerated from ``hunter_core.db.models``, unedited except for order."""
    op.create_table(
        "fx_observations",
        sa.Column("pair", sa.Text(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("available_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint("char_length(pair) > 0", name=op.f("ck_fx_observations_pair_not_empty")),
        sa.CheckConstraint(
            "char_length(source) > 0", name=op.f("ck_fx_observations_source_not_empty")
        ),
        sa.CheckConstraint(
            "observed_at <= available_at", name=op.f("ck_fx_observations_observation_is_causal")
        ),
        sa.CheckConstraint("rate > 0", name=op.f("ck_fx_observations_rate_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fx_observations")),
        sa.UniqueConstraint("pair", "source", "observed_at", name="uq_fx_observations_observation"),
    )
    op.create_index(
        "ix_fx_observations_lookup", "fx_observations", ["pair", "available_at"], unique=False
    )
    op.create_table(
        "market_betas",
        sa.Column("market_id", sa.UUID(), nullable=False),
        sa.Column("reference_market_id", sa.UUID(), nullable=False),
        sa.Column("as_of", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("input_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_pair_end", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "computed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "available_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("beta_version", sa.Text(), nullable=False),
        sa.Column("estimator", sa.Text(), nullable=False),
        sa.Column("beta", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("alpha", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("r_squared", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("contiguous_bars", sa.Integer(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("input_digest", sa.Text(), nullable=False),
        sa.Column(
            "estimate",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("superseded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "NOT valid OR beta IS NOT NULL",
            name=op.f("ck_market_betas_a_valid_revision_has_a_beta"),
        ),
        sa.CheckConstraint(
            "char_length(beta_version) > 0", name=op.f("ck_market_betas_beta_version_not_empty")
        ),
        sa.CheckConstraint(
            "char_length(input_digest) > 0", name=op.f("ck_market_betas_input_digest_not_empty")
        ),
        sa.CheckConstraint(
            "contiguous_bars <= n", name=op.f("ck_market_betas_contiguous_bars_within_n")
        ),
        sa.CheckConstraint(
            "input_start < window_start AND window_start < window_end AND window_end <= as_of AND window_end <= available_at AND valid_until > window_end",
            name=op.f("ck_market_betas_window_is_ordered_and_causal"),
        ),
        sa.CheckConstraint(
            "last_pair_end IS NULL OR (last_pair_end >= window_start AND last_pair_end <= window_end)",
            name=op.f("ck_market_betas_last_pair_end_within_window"),
        ),
        sa.CheckConstraint(
            "n >= 0 AND contiguous_bars >= 0", name=op.f("ck_market_betas_counts_not_negative")
        ),
        sa.CheckConstraint(
            "superseded_at IS NULL OR superseded_at >= computed_at",
            name=op.f("ck_market_betas_superseded_after_computed"),
        ),
        sa.CheckConstraint(
            "valid = (reason IS NULL)", name=op.f("ck_market_betas_reason_states_invalidity")
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
            name=op.f("fk_market_betas_market_id_markets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reference_market_id"],
            ["markets.id"],
            name=op.f("fk_market_betas_reference_market_id_markets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_betas")),
        sa.UniqueConstraint(
            "market_id", "as_of", "beta_version", "input_digest", name="uq_market_betas_revision"
        ),
    )
    op.create_index(
        "ix_market_betas_asof",
        "market_betas",
        ["market_id", "beta_version", "available_at", "as_of"],
        unique=False,
    )
    op.create_index(
        op.f("ix_market_betas_reference_market_id"),
        "market_betas",
        ["reference_market_id"],
        unique=False,
    )
    op.create_index(
        "uq_market_betas_current",
        "market_betas",
        ["market_id", "as_of", "beta_version"],
        unique=True,
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_table(
        "portfolio_currency_anchor",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("origin_currency", sa.Text(), server_default="BRL", nullable=False),
        sa.Column("origin_amount", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("operating_currency", sa.Text(), server_default="USDT", nullable=False),
        sa.Column("credited_amount", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("fx_observation_id", sa.UUID(), nullable=False),
        sa.Column("rate", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("conversion_residual", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("rounding_policy", sa.Text(), nullable=False),
        sa.Column(
            "anchored_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "char_length(operating_currency) > 0",
            name=op.f("ck_portfolio_currency_anchor_operating_currency_not_empty"),
        ),
        sa.CheckConstraint(
            "char_length(origin_currency) > 0",
            name=op.f("ck_portfolio_currency_anchor_origin_currency_not_empty"),
        ),
        sa.CheckConstraint(
            "char_length(rounding_policy) > 0",
            name=op.f("ck_portfolio_currency_anchor_rounding_policy_not_empty"),
        ),
        sa.CheckConstraint(
            "conversion_residual >= 0",
            name=op.f("ck_portfolio_currency_anchor_conversion_residual_not_negative"),
        ),
        sa.CheckConstraint(
            "credited_amount > 0",
            name=op.f("ck_portfolio_currency_anchor_credited_amount_positive"),
        ),
        sa.CheckConstraint(
            "origin_amount > 0", name=op.f("ck_portfolio_currency_anchor_origin_amount_positive")
        ),
        sa.CheckConstraint("rate > 0", name=op.f("ck_portfolio_currency_anchor_rate_positive")),
        sa.CheckConstraint(
            "round(credited_amount * rate + conversion_residual, 10) = round(origin_amount, 10)",
            name=op.f("ck_portfolio_currency_anchor_conversion_is_exact"),
        ),
        sa.ForeignKeyConstraint(
            ["fx_observation_id"],
            ["fx_observations.id"],
            name=op.f("fk_portfolio_currency_anchor_fx_observation_id_fx_observations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_portfolio_currency_anchor_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "organization_id"],
            ["portfolios.id", "portfolios.organization_id"],
            name=op.f("fk_portfolio_currency_anchor_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_currency_anchor")),
        sa.UniqueConstraint("portfolio_id", name="uq_portfolio_currency_anchor_portfolio"),
    )
    op.create_index(
        op.f("ix_portfolio_currency_anchor_fx_observation_id"),
        "portfolio_currency_anchor",
        ["fx_observation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_currency_anchor_organization_id"),
        "portfolio_currency_anchor",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_currency_anchor_portfolio_id"),
        "portfolio_currency_anchor",
        ["portfolio_id"],
        unique=False,
    )
    op.create_table(
        "portfolio_risk_state",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("last_admission_seq", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("trading_day", sa.Date(), nullable=True),
        sa.Column(
            "trading_day_timezone", sa.Text(), server_default="America/Sao_Paulo", nullable=False
        ),
        sa.Column("trading_day_start_utc", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("equity_day_start", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("day_reference_observed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("peak_equity", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("peak_equity_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("peak_sampling_interval_s", sa.Integer(), server_default="60", nullable=False),
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
            "(equity_day_start IS NULL) = (day_reference_observed_at IS NULL)",
            name=op.f("ck_portfolio_risk_state_day_reference_is_all_or_nothing"),
        ),
        sa.CheckConstraint(
            "(trading_day IS NULL) = (trading_day_start_utc IS NULL)",
            name=op.f("ck_portfolio_risk_state_trading_day_is_all_or_nothing"),
        ),
        sa.CheckConstraint(
            "char_length(trading_day_timezone) > 0",
            name=op.f("ck_portfolio_risk_state_trading_day_timezone_not_empty"),
        ),
        sa.CheckConstraint(
            "equity_day_start IS NULL OR equity_day_start >= 0",
            name=op.f("ck_portfolio_risk_state_day_equity_not_negative"),
        ),
        sa.CheckConstraint(
            "equity_day_start IS NULL OR trading_day IS NOT NULL",
            name=op.f("ck_portfolio_risk_state_day_equity_belongs_to_a_day"),
        ),
        sa.CheckConstraint(
            "last_admission_seq >= 0",
            name=op.f("ck_portfolio_risk_state_admission_seq_not_negative"),
        ),
        sa.CheckConstraint(
            "peak_equity >= 0", name=op.f("ck_portfolio_risk_state_peak_equity_not_negative")
        ),
        sa.CheckConstraint(
            "peak_sampling_interval_s > 0",
            name=op.f("ck_portfolio_risk_state_peak_cadence_declared"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_portfolio_risk_state_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "organization_id"],
            ["portfolios.id", "portfolios.organization_id"],
            name=op.f("fk_portfolio_risk_state_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("portfolio_id", name=op.f("pk_portfolio_risk_state")),
    )
    op.create_index(
        op.f("ix_portfolio_risk_state_organization_id"),
        "portfolio_risk_state",
        ["organization_id"],
        unique=False,
    )
    op.create_table(
        "portfolio_exit_intents",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("position_id", sa.UUID(), nullable=False),
        sa.Column("market_id", sa.UUID(), nullable=False),
        sa.Column(
            "reason",
            postgresql.ENUM(
                "target",
                "stop",
                "invalidation",
                "manual",
                "kill_switch",
                "expired",
                "risk_event",
                name="exit_reason",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("protection_key", sa.Text(), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(
                "open",
                "blocked_residual",
                "fulfilled",
                "superseded",
                "voided",
                name="exit_intent_state",
                create_type=False,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("intended_qty", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column(
            "filled_qty", sa.Numeric(precision=28, scale=10), server_default="0", nullable=False
        ),
        sa.Column("trigger_price", sa.Numeric(precision=28, scale=10), nullable=True),
        sa.Column("degraded_since", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("degraded_reason", sa.Text(), nullable=True),
        sa.Column("superseded_by_id", sa.UUID(), nullable=True),
        sa.Column("closed_reason", sa.Text(), nullable=True),
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
            "(state = 'fulfilled') = (filled_qty = intended_qty)",
            name=op.f("ck_portfolio_exit_intents_fulfilled_means_filled"),
        ),
        sa.CheckConstraint(
            "(state = 'superseded') = (superseded_by_id IS NOT NULL)",
            name=op.f("ck_portfolio_exit_intents_superseded_names_its_successor"),
        ),
        sa.CheckConstraint(
            "(state IN ('fulfilled', 'superseded', 'voided')) = (closed_at IS NOT NULL)",
            name=op.f("ck_portfolio_exit_intents_terminal_states_are_closed"),
        ),
        sa.CheckConstraint(
            "state <> 'voided' OR closed_reason IS NOT NULL",
            name=op.f("ck_portfolio_exit_intents_voided_states_why"),
        ),
        sa.CheckConstraint(
            "(degraded_since IS NULL) = (degraded_reason IS NULL)",
            name=op.f("ck_portfolio_exit_intents_degradation_is_all_or_nothing"),
        ),
        sa.CheckConstraint(
            "char_length(protection_key) > 0",
            name=op.f("ck_portfolio_exit_intents_protection_key_not_empty"),
        ),
        sa.CheckConstraint(
            "filled_qty >= 0 AND filled_qty <= intended_qty",
            name=op.f("ck_portfolio_exit_intents_filled_qty_within_intent"),
        ),
        sa.CheckConstraint(
            "id <> superseded_by_id", name=op.f("ck_portfolio_exit_intents_no_self_supersession")
        ),
        sa.CheckConstraint(
            "intended_qty > 0", name=op.f("ck_portfolio_exit_intents_intended_qty_positive")
        ),
        sa.CheckConstraint(
            "trigger_price IS NULL OR trigger_price > 0",
            name=op.f("ck_portfolio_exit_intents_trigger_price_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_portfolio_exit_intents_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "organization_id"],
            ["portfolios.id", "portfolios.organization_id"],
            name=op.f("fk_portfolio_exit_intents_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id", "organization_id", "portfolio_id", "market_id"],
            [
                "positions.id",
                "positions.organization_id",
                "positions.portfolio_id",
                "positions.market_id",
            ],
            name=op.f("fk_portfolio_exit_intents_position_id_positions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by_id", "position_id"],
            ["portfolio_exit_intents.id", "portfolio_exit_intents.position_id"],
            name="fk_portfolio_exit_intents_superseded_by_id",
            ondelete="RESTRICT",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_exit_intents")),
        sa.UniqueConstraint(
            "id",
            "organization_id",
            "portfolio_id",
            "market_id",
            name="uq_portfolio_exit_intents_id_scope",
        ),
        sa.UniqueConstraint("id", "position_id", name="uq_portfolio_exit_intents_id_position"),
    )
    op.create_index(
        op.f("ix_portfolio_exit_intents_market_id"),
        "portfolio_exit_intents",
        ["market_id"],
        unique=False,
    )
    op.create_index(
        "ix_portfolio_exit_intents_org_portfolio_state",
        "portfolio_exit_intents",
        ["organization_id", "state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_exit_intents_organization_id"),
        "portfolio_exit_intents",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_exit_intents_portfolio_id"),
        "portfolio_exit_intents",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_exit_intents_position_id"),
        "portfolio_exit_intents",
        ["position_id"],
        unique=False,
    )
    op.create_index(
        "uq_portfolio_exit_intents_live",
        "portfolio_exit_intents",
        ["position_id", "protection_key"],
        unique=True,
        postgresql_where=sa.text("state IN ('open', 'blocked_residual')"),
    )
    op.create_table(
        "participation_consumptions",
        sa.Column("portfolio_id", sa.UUID(), nullable=False),
        sa.Column("market_id", sa.UUID(), nullable=False),
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("order_id", sa.UUID(), nullable=True),
        sa.Column("fill_id", sa.UUID(), nullable=True),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "reserved",
                "executed",
                "released",
                name="participation_entry_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("notional", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organization_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(kind = 'executed') = (fill_id IS NOT NULL AND order_id IS NOT NULL)",
            name=op.f("ck_participation_consumptions_execution_names_its_fill"),
        ),
        sa.CheckConstraint(
            "notional > 0", name=op.f("ck_participation_consumptions_notional_positive")
        ),
        sa.ForeignKeyConstraint(
            ["fill_id", "order_id"],
            ["fills.id", "fills.order_id"],
            name=op.f("fk_participation_consumptions_fill_id_fills"),
        ),
        sa.ForeignKeyConstraint(
            ["market_id"],
            ["markets.id"],
            name=op.f("fk_participation_consumptions_market_id_markets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "organization_id", "portfolio_id", "market_id"],
            ["orders.id", "orders.organization_id", "orders.portfolio_id", "orders.market_id"],
            name=op.f("fk_participation_consumptions_order_id_orders"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_participation_consumptions_organization_id_organizations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id", "organization_id"],
            ["portfolios.id", "portfolios.organization_id"],
            name=op.f("fk_participation_consumptions_portfolio_id_portfolios"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id", "organization_id", "portfolio_id", "market_id"],
            [
                "trade_proposals.id",
                "trade_proposals.organization_id",
                "trade_proposals.portfolio_id",
                "trade_proposals.market_id",
            ],
            name=op.f("fk_participation_consumptions_proposal_id_trade_proposals"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_participation_consumptions")),
    )
    op.create_index(
        op.f("ix_participation_consumptions_fill_id"),
        "participation_consumptions",
        ["fill_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_participation_consumptions_market_id"),
        "participation_consumptions",
        ["market_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_participation_consumptions_order_id"),
        "participation_consumptions",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_participation_consumptions_organization_id"),
        "participation_consumptions",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_participation_consumptions_portfolio_id"),
        "participation_consumptions",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_participation_consumptions_proposal_id"),
        "participation_consumptions",
        ["proposal_id"],
        unique=False,
    )
    op.create_index(
        "ix_participation_window",
        "participation_consumptions",
        ["organization_id", "portfolio_id", "market_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "uq_participation_executed",
        "participation_consumptions",
        ["fill_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'executed'"),
    )
    op.create_index(
        "uq_participation_released",
        "participation_consumptions",
        ["proposal_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'released'"),
    )
    op.create_index(
        "uq_participation_reserved",
        "participation_consumptions",
        ["proposal_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'reserved'"),
    )


def _alter_existing_tables() -> None:
    """What the wallet needs on the tables ``0001`` already created."""
    op.add_column("fills", sa.Column("execution_key", sa.Text(), nullable=True))
    # Derived from a column that is already there - the 0002 boundary: backfill
    # what the existing columns *imply*. A fill's own id is a unique, stable key
    # for that execution. It is a *legacy identity*, not a claim that duplicate
    # protection was ever applied to those rows, and the downgrade guard tells the
    # two apart by exactly this equality. On every database today it touches
    # nothing: no production code writes a fill yet.
    op.execute("UPDATE fills SET execution_key = id::text WHERE execution_key IS NULL")
    op.alter_column("fills", "execution_key", nullable=False)
    op.create_unique_constraint(
        "uq_fills_execution_key", "fills", ["organization_id", "execution_key"]
    )
    op.drop_constraint(op.f("fk_fills_order_id_orders"), "fills", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_fills_order_id_orders"),
        "fills",
        "orders",
        ["order_id", "organization_id", "portfolio_id"],
        ["id", "organization_id", "portfolio_id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        op.f("ck_fills_execution_key_not_empty"), "fills", "char_length(execution_key) > 0"
    )
    op.add_column(
        "kill_switch_transitions",
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_kill_switch_transitions_a_transition_moves"),
        "kill_switch_transitions",
        "from_state <> to_state",
    )
    op.create_check_constraint(
        op.f("ck_kill_switch_transitions_actor_type_is_known"),
        "kill_switch_transitions",
        "actor_type IN ('user', 'system')",
    )
    op.create_check_constraint(
        op.f("ck_kill_switch_transitions_resuming_a_block_is_authenticated"),
        "kill_switch_transitions",
        "NOT (from_state IN ('TRADING_DISABLED', 'EMERGENCY') AND to_state IN ('ACTIVE', 'WARNING')) OR (actor_type = 'user' AND actor_id IS NOT NULL)",
    )
    op.add_column("orders", sa.Column("exit_intent_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_orders_exit_intent_id"), "orders", ["exit_intent_id"], unique=False)
    op.drop_constraint(op.f("fk_orders_proposal_id_trade_proposals"), "orders", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_orders_proposal_id_trade_proposals"),
        "orders",
        "trade_proposals",
        ["proposal_id", "organization_id", "portfolio_id", "market_id"],
        ["id", "organization_id", "portfolio_id", "market_id"],
        ondelete="SET NULL (proposal_id)",
    )
    op.create_foreign_key(
        op.f("fk_orders_exit_intent_id_portfolio_exit_intents"),
        "orders",
        "portfolio_exit_intents",
        ["exit_intent_id", "organization_id", "portfolio_id", "market_id"],
        ["id", "organization_id", "portfolio_id", "market_id"],
        ondelete="SET NULL (exit_intent_id)",
    )
    op.create_check_constraint(
        op.f("ck_orders_an_entry_serves_no_exit_intent"),
        "orders",
        "purpose <> 'entry' OR exit_intent_id IS NULL",
    )
    op.add_column(
        "portfolio_equity_snapshots", sa.Column("fx_observation_id", sa.UUID(), nullable=True)
    )
    op.create_index(
        op.f("ix_portfolio_equity_snapshots_fx_observation_id"),
        "portfolio_equity_snapshots",
        ["fx_observation_id"],
        unique=False,
    )
    op.create_foreign_key(
        op.f("fk_portfolio_equity_snapshots_fx_observation_id_fx_observations"),
        "portfolio_equity_snapshots",
        "fx_observations",
        ["fx_observation_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "uq_portfolios_principal_paper",
        "portfolios",
        ["organization_id", "workspace_id"],
        unique=True,
        postgresql_where=sa.text("type = 'paper' AND NOT is_arena"),
    )
    op.add_column(
        "trade_proposals",
        sa.Column(
            "source",
            postgresql.ENUM("manual", "agent", name="proposal_source", create_type=False),
            server_default="manual",
            nullable=False,
        ),
    )
    op.add_column("trade_proposals", sa.Column("admission_seq", sa.BigInteger(), nullable=True))
    op.add_column(
        "trade_proposals",
        sa.Column(
            "reservation_state",
            postgresql.ENUM(
                "none",
                "held",
                "consumed",
                "released",
                "expired",
                name="reservation_state",
                create_type=False,
            ),
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column(
        "trade_proposals",
        sa.Column("reserved_notional", sa.Numeric(precision=28, scale=10), nullable=True),
    )
    op.add_column(
        "trade_proposals",
        sa.Column("reserved_cash", sa.Numeric(precision=28, scale=10), nullable=True),
    )
    op.add_column(
        "trade_proposals",
        sa.Column("reserved_risk", sa.Numeric(precision=28, scale=10), nullable=True),
    )
    op.add_column(
        "trade_proposals",
        sa.Column("reserved_slot", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "trade_proposals", sa.Column("reserved_until", sa.TIMESTAMP(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_trade_proposals_reservation_expiry",
        "trade_proposals",
        ["organization_id", "portfolio_id", "reserved_until"],
        unique=False,
        postgresql_where=sa.text("reservation_state = 'held'"),
    )
    op.create_unique_constraint(
        "uq_trade_proposals_admission_seq",
        "trade_proposals",
        ["organization_id", "portfolio_id", "admission_seq"],
    )
    op.create_check_constraint(
        op.f("ck_trade_proposals_a_reservation_is_quantified"),
        "trade_proposals",
        "reservation_state = 'none' OR (reserved_notional IS NOT NULL AND reserved_cash IS NOT NULL AND reserved_risk IS NOT NULL AND reserved_until IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_trade_proposals_a_slot_is_held_or_gone"),
        "trade_proposals",
        "NOT reserved_slot OR reservation_state = 'held'",
    )
    op.create_check_constraint(
        op.f("ck_trade_proposals_admission_seq_positive"),
        "trade_proposals",
        "admission_seq IS NULL OR admission_seq > 0",
    )
    op.create_check_constraint(
        op.f("ck_trade_proposals_an_unreserved_proposal_holds_nothing"),
        "trade_proposals",
        "reservation_state <> 'none' OR (reserved_notional IS NULL AND reserved_cash IS NULL AND reserved_risk IS NULL AND reserved_until IS NULL)",
    )
    op.create_check_constraint(
        op.f("ck_trade_proposals_reserved_amounts_are_sane"),
        "trade_proposals",
        "(reserved_notional IS NULL OR reserved_notional > 0) AND (reserved_cash IS NULL OR reserved_cash > 0) AND (reserved_risk IS NULL OR reserved_risk >= 0)",
    )


def _revert_existing_tables() -> None:
    op.drop_constraint(
        op.f("ck_trade_proposals_reserved_amounts_are_sane"), "trade_proposals", type_="check"
    )
    op.drop_constraint(
        op.f("ck_trade_proposals_an_unreserved_proposal_holds_nothing"),
        "trade_proposals",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_trade_proposals_admission_seq_positive"), "trade_proposals", type_="check"
    )
    op.drop_constraint(
        op.f("ck_trade_proposals_a_slot_is_held_or_gone"), "trade_proposals", type_="check"
    )
    op.drop_constraint(
        op.f("ck_trade_proposals_a_reservation_is_quantified"), "trade_proposals", type_="check"
    )
    op.drop_constraint("uq_trade_proposals_admission_seq", "trade_proposals", type_="unique")
    op.drop_index(
        "ix_trade_proposals_reservation_expiry",
        table_name="trade_proposals",
        postgresql_where=sa.text("reservation_state = 'held'"),
    )
    op.drop_column("trade_proposals", "reserved_until")
    op.drop_column("trade_proposals", "reserved_slot")
    op.drop_column("trade_proposals", "reserved_risk")
    op.drop_column("trade_proposals", "reserved_cash")
    op.drop_column("trade_proposals", "reserved_notional")
    op.drop_column("trade_proposals", "reservation_state")
    op.drop_column("trade_proposals", "admission_seq")
    op.drop_column("trade_proposals", "source")
    op.drop_index(
        "uq_portfolios_principal_paper",
        table_name="portfolios",
        postgresql_where=sa.text("type = 'paper' AND NOT is_arena"),
    )
    op.drop_constraint(
        op.f("fk_portfolio_equity_snapshots_fx_observation_id_fx_observations"),
        "portfolio_equity_snapshots",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_portfolio_equity_snapshots_fx_observation_id"),
        table_name="portfolio_equity_snapshots",
    )
    op.drop_column("portfolio_equity_snapshots", "fx_observation_id")
    op.drop_constraint(op.f("ck_orders_an_entry_serves_no_exit_intent"), "orders", type_="check")
    op.drop_constraint(
        op.f("fk_orders_exit_intent_id_portfolio_exit_intents"), "orders", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_orders_proposal_id_trade_proposals"), "orders", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_orders_proposal_id_trade_proposals"),
        "orders",
        "trade_proposals",
        ["proposal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_index(op.f("ix_orders_exit_intent_id"), table_name="orders")
    op.drop_column("orders", "exit_intent_id")
    op.drop_constraint(
        op.f("ck_kill_switch_transitions_resuming_a_block_is_authenticated"),
        "kill_switch_transitions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_kill_switch_transitions_actor_type_is_known"),
        "kill_switch_transitions",
        type_="check",
    )
    op.drop_constraint(
        op.f("ck_kill_switch_transitions_a_transition_moves"),
        "kill_switch_transitions",
        type_="check",
    )
    op.drop_column("kill_switch_transitions", "evidence")
    op.drop_constraint(op.f("ck_fills_execution_key_not_empty"), "fills", type_="check")
    op.drop_constraint(op.f("fk_fills_order_id_orders"), "fills", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_fills_order_id_orders"),
        "fills",
        "orders",
        ["order_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_fills_execution_key", "fills", type_="unique")
    op.drop_column("fills", "execution_key")


def _drop_tables() -> None:
    op.drop_index(
        "uq_participation_reserved",
        table_name="participation_consumptions",
        postgresql_where=sa.text("kind = 'reserved'"),
    )
    op.drop_index(
        "uq_participation_released",
        table_name="participation_consumptions",
        postgresql_where=sa.text("kind = 'released'"),
    )
    op.drop_index(
        "uq_participation_executed",
        table_name="participation_consumptions",
        postgresql_where=sa.text("kind = 'executed'"),
    )
    op.drop_index("ix_participation_window", table_name="participation_consumptions")
    op.drop_index(
        op.f("ix_participation_consumptions_proposal_id"), table_name="participation_consumptions"
    )
    op.drop_index(
        op.f("ix_participation_consumptions_portfolio_id"), table_name="participation_consumptions"
    )
    op.drop_index(
        op.f("ix_participation_consumptions_organization_id"),
        table_name="participation_consumptions",
    )
    op.drop_index(
        op.f("ix_participation_consumptions_order_id"), table_name="participation_consumptions"
    )
    op.drop_index(
        op.f("ix_participation_consumptions_market_id"), table_name="participation_consumptions"
    )
    op.drop_index(
        op.f("ix_participation_consumptions_fill_id"), table_name="participation_consumptions"
    )
    op.drop_table("participation_consumptions")
    op.drop_index(
        "uq_portfolio_exit_intents_live",
        table_name="portfolio_exit_intents",
        postgresql_where=sa.text("state IN ('open', 'blocked_residual')"),
    )
    op.drop_index(
        op.f("ix_portfolio_exit_intents_position_id"), table_name="portfolio_exit_intents"
    )
    op.drop_index(
        op.f("ix_portfolio_exit_intents_portfolio_id"), table_name="portfolio_exit_intents"
    )
    op.drop_index(
        op.f("ix_portfolio_exit_intents_organization_id"), table_name="portfolio_exit_intents"
    )
    op.drop_index(
        "ix_portfolio_exit_intents_org_portfolio_state", table_name="portfolio_exit_intents"
    )
    op.drop_index(op.f("ix_portfolio_exit_intents_market_id"), table_name="portfolio_exit_intents")
    op.drop_table("portfolio_exit_intents")
    op.drop_index(
        op.f("ix_portfolio_risk_state_organization_id"), table_name="portfolio_risk_state"
    )
    op.drop_table("portfolio_risk_state")
    op.drop_index(
        op.f("ix_portfolio_currency_anchor_portfolio_id"), table_name="portfolio_currency_anchor"
    )
    op.drop_index(
        op.f("ix_portfolio_currency_anchor_organization_id"), table_name="portfolio_currency_anchor"
    )
    op.drop_index(
        op.f("ix_portfolio_currency_anchor_fx_observation_id"),
        table_name="portfolio_currency_anchor",
    )
    op.drop_table("portfolio_currency_anchor")
    op.drop_index(
        "uq_market_betas_current",
        table_name="market_betas",
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_index(op.f("ix_market_betas_reference_market_id"), table_name="market_betas")
    op.drop_index("ix_market_betas_asof", table_name="market_betas")
    op.drop_table("market_betas")
    op.drop_index("ix_fx_observations_lookup", table_name="fx_observations")
    op.drop_table("fx_observations")
