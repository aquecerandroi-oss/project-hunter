"""``infra/scripts/seed.py`` and ``infra/scripts/create_partitions.py`` are idempotent.

Both scripts run against a database of their own so their writes cannot disturb
the RLS and constraint tests. They are loaded by path rather than imported: they
are operational scripts under ``infra/scripts``, not an installed package.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from types import ModuleType
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import create_partition_sql

from .conftest import SCRIPTS_DIR, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

OWNER_ROLE = "hunter_owner_probe"
OWNER_PASSWORD = "FAKEownerpw"
OWNER_DB = "hunter_owned"

SEEDED_TABLES = (
    "exchanges",
    "strategies",
    "strategy_versions",
    "plan_entitlements",
    "feature_flags",
    "risk_profiles",
    "opportunity_weights",
)


def _use(url: str) -> None:
    """Point the operational scripts at ``url``.

    They all read ``DATABASE_URL_MIGRATIONS`` through ``Settings()`` at call
    time, and this module drives three different databases, so the variable is
    set per test rather than once per fixture.
    """
    os.environ["DATABASE_URL_MIGRATIONS"] = url


def _load_script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"hunter_infra_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seed_db(container_url: str) -> Iterator[str]:
    """A migrated database used only by this module."""
    url = asyncio.run(create_database(container_url, "hunter_seed"))
    command.upgrade(alembic_config(url), "head")
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    yield url


async def _row_counts(url: str) -> dict[str, int]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            counts: dict[str, int] = {}
            for table in SEEDED_TABLES:
                value = await connection.scalar(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
                counts[table] = int(value or 0)
    finally:
        await engine.dispose()
    return counts


async def _partition_names(url: str) -> set[str]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            # 'p' as well as 'r': the candles_1m level is a partition and is
            # itself partitioned, and create_partitions.py ensures it too
            result = await connection.execute(
                text("SELECT relname FROM pg_class WHERE relispartition AND relkind IN ('r', 'p')")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


def test_seeding_twice_leaves_the_same_rows(seed_db: str) -> None:
    """And what the seed *reports* is what the database actually holds.

    The counts used to be the length of the input tuples — constants, printed
    whether or not a single row landed. That is precisely how the RLS bug in
    ``risk_profiles`` stayed invisible: the script said "seeded 3 row(s)" while
    ``FORCE ROW LEVEL SECURITY`` filtered every one of them away. Each seed
    function now counts what ``RETURNING`` gave back.
    """
    _use(seed_db)
    seed = _load_script("seed")

    first: dict[str, int] = asyncio.run(seed.seed())
    counts_after_first = asyncio.run(_row_counts(seed_db))
    second: dict[str, int] = asyncio.run(seed.seed())
    counts_after_second = asyncio.run(_row_counts(seed_db))

    assert first == second
    assert counts_after_first == counts_after_second
    assert set(first) == set(SEEDED_TABLES), "the seed no longer reports every table it writes"
    assert first == counts_after_first, "the seed reported rows it did not write"
    assert counts_after_first["exchanges"] == 2
    assert counts_after_first["strategies"] == 8
    assert counts_after_first["strategy_versions"] == 8
    assert counts_after_first["plan_entitlements"] == 36
    assert counts_after_first["feature_flags"] == 7
    assert counts_after_first["risk_profiles"] == 3
    assert counts_after_first["opportunity_weights"] == 1


def test_seeded_risk_presets_carry_the_documented_limits(seed_db: str) -> None:
    """RISK_ENGINE.md §2, and fractions are JSON strings so they stay exact."""
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _balanced_limits() -> dict[str, Any]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                value = await connection.scalar(
                    text("SELECT limits FROM risk_profiles WHERE preset = 'balanced'")
                )
        finally:
            await engine.dispose()
        assert isinstance(value, dict)
        return cast("dict[str, Any]", value)

    limits = asyncio.run(_balanced_limits())
    assert limits["max_position_pct"] == "0.05"
    assert limits["risk_per_trade_pct"] == "0.005"
    assert limits["max_drawdown_pct"] == "0.10"
    assert limits["max_concurrent_positions"] == 6
    assert limits["auto_close_on_emergency"] is False


def test_create_partitions_is_idempotent(seed_db: str) -> None:
    _use(seed_db)
    create_partitions = _load_script("create_partitions")

    # far enough ahead to run past what 0001 already created (2026-09..2026-12),
    # so the first run really creates something and the second really has nothing
    # left to do — with a shorter horizon both runs would be no-ops and the
    # assertions would hold vacuously
    groups: list[tuple[str, list[tuple[str, str]]]] = create_partitions.planned_groups(6)
    statements = [statement for _parent, group in groups for statement in group]
    before = asyncio.run(_partition_names(seed_db))
    created: list[str] = asyncio.run(create_partitions.ensure_partitions(groups))
    after = asyncio.run(_partition_names(seed_db))

    assert created, "the first run created no partition; the horizon is too short to test"
    assert set(created) == after - before
    assert {name for name, _ in statements} <= after

    created_again: list[str] = asyncio.run(create_partitions.ensure_partitions(groups))
    assert created_again == []
    assert asyncio.run(_partition_names(seed_db)) == after


def test_create_partitions_dry_run_touches_nothing(seed_db: str) -> None:
    _use(seed_db)
    create_partitions = _load_script("create_partitions")

    before = asyncio.run(_partition_names(seed_db))
    statements: list[tuple[str, str]] = create_partitions.planned_statements(12)

    # every statement either creates a partition or hardens one; nothing else
    prefixes = ("CREATE TABLE IF NOT EXISTS", "REVOKE ALL ON", "ALTER TABLE", "CREATE POLICY")
    unexpected = [
        sql for _, sql in statements if not sql.startswith((*prefixes, "DROP POLICY IF EXISTS"))
    ]
    assert unexpected == []
    assert any(sql.startswith("REVOKE ALL ON") for _, sql in statements)
    assert asyncio.run(_partition_names(seed_db)) == before


def test_new_partitions_are_hardened_the_way_the_migration_hardens_them(
    seed_db: str,
) -> None:
    """A partition created by the daily job is no more reachable than one from ``0001``.

    Same two properties the review found missing: no direct grant for either
    application role, and — for a child of a tenant parent — RLS enabled, forced
    and policed on the child itself.
    """
    _use(seed_db)
    create_partitions = _load_script("create_partitions")
    asyncio.run(create_partitions.ensure_partitions(create_partitions.planned_groups(9)))

    async def _inspect() -> tuple[list[str], list[str]]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT c.relname, c.relrowsecurity AND c.relforcerowsecurity "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "JOIN pg_attribute a ON a.attrelid = c.oid "
                        "WHERE n.nspname = 'public' AND c.relispartition "
                        "AND c.relkind IN ('r', 'p') "
                        "AND a.attname = 'organization_id' AND NOT a.attisdropped"
                    )
                )
                unforced = [row[0] for row in result if not row[1]]
                granted = await connection.execute(
                    text(
                        "SELECT c.relname FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relispartition "
                        "AND c.relkind IN ('r', 'p') "
                        "AND (has_table_privilege('hunter_app', c.oid, 'SELECT') "
                        "OR has_table_privilege('hunter_worker', c.oid, 'SELECT'))"
                    )
                )
                reachable = [row[0] for row in granted]
        finally:
            await engine.dispose()
        return unforced, reachable

    unforced, reachable = asyncio.run(_inspect())
    assert unforced == [], f"tenant partitions without forced RLS: {unforced}"
    assert reachable == [], f"partitions an application role can read directly: {reachable}"


def test_reseeding_never_reactivates_a_retired_weight_version(seed_db: str) -> None:
    """Which opportunity weights are live is an operational decision, not a seed one.

    The seed used to write ``is_active`` on conflict, so every deploy silently
    reactivated v1 underneath whatever an operator had switched to. With the
    partial unique index on ``is_active`` it would not even fail loudly — it
    would fail the deploy.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _retire_then_reseed() -> tuple[bool, bool]:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE opportunity_weights SET is_active = false WHERE version = 'v1'")
                )
        finally:
            await engine.dispose()
        await seed.seed()
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                active = await connection.scalar(
                    text("SELECT is_active FROM opportunity_weights WHERE version = 'v1'")
                )
                weights = await connection.scalar(
                    text("SELECT weights ? 'momentum' FROM opportunity_weights WHERE version='v1'")
                )
        finally:
            await engine.dispose()
        return bool(active), bool(weights)

    still_active, weights_refreshed = asyncio.run(_retire_then_reseed())
    assert still_active is False, "re-seeding reactivated a version an operator had retired"
    assert weights_refreshed is True, "the seed must still refresh the weight vector itself"


