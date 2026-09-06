#!/usr/bin/env python3
"""Seed the reference data every environment needs — DATABASE.md, PRODUCT.md §5,
RISK_ENGINE.md §2, PIPELINE.md §2 and §5.

Idempotent: most writes are an upsert on the row's natural key
(``exchanges.code``, ``strategies.key``, ``(strategy_id, version)``,
``(plan, key)``, ``feature_flags.key``, the system-preset
``risk_profiles.preset``), so running it twice leaves the same row counts.

Two tables are **not** upserted, because their content is frozen once published
and something stored elsewhere names it: ``opportunity_weights.version``, which
every score cites, and ``(feature_definitions.name, version)``, whose identity is
hashed into every ``feature_snapshots.feature_set_version``. For those the seed
inserts what is missing, *verifies* what exists, and stops on a divergence
(DATABASE.md §17.8).

The content lives in the sibling ``seed_reference`` module — literals, plus the
feature catalogue derived from the ``hunter_indicators`` registry; this file is
the writes. ``is_active`` on ``opportunity_weights`` is the one thing here that
is an *operational* state rather than content, and §17 of DATABASE.md records
how it is handled: the seed promotes the release's profile exactly once, on the
run that first creates it, and never touches the flag on a row that already
exists.

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

from seed_reference import (
    ENTITLEMENTS,
    EXCHANGES,
    FEATURE_FLAGS,
    REGIME_MULTIPLIERS,
    RISK_LIMITS,
    RISK_PRESETS,
    STRATEGIES,
    feature_definition_rows,
)
from seed_weights import seed_opportunity_weights
from sqlalchemy import select, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from hunter_core.db.models import (
    Exchange,
    FeatureDefinition,
    FeatureFlag,
    PlanEntitlement,
    RiskProfile,
    Strategy,
    StrategyVersion,
)
from hunter_core.domain.enums import Plan, StrategyVersionStatus
from hunter_core.domain.types import uuid7
from hunter_core.settings import Settings


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


async def _refuse_diverging_definition(conn: AsyncConnection, row: dict[str, Any]) -> None:
    """A published ``(name, version)`` is frozen, like a weight vector (§17.8).

    ``feature_snapshots.feature_set_version`` is a hash of exactly what
    ``FeatureDefinition.identity()`` covers — key, version, category, inputs and
    parameters — so rewriting any of them under a name that already exists makes
    this table describe an engine that did not produce the stored snapshots. A
    real formula change is a **new** ``version`` in the registry, which inserts a
    row next to the old one; there is no case where overwriting is right, so the
    seed stops instead. ``description`` is deliberately outside the check: it is
    prose, excluded from the hash, and is refreshed in place.
    """
    stored = (
        await conn.execute(
            select(
                FeatureDefinition.category,
                FeatureDefinition.inputs,
                FeatureDefinition.parameters,
                FeatureDefinition.description,
            ).where(
                FeatureDefinition.name == row["name"],
                FeatureDefinition.version == row["version"],
            )
        )
    ).first()
    if stored is None:
        return  # deleted between the insert and this read; the next run inserts it
    identity = (stored.category, sorted(stored.inputs), stored.parameters)
    shipped = (row["category"], sorted(row["inputs"]), row["parameters"])
    if identity != shipped:
        raise SystemExit(
            f"feature_definitions {row['name']} v{row['version']} in the database differs "
            f"from the definition this build's registry publishes, and a published feature "
            f"identity is never rewritten: every feature_snapshots.feature_set_version "
            f"naming it was hashed from the stored one. Bump the version in "
            f"hunter_indicators instead of editing the definition in place."
        )
    if stored.description != row["description"]:
        await conn.execute(
            text(
                "UPDATE feature_definitions SET description = :description "
                "WHERE name = :name AND version = :version"
            ),
            {"description": row["description"], "name": row["name"], "version": row["version"]},
        )


async def seed_feature_definitions(conn: AsyncConnection) -> int:
    """The catalogue of ``hunter_indicators``' registry — derived, never retyped.

    ``seed_reference.feature_definition_rows()`` is the engine's own
    ``as_row()``, so the table says which features exist, what category they are
    in, which sources each may read and with which parameters, in the build's
    vocabulary. Missing rows are inserted; existing ones are *verified* and a
    divergence stops the seed — the ``opportunity_weights`` rule of §17.8, for
    the same reason: a stored snapshot names an identity, and that identity has
    to keep meaning what it meant.
    """
    rows = feature_definition_rows()
    for row in rows:
        statement = insert(FeatureDefinition).values(id=uuid7(), **row)
        result = await conn.execute(
            statement.on_conflict_do_nothing(constraint="uq_feature_definitions_name").returning(
                FeatureDefinition.id
            )
        )
        if not result.fetchall():
            await _refuse_diverging_definition(conn, row)

    present = await conn.execute(
        select(FeatureDefinition.id).where(
            tuple_(FeatureDefinition.name, FeatureDefinition.version).in_(
                [(row["name"], row["version"]) for row in rows]
            )
        )
    )
    # Counted from what the database actually holds, never from len(rows) — the
    # doctrine ``_written`` states, and the reason the risk_profiles bug showed.
    return len(present.fetchall())


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
                "feature_definitions": await seed_feature_definitions(conn),
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
