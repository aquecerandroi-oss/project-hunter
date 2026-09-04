"""Roles, grants and Row Level Security — DATABASE.md §1.2, SECURITY.md §3.

Two application roles, both ``NOLOGIN`` (deployments grant them to the concrete
login role of the environment):

- ``hunter_app`` — what the API runs as. Full DML on tenant and global tables,
  but only ``INSERT``/``SELECT`` on the append-only tables, and always subject to
  RLS (no ``BYPASSRLS``).
- ``hunter_worker`` — what the workers run as. Writes market data, analysis,
  execution and system tables; reads the rest. ``BYPASSRLS`` because strategy,
  execution and analytics scan every organization; the ``ALTER ROLE`` is wrapped
  in an exception handler so the migration still succeeds on a managed Postgres
  where the migrating role may not grant that attribute (the deployment then
  sets it once by hand — see the notice the migration raises).

RLS is enabled *and forced* on every table with ``organization_id``, so even the
table owner is filtered. ``TENANT_TABLES`` is a frozen list rather than a live
read of ``Base.metadata``: a revision must describe the schema *as of that
revision*, so editing a model years from now must not retroactively change what
``0001`` does. ``test_schema_rls.py`` asserts the frozen list still equals
``hunter_core.db.models.tenant_tables()``, which is what catches the drift.
"""

from __future__ import annotations

from alembic import op

APP_ROLE = "hunter_app"
WORKER_ROLE = "hunter_worker"

APPEND_ONLY_TABLES: tuple[str, ...] = (
    "audit_logs",
    "risk_events",
    "kill_switch_transitions",
    "system_events",
)
"""INSERT + SELECT only for ``hunter_app`` — never UPDATE, never DELETE."""

WORKER_WRITE_TABLES: tuple[str, ...] = (
    # market reference and market data
    "exchanges",
    "assets",
    "markets",
    "candles",
    "market_snapshots",
    "funding_rates",
    "open_interest_history",
    "liquidations",
    "ingestion_gaps",
    # analysis
    "feature_definitions",
    "feature_snapshots",
    "anomalies",
    "market_regimes",
    "opportunity_weights",
    "opportunities",
    "opportunity_history",
    # signals and agent statistics
    "agent_signals",
    "signal_outcomes",
    "agent_stats",
    # execution
    "trade_proposals",
    "orders",
    "fills",
    "positions",
    "trades",
    "portfolio_equity_snapshots",
    # backtests and system bookkeeping
    "backtests",
    "backtest_results",
    "backtest_trades",
    "worker_heartbeats",
    "processed_events",
    "notifications",
)

TENANT_TABLES: tuple[str, ...] = (
    "agents",
    "alert_rules",
    "api_keys",
    "audit_logs",
    "backtests",
    "exchange_connections",
    "fills",
    "notifications",
    "orders",
    "organization_feature_overrides",
    "organization_invitations",
    "organization_members",
    "portfolios",
    "positions",
    "risk_events",
    "risk_profiles",
    "subscriptions",
    "trade_proposals",
    "trades",
    "workspaces",
)
"""Every table with ``organization_id`` as of this revision — the RLS set."""

TENANT_POLICY = "tenant_isolation"
SYSTEM_PRESET_POLICY = "system_presets_readable"
_ORG_MATCH = "organization_id = current_setting('app.current_org', true)::uuid"


def create_roles() -> None:
    """Create both roles if they do not already exist.

    Postgres has no ``CREATE ROLE IF NOT EXISTS``; roles are cluster-wide, so
    another database may already have created them. The ``duplicate_object``
    handler makes this idempotent without querying ``pg_roles``.
    """
    for role in (APP_ROLE, WORKER_ROLE):
        op.execute(
            f"DO $$ BEGIN CREATE ROLE {role} NOLOGIN; "
            f"EXCEPTION WHEN duplicate_object THEN "
            f"RAISE NOTICE 'role {role} already exists'; END $$;"
        )
    op.execute(
        f"DO $$ BEGIN ALTER ROLE {WORKER_ROLE} BYPASSRLS; "
        f"EXCEPTION WHEN insufficient_privilege THEN "
        f"RAISE NOTICE 'could not set BYPASSRLS on {WORKER_ROLE}; "
        f"grant it manually with a superuser role'; END $$;"
    )


def grant_privileges() -> None:
    """Grant what each role needs; revoke what the append-only rule forbids."""
    for role in (APP_ROLE, WORKER_ROLE):
        op.execute(f"GRANT USAGE ON SCHEMA public TO {role}")

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM {APP_ROLE}")

    op.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {WORKER_ROLE}")
    for table in WORKER_WRITE_TABLES:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {table} TO {WORKER_ROLE}")
    for table in APPEND_ONLY_TABLES:
        op.execute(f"GRANT INSERT ON {table} TO {WORKER_ROLE}")


def revoke_privileges() -> None:
    """Reverse :func:`grant_privileges`. The roles themselves survive a downgrade."""
    for role in (APP_ROLE, WORKER_ROLE):
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}")
        op.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")


def enable_row_level_security() -> None:
    """Enable, force and police every table carrying ``organization_id``."""
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {TENANT_POLICY} ON {table} "
            f"USING ({_ORG_MATCH}) WITH CHECK ({_ORG_MATCH})"
        )
    # risk_profiles rows with a NULL organization_id are the seeded system presets
    # every organization copies at onboarding; tenant_isolation alone would hide
    # them. Read-only on purpose: WITH CHECK stays strictly tenant-scoped, so the
    # app can never create or edit a system preset.
    op.execute(
        f"CREATE POLICY {SYSTEM_PRESET_POLICY} ON risk_profiles "
        f"FOR SELECT USING (organization_id IS NULL)"
    )


def disable_row_level_security() -> None:
    """Drop the policies and turn RLS back off (tables are dropped afterwards)."""
    op.execute(f"DROP POLICY IF EXISTS {SYSTEM_PRESET_POLICY} ON risk_profiles")
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {TENANT_POLICY} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