def test_only_one_weight_version_can_be_active(seed_db: str) -> None:
    """The partial unique index — the scorer must never have to pick one of two."""
    _use(seed_db)

    async def _activate_two() -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE opportunity_weights SET is_active = true WHERE version = 'v1'")
                )
                await connection.execute(
                    text(
                        "INSERT INTO opportunity_weights (id, version, weights, is_active) "
                        "VALUES (gen_random_uuid(), 'v2-probe', '{}'::jsonb, true)"
                    )
                )
        finally:
            await engine.dispose()

    with pytest.raises(IntegrityError, match="uq_opportunity_weights_active"):
        asyncio.run(_activate_two())


@pytest.fixture(scope="module")
def owner_db(container_url: str) -> str:
    """A database owned — and migrated — by an ordinary ``NOSUPERUSER`` role.

    This is what a managed Postgres actually gives you, and it is the setup the
    review used to prove the seed silently wrote nothing: ``risk_profiles`` has
    ``FORCE ROW LEVEL SECURITY``, which filters the table owner too, so the
    system presets never landed while the script reported three rows seeded.
    The container's own superuser hides the bug completely.
    """
    url = asyncio.run(_create_owned_database(container_url))
    command.upgrade(alembic_config(url), "head")
    return url


async def _create_owned_database(admin_url: str) -> str:
    """Create ``OWNER_ROLE`` and a database it owns; return the URL to log in as it."""
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            await connection.execute(
                text(
                    f"DO $$ BEGIN CREATE ROLE {OWNER_ROLE} LOGIN NOSUPERUSER CREATEROLE "
                    f"PASSWORD '{OWNER_PASSWORD}'; "
                    f"EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
                )
            )
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": OWNER_DB}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{OWNER_DB}" OWNER {OWNER_ROLE}'))
    finally:
        await engine.dispose()

    split = urlsplit(admin_url)
    netloc = f"{OWNER_ROLE}:{OWNER_PASSWORD}@{split.hostname}:{split.port}"
    return urlunsplit((split.scheme, netloc, f"/{OWNER_DB}", "", ""))


