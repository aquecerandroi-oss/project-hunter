"""The frozen table catalogue this revision secures — DATABASE.md §1.2.

Who the roles are, and why they exist, is in :mod:`ddl.security`; the grants and
the policies built from these lists are in :mod:`ddl.grants` and
:mod:`ddl.policies`. This module is only the vocabulary, kept apart so those
three can share it without importing each other.

Two application roles, both ``NOLOGIN`` (deployments grant them to the concrete
login role of the environment):

- ``hunter_app`` — what the API runs as. Full DML on the tenant tables it owns,
  ``INSERT``/``SELECT`` only on the append-only ones, and **``SELECT`` only** on
  every global catalogue, market and analysis table: the API reads the universe,
  the workers write it. Never ``BYPASSRLS``.
- ``hunter_worker`` — what the workers run as. Writes market data, analysis,
  execution and system tables; reads the rest. ``BYPASSRLS`` because strategy,
  execution and analytics scan every organization; the ``ALTER ROLE`` is wrapped
  in an exception handler so the migration still succeeds on a managed Postgres
  where the migrating role may not grant that attribute (the deployment then
  sets it once by hand — see the notice the migration raises).

Every list here is **frozen**: a revision must describe the schema *as of that
revision*, so editing a model years from now must not retroactively change what
``0001`` does. The integration tests are what catch the drift —
``test_schema_rls.py`` compares :data:`TENANT_TABLES` with
``hunter_core.db.models.tenant_tables()``, and ``test_schema_privileges.py``
asserts the three grant classes still partition the tables Postgres actually has.
"""

from __future__ import annotations

APPEND_ONLY_TABLES: tuple[str, ...] = (
    "audit_logs",
    "risk_events",
    "kill_switch_transitions",
    "system_events",
)
"""INSERT + SELECT only, for **both** roles — never UPDATE, never DELETE."""

APP_READ_ONLY_TABLES: tuple[str, ...] = (
    # market reference and market data
    "assets",
    "exchanges",
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
    "opportunities",
    "opportunity_history",
    "opportunity_weights",
    # strategy catalogue and the signals it emits
    "strategies",
    "strategy_versions",
    "agent_signals",
    "signal_outcomes",
    # platform configuration and bookkeeping
    "plan_entitlements",
    "feature_flags",
    "intelligence_sources",
    "intelligence_events",
    "worker_heartbeats",
    "processed_events",
)
"""``SELECT`` for ``hunter_app``. Nothing here is written by a user request in
M0, so nothing here is writable by the API role: an SQL-injection or a logic bug
in a request handler cannot flip a feature flag, retune the opportunity weights
or rewrite the strategy catalogue. The exception list is deliberately empty."""

APP_WRITE_TABLES: tuple[str, ...] = (
    "users",
    "organizations",
    "organization_members",
    "organization_invitations",
    "organization_feature_overrides",
    "workspaces",
    "api_keys",
    "subscriptions",
    "risk_profiles",
    "portfolios",
    "portfolio_equity_snapshots",
    "agents",
    "agent_stats",
    "alert_rules",
    "notifications",
    "exchange_connections",
    "backtests",
    "backtest_results",
    "backtest_trades",
    "trade_proposals",
    "orders",
    "fills",
    "positions",
    "trades",
)
"""Full DML for ``hunter_app`` — and every one of them is behind RLS."""

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
    # strategy catalogue, signals and agent statistics
    "strategies",
    "strategy_versions",
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
    # backtests, platform configuration and system bookkeeping
    "backtests",
    "backtest_results",
    "backtest_trades",
    "plan_entitlements",
    "feature_flags",
    "intelligence_sources",
    "intelligence_events",
    "worker_heartbeats",
    "processed_events",
    "notifications",
)
"""``INSERT``/``UPDATE``/``DELETE`` for ``hunter_worker``, on top of read-all."""

TENANT_TABLES: tuple[str, ...] = (
    "agent_stats",
    "agents",
    "alert_rules",
    "api_keys",
    "audit_logs",
    "backtest_results",
    "backtest_trades",
    "backtests",
    "exchange_connections",
    "fills",
    "kill_switch_transitions",
    "notifications",
    "orders",
    "organization_feature_overrides",
    "organization_invitations",
    "organization_members",
    "portfolio_equity_snapshots",
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

SELF_SCOPED_TABLES: tuple[str, ...] = ("organizations", "users")
"""RLS tables that have no ``organization_id`` of their own.

``organizations`` is keyed on its own ``id``; ``users`` is reachable through
membership of the current organization, plus the caller's own row. They are the
only two relations that carry RLS without carrying the tenant column, which is
why ``test_schema_rls.py`` states the invariant as
``secured == with_organization_id ∪ SELF_SCOPED_TABLES``.
"""

ALL_TABLES: tuple[str, ...] = tuple(
    sorted({*APPEND_ONLY_TABLES, *APP_READ_ONLY_TABLES, *APP_WRITE_TABLES})
)
"""Every table this revision creates, exactly once.

The three ``hunter_app`` grant classes are a partition of the schema — no table
is in two of them and none is missing — and ``test_schema_privileges.py`` proves
they still are against the live ``pg_class``.
"""
