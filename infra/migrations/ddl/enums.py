"""``CREATE TYPE`` / ``DROP TYPE`` for every Postgres enum.

The models declare their enum columns with ``create_type=False`` so exactly one
place owns the types: this module, driven by ``hunter_core.domain.enums.ALL_ENUMS``.
Adding a value to an enum is therefore always a migration, as DATABASE.md §1
requires. Labels come from our own ``StrEnum`` members, never from user input.

**Which types belong to which revision is frozen here.** The first version of
this module iterated ``ALL_ENUMS`` live, which was fine while there was exactly
one revision and became a trap the moment there were two: adding a type to
``ALL_ENUMS`` for ``0002`` made ``0001`` create it retroactively, so a clean
``upgrade head`` failed with "type already exists" — and, worse, ``0001`` would
have silently stopped describing the schema it actually built. Each revision now
names its own tuple, exactly like the frozen grant lists in :mod:`ddl.tables`,
and ``test_migrations.py`` proves the tuples still partition ``ALL_ENUMS``.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from hunter_core.domain.enums import ALL_ENUMS

INITIAL_ENUMS: tuple[str, ...] = (
    "org_role",
    "plan_tier",
    "kill_switch_state",
    "member_status",
    "workspace_objective",
    "subscription_status",
    "exchange_status",
    "market_type",
    "market_status",
    "candle_timeframe",
    "order_side",
    "feature_category",
    "anomaly_type",
    "anomaly_status",
    "regime_scope",
    "market_regime",
    "trade_direction",
    "opportunity_status",
    "strategy_version_status",
    "signal_status",
    "outcome_result",
    "agent_status",
    "stats_window",
    "risk_preset",
    "portfolio_type",
    "portfolio_status",
    "proposal_status",
    "order_type",
    "order_purpose",
    "execution_mode",
    "liquidity_role",
    "order_status",
    "position_status",
    "exit_reason",
    "risk_event_type",
    "event_severity",
    "ks_scope",
    "connection_status",
    "backtest_status",
    "backtest_warning_code",
    "intelligence_source_kind",
    "notification_channel",
    "notification_status",
    "worker_heartbeat_status",
)
"""The 44 types ``0001_initial_schema`` creates. Frozen — never extend."""

SHADOW_ENUMS: tuple[str, ...] = ("shadow_tracking_state",)
"""The types ``0002_shadow_lab`` adds."""


def create_enum_types(names: Sequence[str] = INITIAL_ENUMS) -> None:
    """Create the named enum types, before any table that uses one."""
    for name in names:
        labels = ", ".join(f"'{member.value}'" for member in ALL_ENUMS[name])
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")


def drop_enum_types(names: Sequence[str] = INITIAL_ENUMS) -> None:
    """Drop the named enum types, after every table that uses one is gone."""
    for name in reversed(list(names)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