def test_the_seed_writes_system_presets_under_a_nosuperuser_owner(owner_db: str) -> None:
    """The review's fifth finding, end to end.

    ``system_presets_manageable`` is granted to the migrating role, so the same
    script that wrote nothing before now writes — and re-writes — the three
    presets under an owner with no superuser powers at all.
    """
    _use(owner_db)
    seed = _load_script("seed")

    reported: dict[str, int] = asyncio.run(seed.seed())
    stored = asyncio.run(_row_counts(owner_db))

    assert reported["risk_profiles"] == 3
    assert stored["risk_profiles"] == 3, (
        "the seed reported rows it did not write: FORCE ROW LEVEL SECURITY filtered "
        "the table owner and the upsert matched nothing"
    )

    asyncio.run(seed.seed())
    assert asyncio.run(_row_counts(owner_db)) == stored


def test_prune_partitions_plans_per_timeframe(seed_db: str) -> None:
    """Retention is per timeframe, which is the whole point of the LIST level."""
    _use(seed_db)
    prune_partitions = _load_script("prune_partitions")
    now = datetime(2026, 9, 4, tzinfo=UTC)
    candidates = [
        ("candles_1m", "candles_1m_2025_01"),
        ("candles_1h", "candles_1h_2025_01"),
        ("candles_1m", "candles_1m_2026_09"),
        ("audit_logs", "audit_logs_2025_01"),
        ("system_events", "system_events_2025_01"),
    ]
    statements: list[tuple[str, str]] = prune_partitions.planned_statements(candidates, now)
    dropped = {name for name, sql in statements if sql.startswith("DROP TABLE")}

    assert dropped == {"candles_1m_2025_01", "system_events_2025_01"}
    assert [sql for name, sql in statements if name == "candles_1m_2025_01"] == [
        "ALTER TABLE candles_1m DETACH PARTITION candles_1m_2025_01",
        "DROP TABLE IF EXISTS candles_1m_2025_01",
    ]


def test_prune_partitions_drops_only_what_is_past_retention_and_is_idempotent(
    seed_db: str,
) -> None:
    _use(seed_db)
    prune_partitions = _load_script("prune_partitions")
    stale = "candles_1m_2025_01"

    async def _create_stale() -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(create_partition_sql("candles_1m", 2025, 1)))
        finally:
            await engine.dispose()

    asyncio.run(_create_stale())
    assert stale in asyncio.run(_partition_names(seed_db))

    planned: list[tuple[str, str]] = asyncio.run(prune_partitions.expired_partitions())
    dropped: list[str] = asyncio.run(prune_partitions.prune(planned))
    remaining = asyncio.run(_partition_names(seed_db))

    assert dropped == [stale]
    assert stale not in remaining
    # nothing inside its retention window went with it
    assert "candles_1h_2026_09" in remaining
    assert "audit_logs_2026_09" in remaining

    again: list[tuple[str, str]] = asyncio.run(prune_partitions.expired_partitions())
    assert again == []
    assert asyncio.run(_partition_names(seed_db)) == remaining


