"""``CREATE TYPE`` / ``ALTER TYPE`` / ``DROP TYPE`` for every Postgres enum.

The models declare their enum columns with ``create_type=False`` so exactly one
place owns the types: this module. Adding a value to an enum is therefore always
a migration, as DATABASE.md §1 requires. Labels come from our own ``StrEnum``
members, never from user input.

**Types *and their labels* are frozen per revision here.** The first version of
this module iterated ``ALL_ENUMS`` live, which was fine with one revision and
became a trap with two: adding a type to ``ALL_ENUMS`` for ``0002`` made
``0001`` create it retroactively, so a clean ``upgrade head`` failed with "type
already exists". ``0002`` froze the type *names*, and left the follow-up
recorded in DATABASE.md §16.5: the labels were still read from ``ALL_ENUMS`` at
migration time, so the first revision to add a member to an existing enum —
this one, M2 · T2.1 — would have silently changed what ``0001`` creates.
``EXTENDED`` would have appeared in the ``opportunity_status`` that ``0001``
built, and ``0003``'s ``ALTER TYPE ... ADD VALUE`` would have found it already
there.

So each revision now names its own frozen mapping of type -> labels, exactly
like the grant lists in :mod:`ddl.tables`, and nothing below reads ``ALL_ENUMS``.
``test_migrations.py`` proves both halves: that the mappings still partition
``ALL_ENUMS`` by type name, and that stopping at ``0001`` or ``0002`` produces
exactly the labels — in exactly the order — that revision froze.

**Order is part of the contract.** ``pg_enum.enumsortorder`` is what the schema
tests compare against, so a member added in the middle of a Python class needs
a matching ``BEFORE``/``AFTER`` in :data:`ANALYSIS_ADDED_VALUES`, and vice
versa.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from alembic import op

INITIAL_ENUMS: Final[Mapping[str, tuple[str, ...]]] = {
    "org_role": (
        "OWNER",
        "ADMIN",
        "TRADER",
        "ANALYST",
        "VIEWER",
    ),
    "plan_tier": (
        "FREE",
        "PRO",
        "QUANT",
        "ENTERPRISE",
    ),
    "kill_switch_state": (
        "ACTIVE",
        "WARNING",
        "TRADING_DISABLED",
        "EMERGENCY",
    ),
    "member_status": (
        "invited",
        "active",
        "suspended",
    ),
    "workspace_objective": (
        "explore",
        "paper_trading",
        "research",
        "automated_trading",
    ),
    "subscription_status": (
        "trialing",
        "active",
        "past_due",
        "canceled",
    ),
    "exchange_status": (
        "active",
        "inactive",
    ),
    "market_type": (
        "spot",
        "perpetual",
    ),
    "market_status": (
        "active",
        "suspended",
        "delisted",
    ),
    "candle_timeframe": (
        "1m",
        "5m",
        "15m",
        "1h",
        "4h",
        "1d",
    ),
    "order_side": (
        "buy",
        "sell",
    ),
    "feature_category": (
        "price",
        "volume",
        "volatility",
        "microstructure",
        "momentum",
        "derivatives",
        "cross",
    ),
    "anomaly_type": (
        "VOLUME_SPIKE",
        "PRICE_ACCELERATION",
        "VOLATILITY_EXPANSION",
        "ORDERBOOK_IMBALANCE",
        "OPEN_INTEREST_SPIKE",
        "FUNDING_ANOMALY",
        "LIQUIDATION_CLUSTER",
        "CROSS_EXCHANGE_DIVERGENCE",
        "SOCIAL_SPIKE",
        "WHALE_ACTIVITY",
    ),
    "anomaly_status": (
        "active",
        "resolved",
        "expired",
    ),
    "regime_scope": (
        "global",
        "btc",
    ),
    "market_regime": (
        "BTC_BULL",
        "BTC_BEAR",
        "SIDEWAYS",
        "HIGH_VOLATILITY",
        "LOW_VOLATILITY",
        "RISK_ON",
        "RISK_OFF",
        "ALT_EXPANSION",
        "PANIC",
        "LIQUIDITY_CONTRACTION",
    ),
    "trade_direction": (
        "long",
        "short",
        "neutral",
    ),
    "opportunity_status": (
        "NORMAL",
        "WATCHING",
        "ANOMALY",
        "HOT",
        "ENTRY_CANDIDATE",
        "EXPIRED",
    ),
    "strategy_version_status": (
        "draft",
        "active",
        "deprecated",
    ),
    "signal_status": (
        "active",
        "expired",
        "invalidated",
    ),
    "outcome_result": (
        "target",
        "stop",
        "expired",
        "invalidated",
        "open",
    ),
    "agent_status": (
        "enabled",
        "paused",
        "disabled",
    ),
    "stats_window": (
        "all",
        "7d",
        "30d",
        "90d",
    ),
    "risk_preset": (
        "conservative",
        "balanced",
        "aggressive",
        "custom",
    ),
    "portfolio_type": (
        "paper",
        "shadow",
        "live",
    ),
    "portfolio_status": (
        "active",
        "paused",
        "archived",
    ),
    "proposal_status": (
        "pending",
        "approved",
        "rejected",
        "expired",
        "executed",
        "failed",
    ),
    "order_type": (
        "market",
        "limit",
        "stop_market",
        "stop_limit",
        "take_profit",
    ),
    "order_purpose": (
        "entry",
        "stop",
        "target",
        "exit",
        "reduce",
    ),
    "execution_mode": (
        "paper",
        "shadow",
        "live",
    ),
    "liquidity_role": (
        "maker",
        "taker",
    ),
    "order_status": (
        "pending",
        "submitted",
        "partially_filled",
        "filled",
        "cancelled",
        "rejected",
        "expired",
    ),
    "position_status": (
        "open",
        "closing",
        "closed",
    ),
    "exit_reason": (
        "target",
        "stop",
        "invalidation",
        "manual",
        "kill_switch",
        "expired",
        "risk_event",
    ),
    "risk_event_type": (
        "limits_changed",
        "proposal_rejected",
        "daily_loss_warning",
        "daily_loss_limit",
        "drawdown_warning",
        "drawdown_limit",
        "exposure_limit",
        "data_degraded_in_position",
        "kill_switch_changed",
        "stop_slippage_excess",
        "position_stale_price",
    ),
    "event_severity": (
        "debug",
        "info",
        "warning",
        "error",
        "critical",
    ),
    "ks_scope": (
        "system",
        "organization",
        "portfolio",
    ),
    "connection_status": (
        "pending",
        "valid",
        "invalid",
        "revoked",
    ),
    "backtest_status": (
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
    ),
    "backtest_warning_code": (
        "overfitting",
        "leakage",
        "lookahead",
    ),
    "intelligence_source_kind": (
        "news",
        "reddit",
        "x",
        "google_trends",
        "onchain",
        "whales",
        "listings",
        "unlocks",
        "announcements",
    ),
    "notification_channel": (
        "in_app",
        "email",
        "telegram",
        "discord",
        "push",
    ),
    "notification_status": (
        "pending",
        "sent",
        "failed",
        "read",
    ),
    "worker_heartbeat_status": (
        "healthy",
        "degraded",
        "stale",
        "down",
    ),
}
"""The 44 types ``0001_initial_schema`` creates, with the labels it creates them
with. Frozen — never extend, never reorder. ``0003`` adds ``EXTENDED`` to
``opportunity_status``, ``UNKNOWN`` to ``market_regime`` and two detectors to
``anomaly_type``; none of them belong in what ``0001`` describes."""

SHADOW_ENUMS: Final[Mapping[str, tuple[str, ...]]] = {
    "shadow_tracking_state": (
        "pending_entry",
        "active",
        "terminal",
        "no_entry",
        "censored",
    ),
}
"""The types ``0002_shadow_lab`` adds. Frozen."""

ANALYSIS_ENUMS: Final[Mapping[str, tuple[str, ...]]] = {
    "opportunity_stage": (
        "EARLY",
        "DEVELOPING",
        "EXTENDED",
        "NONE",
    ),
    "anomaly_evaluation_state": (
        "ok",
        "stale",
        "unknown",
    ),
    "baseline_source": (
        "live",
        "bootstrap",
    ),
    "baseline_sampling": ("per_minute",),
}
"""The types ``0003_analysis`` adds. Frozen.

