#!/usr/bin/env python3
"""Seed the reference data every environment needs — DATABASE.md, PRODUCT.md §5,
RISK_ENGINE.md §2, PIPELINE.md §2 and §5.

Idempotent: most writes are an upsert on the row's natural key (``exchanges.code``,
``strategies.key``, ``(strategy_id, version)``, ``(plan, key)``, ``feature_flags.key``,
the system-preset ``risk_profiles.preset``), so running it twice leaves the same counts.

Three things are **never** rewritten, because their content is frozen once
published and something stored elsewhere names it: ``opportunity_weights.version``,
which every score cites, ``(feature_definitions.name, version)``, hashed into
every ``feature_snapshots.feature_set_version``, and a ``strategy_version`` past
its first activation, which every shadow signal points at. The first two are
inserted when missing, *verified* when present, and a divergence stops the seed.
The third does not even stop it: the frozen row is the truth, a registry that has
moved on is answered by a successor version rather than by this script, so the
row is left untouched and reported (DATABASE.md §16.1 and §17.8).

The content is the sibling ``seed_reference`` module (fractions as JSON strings
included); this file is the writes. ``is_active`` on ``opportunity_weights`` is
the one *operational* state here, handled as §17.8 says: promoted exactly once,
on the run that first creates the profile, never touched on a row that exists.

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

    Every count in this module comes from here, never from the length of the
    input tuple: a constant is what let the ``risk_profiles`` bug hide, printing
    "seeded 3 row(s)" while ``FORCE ROW LEVEL SECURITY`` filtered every one of
    them away. A row a policy refuses has to make the number go down.
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


async def _report_frozen_version(conn: AsyncConnection, key: str, shipped: str) -> int:
    """The activated v1 the upsert skipped: report it, count it as present (§16.1).

    Not an error, and not this script's to resolve: the activated row is the truth
    every shadow signal points at, while ``shipped`` is only the registry's
    placeholder. Moving a frozen version onto real code publishes a successor
    (``activate_strategy_version.py --supersede``), which is why rewriting the old
    one is what ``0002``'s trigger refuses.
    """
    stored = await conn.scalar(
        select(StrategyVersion.code_ref)
        .join(Strategy, Strategy.id == StrategyVersion.strategy_id)
        .where(Strategy.key == key, StrategyVersion.version == "v1")
    )
    if stored != shipped:
        print(
            f"note: {key} v1 is activated and frozen at {stored}; this build's registry "
            f"ships {shipped}. Left untouched: supersede it to move the code."
        )
    return 1


async def seed_strategies(conn: AsyncConnection) -> tuple[int, int]:
    """Catalogue plus one ``draft`` v1 per strategy (PIPELINE.md §6 activates them).

    The version upsert **never touches an activated row**: ``WHERE activated_at
    IS NULL`` on the ``DO UPDATE`` turns a frozen row into a no-op, so no
    ``UPDATE`` runs and ``0002``'s freeze trigger never fires. Without it, one
    activated version failed the statement and — the seed being a single
    transaction — took all eight reference tables down with it, on every deploy
    from then on. A ``draft`` row is still refreshed: nothing points at it yet,
    and until something is activated the registry is the only truth there is.

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
        code_ref = f"hunter_indicators.strategies.{key}_v1"
        version = insert(StrategyVersion).values(
            id=uuid7(),
            strategy_id=strategy_id,
            version="v1",
            status=StrategyVersionStatus.DRAFT,
            code_ref=code_ref,
        )
        version_result = await conn.execute(
            version.on_conflict_do_update(
                index_elements=[StrategyVersion.strategy_id, StrategyVersion.version],
                set_={"code_ref": version.excluded.code_ref},
                where=StrategyVersion.activated_at.is_(None),
            ).returning(StrategyVersion.id)
        )
        # A frozen row the statement skipped is still a row that is there.
        written = _written(version_result)
        versions += written or await _report_frozen_version(conn, key, code_ref)
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
    ``system_presets_manageable`` policy: ``risk_profiles`` has ``FORCE ROW LEVEL
    SECURITY``, which filters the table owner too, so under an ordinary
    ``NOSUPERUSER`` owner this upsert matched nothing, wrote nothing and still
    reported three rows seeded. The coupling that survives is ``TO CURRENT_USER``
    — run this as a *different* role and the presets are filtered away again,
    visibly now that the count comes from ``RETURNING``. DATABASE.md §15.6 records
    it: seed and migrate as the same role.
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

    ``feature_snapshots.feature_set_version`` hashes exactly what
    ``FeatureDefinition.identity()`` covers — key, version, category, inputs,
    parameters — so rewriting any of them under an existing name makes this table
    describe an engine that did not produce the stored snapshots. A real formula
    change is a **new** ``version`` in the registry, inserted next to the old row;
    overwriting is never right, so the seed stops. ``description`` is outside the
    check: prose, excluded from the hash, refreshed in place.
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

    ``seed_reference.feature_definition_rows()`` is the engine's own ``as_row()``,
    so the table says which features exist, in which category, reading which
    sources with which parameters, in the build's vocabulary. Missing rows are
    inserted, existing ones *verified*, and a divergence stops the seed — the
    ``opportunity_weights`` rule of §17.8, for the same reason: a stored snapshot
    names an identity, which has to keep meaning what it meant.
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
