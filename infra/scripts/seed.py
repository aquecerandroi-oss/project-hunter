#!/usr/bin/env python3
"""Seed the reference data every environment needs — DATABASE.md, PRODUCT.md §5,
RISK_ENGINE.md §2, PIPELINE.md §5.

Idempotent: every write is an upsert on the row's natural key (``exchanges.code``,
``strategies.key``, ``(strategy_id, version)``, ``(plan, key)``,
``feature_flags.key``, the system-preset ``risk_profiles.preset``,
``opportunity_weights.version``), so running it twice leaves the same row counts.

Every count it reports comes from the statement's ``RETURNING`` clause, never
from the length of the input tuple: a row a policy filters away has to make the
number go down, or the report is worse than no report at all.

Fractions are stored as JSON **strings**, never JSON numbers: a limit like
``0.0025`` has no exact binary float, and the Risk Engine reads these straight
into ``Decimal``. Integers and booleans stay native.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler) over
asyncpg, the only Postgres driver this workspace installs.

Usage:
    uv run python infra/scripts/seed.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.db.models import (
    Exchange,
    FeatureFlag,
    OpportunityWeights,
    PlanEntitlement,
    RiskProfile,
    Strategy,
    StrategyVersion,
)
from hunter_core.domain.enums import Plan, RiskPreset, StrategyVersionStatus
from hunter_core.domain.types import uuid7
from hunter_core.settings import Settings

_CAPABILITIES = {
    "spot": True,
    "perpetual": True,
    "funding": True,
    "open_interest": True,
    "liquidations": True,
    "ws_depth": True,
}

EXCHANGES: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("binance", "Binance", _CAPABILITIES),
    ("bybit", "Bybit", _CAPABILITIES),
)

STRATEGIES: tuple[tuple[str, str, str, str], ...] = (
    ("momentum", "Momentum", "trend", "Continuation with relative volume and breakout strength."),
    ("breakout", "Breakout", "trend", "Range break confirmed by volume and order flow."),
    ("volume_anomaly", "Volume Anomaly", "anomaly", "Entry after a VOLUME_SPIKE with pressure."),
    ("order_flow", "Order Flow", "microstructure", "Book imbalance and taker pressure."),
    ("mean_reversion", "Mean Reversion", "reversion", "Fade of stretched moves in low volatility."),
    ("derivatives", "Derivatives", "derivatives", "Funding, open interest and liquidation setups."),
    ("narrative", "Narrative", "intelligence", "Narrative and news driven flow (Phase 2)."),
    ("ensemble", "Ensemble", "meta", "Weighted combination of the other strategies."),
)

ENTITLEMENTS: dict[str, tuple[Any, Any, Any, Any]] = {
    # key: (FREE, PRO, QUANT, ENTERPRISE) — ``None`` means unlimited
    "max_agents": (2, 8, 30, None),
    "max_exchanges": (2, 4, 8, None),
    "max_portfolios": (1, 5, 20, None),
    "market_history_days": (30, 180, 730, None),
    "backtesting": (False, True, True, True),
    "advanced_intelligence": (False, False, True, True),
    "custom_agent_params": (False, True, True, True),
    "live_trading": (False, False, True, True),
    "api_access": (False, True, True, True),
}

FEATURE_FLAGS: tuple[tuple[str, str], ...] = (
    ("ENABLE_LIVE_TRADING", "Live execution. Stays off until Phase 4."),
    ("ENABLE_SOCIAL_INTELLIGENCE", "Social sources for the intelligence pipeline."),
    ("ENABLE_ONCHAIN", "On-chain sources for the intelligence pipeline."),
    ("ENABLE_STRIPE", "Billing through Stripe."),
    ("ENABLE_LLM_ANALYSIS", "LLM classification of external content."),
    ("ENABLE_ARENA", "Agent Arena."),
    ("ENABLE_BACKTESTS", "Backtest engine and UI."),
)

RISK_LIMITS: dict[str, tuple[Any, Any, Any]] = {
    # key: (conservative, balanced, aggressive) — RISK_ENGINE.md §2
    "max_position_pct": ("0.02", "0.05", "0.10"),
    "risk_per_trade_pct": ("0.0025", "0.005", "0.01"),
    "max_total_exposure_pct": ("0.30", "0.60", "1.00"),
    "max_daily_loss_pct": ("0.01", "0.02", "0.04"),
    "max_drawdown_pct": ("0.05", "0.10", "0.20"),
    "max_concurrent_positions": (3, 6, 12),
    "max_asset_exposure_pct": ("0.05", "0.10", "0.20"),
    "max_exchange_exposure_pct": ("0.50", "0.70", "1.00"),
    "min_liquidity_usd_24h": ("50000000", "20000000", "5000000"),
    "max_spread_pct": ("0.0005", "0.001", "0.002"),
    "max_slippage_pct": ("0.001", "0.002", "0.005"),
    "max_leverage": (1, 2, 3),
    "max_correlated_positions": (2, 4, 8),
    "min_stop_distance_pct": ("0.003", "0.002", "0.001"),
    "max_stop_distance_pct": ("0.03", "0.05", "0.08"),
    "auto_close_on_emergency": (False, False, False),
}

REGIME_MULTIPLIERS: tuple[dict[str, str], ...] = (
    # RISK_ENGINE.md §2 grammar: `<REGIME>` or `<REGIME>_<DIRECTION>`, where
    # <REGIME> is a `market_regime` label and <DIRECTION> is a `trade_direction`
    # upper-cased. The engine looks up `<REGIME>_<DIRECTION>` first, then
    # `<REGIME>`, then falls back to 1.0 — so `BTC_BEAR_LONG` narrows longs in a
    # bear market while `HIGH_VOLATILITY` applies to both directions.
    {"BTC_BEAR_LONG": "0.5", "HIGH_VOLATILITY": "0.7"},
    {"BTC_BEAR_LONG": "0.5", "HIGH_VOLATILITY": "0.7"},
    {"HIGH_VOLATILITY": "0.85"},
)

RISK_PRESETS: tuple[tuple[RiskPreset, str], ...] = (
    (RiskPreset.CONSERVATIVE, "Conservative"),
    (RiskPreset.BALANCED, "Balanced"),
    (RiskPreset.AGGRESSIVE, "Aggressive"),
)

OPPORTUNITY_WEIGHTS_V1: dict[str, str] = {
    "momentum": "0.20",
    "volume": "0.20",
    "liquidity": "0.10",
    "order_flow": "0.15",
    "derivatives": "0.10",
    "market_regime": "0.10",
    "anomalies": "0.10",
    "agent_consensus": "0.05",
    "external_intelligence": "0.00",
}


def migration_url() -> str:
    """``DATABASE_URL_MIGRATIONS`` on the asyncpg driver."""
    secret = Settings().database_url_migrations
    if secret is None or not secret.get_secret_value():
        raise SystemExit("DATABASE_URL_MIGRATIONS is not configured")
    url = secret.get_secret_value()
    if url.startswith("postgresql+"):
        return url
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _written(result: Any) -> int:
    """How many rows the statement actually wrote, from its ``RETURNING`` clause.

    Every count in this module comes from here rather than from the length of the
    input tuple. A constant is what let the ``risk_profiles`` bug hide: under
    ``FORCE ROW LEVEL SECURITY`` the upsert matched nothing, wrote nothing, and
    the script still printed "seeded 3 row(s)". An upsert that is filtered away
    by a policy returns no rows, so the report goes to zero with it.
    """
    return len(result.fetchall())


async def seed_exchanges(conn: AsyncConnection) -> int:
    written = 0
    for code, name, capabilities in EXCHANGES:
        statement = insert(Exchange).values(
            id=uuid7(), code=code, name=name, capabilities=capabilities
        )
        result = await conn.execute(
            statement.on_conflict_do_update(
                index_elements=[Exchange.code],
                set_={
                    "name": statement.excluded.name,
                    "capabilities": statement.excluded.capabilities,
                },
            ).returning(Exchange.id)
        )
        written += _written(result)
    return written


async def seed_strategies(conn: AsyncConnection) -> tuple[int, int]:
    """Catalogue plus one ``draft`` v1 per strategy (PIPELINE.md §6 activates them).

    Returns ``(strategies, strategy_versions)`` — two tables, two counts, because
    a report that folded them together could not show one of them failing.
    """
    strategies = versions = 0
    for key, name, category, description in STRATEGIES:
        statement = insert(Strategy).values(
            id=uuid7(), key=key, name=name, category=category, description=description
        )
        result = await conn.execute(
            statement.on_conflict_do_update(
                index_elements=[Strategy.key],
                set_={
                    "name": statement.excluded.name,
                    "category": statement.excluded.category,
                    "description": statement.excluded.description,
                },
            ).returning(Strategy.id)
        )
        strategy_id: uuid.UUID = result.scalar_one()
        strategies += 1
        version = insert(StrategyVersion).values(
            id=uuid7(),
            strategy_id=strategy_id,
            version="v1",
            status=StrategyVersionStatus.DRAFT,
            code_ref=f"hunter_indicators.strategies.{key}_v1",
        )
        version_result = await conn.execute(
            version.on_conflict_do_update(
                index_elements=[StrategyVersion.strategy_id, StrategyVersion.version],
                set_={"code_ref": version.excluded.code_ref},
            ).returning(StrategyVersion.id)
        )
        versions += _written(version_result)
    return strategies, versions


async def seed_plan_entitlements(conn: AsyncConnection) -> int:
    plans = (Plan.FREE, Plan.PRO, Plan.QUANT, Plan.ENTERPRISE)
    rows = [
        {"plan": plan, "key": key, "value": {"value": values[index]}}
        for key, values in ENTITLEMENTS.items()
        for index, plan in enumerate(plans)
    ]
    statement = insert(PlanEntitlement).values(rows)
    result = await conn.execute(
        statement.on_conflict_do_update(
            index_elements=[PlanEntitlement.plan, PlanEntitlement.key],
            set_={"value": statement.excluded.value},
        ).returning(PlanEntitlement.key)
    )
    return _written(result)


async def seed_feature_flags(conn: AsyncConnection) -> int:
    """Defaults only. The ``ENABLE_*`` env vars are the fallback; this table wins."""
    rows = [{"key": key, "enabled": False, "description": text} for key, text in FEATURE_FLAGS]
    statement = insert(FeatureFlag).values(rows)
    result = await conn.execute(
        statement.on_conflict_do_update(
            index_elements=[FeatureFlag.key],
            set_={"description": statement.excluded.description},
        ).returning(FeatureFlag.key)
    )
    return _written(result)


async def seed_risk_profiles(conn: AsyncConnection) -> int:
    """System presets: ``organization_id IS NULL``, copied into an org at onboarding.

    These rows only exist because ``0001`` grants the migrating role the
    ``system_presets_manageable`` policy. ``risk_profiles`` has ``FORCE ROW LEVEL
    SECURITY``, which filters the table owner too, so under an ordinary
    ``NOSUPERUSER`` owner — what a managed Postgres gives you — this upsert
    matched nothing, wrote nothing, and still reported three rows seeded.

    Note the coupling that survives: the policy is granted ``TO CURRENT_USER``,
    the role that ran the migration. Run this script as a *different* role and
    the presets are filtered away again — silently no longer, since the count
    below comes from ``RETURNING``, but still. DATABASE.md §15.6 records it as an
    operational constraint: seed and migrate as the same role.
    """
    written = 0
    for index, (preset, name) in enumerate(RISK_PRESETS):
        limits: dict[str, Any] = {key: values[index] for key, values in RISK_LIMITS.items()}
        limits["regime_size_multiplier"] = REGIME_MULTIPLIERS[index]
        statement = insert(RiskProfile).values(
            id=uuid7(), organization_id=None, name=name, preset=preset, limits=limits
        )
        result = await conn.execute(
            statement.on_conflict_do_update(
                index_elements=[RiskProfile.preset],
                index_where=RiskProfile.organization_id.is_(None),
                set_={"name": statement.excluded.name, "limits": statement.excluded.limits},
            ).returning(RiskProfile.id)
        )
        written += _written(result)
    return written


async def seed_opportunity_weights(conn: AsyncConnection) -> int:
    statement = insert(OpportunityWeights).values(
        id=uuid7(),
        version="v1",
        weights=OPPORTUNITY_WEIGHTS_V1,
        is_active=True,
        description="Default component weights for the opportunity score (PIPELINE.md §5).",
    )
    result = await conn.execute(
        statement.on_conflict_do_update(
            index_elements=[OpportunityWeights.version],
            # ``is_active`` is deliberately NOT updated. Which version is live is
            # an operational decision (a rollback after a bad tuning, say), and
            # re-running the seed — which every deploy does — must not quietly
            # reactivate v1 underneath it. The partial unique index on
            # ``is_active`` would refuse the write anyway, turning a routine
            # deploy into a failed one.
            set_={"weights": statement.excluded.weights},
        ).returning(OpportunityWeights.id)
    )
    return _written(result)


async def seed() -> dict[str, int]:
    """Every reference table, and how many rows each one actually took."""
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        async with engine.begin() as conn:
            exchanges = await seed_exchanges(conn)
            strategies, strategy_versions = await seed_strategies(conn)
            return {
                "exchanges": exchanges,
                "strategies": strategies,
                "strategy_versions": strategy_versions,
                "plan_entitlements": await seed_plan_entitlements(conn),
                "feature_flags": await seed_feature_flags(conn),
                "risk_profiles": await seed_risk_profiles(conn),
                "opportunity_weights": await seed_opportunity_weights(conn),
            }
    finally:
        await engine.dispose()


def main() -> int:
    for table, count in asyncio.run(seed()).items():
        print(f"seeded {count:>3} row(s) into {table}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