``baseline_sampling`` has a single member on purpose: a second sampling
policy has to arrive as a migration, and every baseline row already records
which policy produced it, so two populations cannot be silently merged."""

ANALYSIS_ADDED_VALUES: Final[tuple[tuple[str, str, str | None], ...]] = (
    ("opportunity_status", "EXTENDED", "EXPIRED"),
    ("anomaly_type", "TRADE_VELOCITY_SPIKE", "SOCIAL_SPIKE"),
    ("anomaly_type", "MOMENTUM_SHIFT", "SOCIAL_SPIKE"),
    ("market_regime", "UNKNOWN", None),
)
"""``(type, new label, the label to insert it before)`` for ``0003_analysis``.

``None`` appends. The positions are not cosmetic: the Python classes in
``hunter_core.domain.enums`` declare these members in the same places, and the
schema test compares against ``enumsortorder``. ``EXTENDED`` goes before
``EXPIRED`` because ``EXPIRED`` is terminal and everything else precedes it;
the two detectors go before ``SOCIAL_SPIKE`` because they are MVP (v1) types and
``SOCIAL_SPIKE``/``WHALE_ACTIVITY`` are Phase 2/3.

Postgres 12+ allows ``ALTER TYPE ... ADD VALUE`` inside a transaction block, but
**not** using the new value in that same transaction — including in a DEFAULT or
an index predicate. ``0003`` therefore adds these and uses none of them; the one
label it does write into DDL (``'EXPIRED'`` in the expiry CHECK) is one ``0001``
already created.
"""


def create_enum_types(types: Mapping[str, Sequence[str]] = INITIAL_ENUMS) -> None:
    """Create the given types with the given labels, before any table uses one."""
    for name, labels in types.items():
        rendered = ", ".join(f"'{label}'" for label in labels)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")


def drop_enum_types(types: Mapping[str, Sequence[str]] = INITIAL_ENUMS) -> None:
    """Drop the given types, after every table that uses one is gone."""
    for name in reversed(list(types)):
        op.execute(f"DROP TYPE IF EXISTS {name}")


def add_enum_values(
    values: Sequence[tuple[str, str, str | None]] = ANALYSIS_ADDED_VALUES,
) -> None:
    """``ALTER TYPE ... ADD VALUE``, positioned, and idempotent.

    ``IF NOT EXISTS`` so a revision that failed after this point can be re-run:
    the alternative is an operator having to hand-edit ``pg_enum`` before the
    retry, which is how a schema ends up different from what the revision says.
    """
    for type_name, label, before in values:
        position = f" BEFORE '{before}'" if before is not None else ""
        op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{label}'{position}")