def test_prune_partitions_dry_run_touches_nothing(seed_db: str) -> None:
    _use(seed_db)
    prune_partitions = _load_script("prune_partitions")

    async def _create_stale() -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(create_partition_sql("candles_1m", 2025, 2)))
        finally:
            await engine.dispose()

    asyncio.run(_create_stale())
    before = asyncio.run(_partition_names(seed_db))
    planned: list[tuple[str, str]] = asyncio.run(prune_partitions.expired_partitions())

    assert {name for name, _ in planned} == {"candles_1m_2025_02"}
    assert asyncio.run(_partition_names(seed_db)) == before


def test_a_partition_of_the_same_name_in_another_schema_is_not_mistaken_for_ours(
    seed_db: str,
) -> None:
    """The census of what exists has to be scoped the way the statements are.

    ``CREATE TABLE IF NOT EXISTS audit_logs_2030_01 PARTITION OF audit_logs``
    resolves through ``search_path`` to ``public``. The "does it already exist?"
    query did not: it scanned ``pg_class`` for the bare ``relname``, so a
    same-named partition anywhere in the database — a staging copy, an
    extension's own table — made the script report a partition it had just
    created as already present. The daily job's output is the only signal an
    operator has that it is still keeping ahead of the clock.
    """
    _use(seed_db)
    create_partitions = _load_script("create_partitions")
    horizon = datetime(2030, 1, 1, tzinfo=UTC)

    async def _shadow(sql: str) -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(sql))
        finally:
            await engine.dispose()

    asyncio.run(_shadow("CREATE SCHEMA IF NOT EXISTS shadow"))
    try:
        asyncio.run(
            _shadow(
                "CREATE TABLE shadow.audit_logs (created_at timestamptz NOT NULL) "
                "PARTITION BY RANGE (created_at)"
            )
        )
        asyncio.run(
            _shadow(
                "CREATE TABLE shadow.audit_logs_2030_01 PARTITION OF shadow.audit_logs "
                "FOR VALUES FROM ('2030-01-01') TO ('2030-02-01')"
            )
        )
        groups = create_partitions.planned_groups(0, horizon)
        created: list[str] = asyncio.run(create_partitions.ensure_partitions(groups))
    finally:
        asyncio.run(_shadow("DROP SCHEMA shadow CASCADE"))

    assert "audit_logs_2030_01" in created
    assert "audit_logs_2030_01" in asyncio.run(_partition_names(seed_db))


def test_one_parent_failing_does_not_discard_the_partitions_of_the_others(
    seed_db: str,
) -> None:
    """One transaction per partitioned parent, not one for the whole run.

    A single transaction over every parent holds an ``ACCESS EXCLUSIVE`` lock on
    each of them until the last statement commits — so the daily job blocks
    writes to ``audit_logs`` while it works through ``candles`` — and any failure
    throws away every partition the run had already created. Here the last
    parent's group is made to fail: everything before it must still be committed,
    and its own work must be rolled back whole.
    """
    _use(seed_db)
    create_partitions = _load_script("create_partitions")
    horizon = datetime(2031, 1, 1, tzinfo=UTC)

    groups: list[tuple[str, list[tuple[str, str]]]] = create_partitions.planned_groups(0, horizon)
    assert len(groups) > 1, "there is only one partitioned parent; the split cannot be observed"
    first_names = {name for name, _sql in groups[0][1]}
    last_names = {name for name, _sql in groups[-1][1]}
    groups[-1][1].append(
        (
            "unreachable",
            "CREATE TABLE IF NOT EXISTS orphan_child PARTITION OF no_such_parent "
            "FOR VALUES FROM ('2031-01-01') TO ('2031-02-01')",
        )
    )

    before = asyncio.run(_partition_names(seed_db))
    with pytest.raises(ProgrammingError):
        asyncio.run(create_partitions.ensure_partitions(groups))
    after = asyncio.run(_partition_names(seed_db))

    assert first_names <= after, "an earlier parent's partitions were rolled back with the failure"
    assert first_names - before, "the first group created nothing; the horizon proves nothing"
    assert last_names & after == last_names & before, "the failing group was left half applied"
