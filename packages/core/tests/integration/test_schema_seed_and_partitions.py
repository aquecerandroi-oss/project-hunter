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
from decimal import Decimal
from types import ModuleType
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_core.db.models import create_partition_sql
from hunter_indicators.features import default_definitions_rows

from .conftest import SCRIPTS_DIR, alembic_config, async_engine, create_database

pytestmark = pytest.mark.integration

OWNER_ROLE = "hunter_owner_probe"
OWNER_PASSWORD = "FAKEownerpw"
OWNER_DB = "hunter_owned"

FROZEN_FEATURE = "spread_pct"
"""The definition the freeze test tampers with, then puts back."""

ACTIVATED_KEY = "momentum"
"""The strategy whose v1 the freeze test activates, then puts back."""

FROZEN_CODE_REF = f"hunter_core.strategies.{ACTIVATED_KEY}_v1@sha256:{'ab' * 32}"
"""What activation writes over the seed's registry placeholder.

Shaped the way ``hunter_strategy_worker.code_ref.version_code_ref`` writes it —
the per-version digest, not the ``hunter_indicators.strategies.*`` placeholder
the seed ships — because the difference between the two is the whole bug.
"""

SEEDED_TABLES = (
    "exchanges",
    "strategies",
    "strategy_versions",
    "plan_entitlements",
    "feature_flags",
    "risk_profiles",
    "feature_definitions",
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
    """Load ``infra/scripts/<name>.py`` the way running it as a script would.

    ``seed.py`` imports its data from the sibling ``seed_reference`` module (the
    two split when the M2 catalogue pushed the script past the 350-line budget).
    Running ``python infra/scripts/seed.py`` puts that directory on ``sys.path``
    automatically; loading the file by path does not, so it is added here — the
    same surgery ``conftest.alembic_config`` does for ``infra/migrations``.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
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
                value = await connection.scalar(
                    text(f"SELECT count(*) FROM {table}")  # noqa: S608  # nosec B608 -- table name from a frozen constant, not user input
                )
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
    assert counts_after_first["feature_definitions"] == len(default_definitions_rows()) == 28
    assert counts_after_first["opportunity_weights"] == 2


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


def test_the_seeded_catalogue_is_exactly_the_feature_registry(seed_db: str) -> None:
    """``feature_definitions`` is derived from ``hunter_indicators``, not retyped.

    The catalogue and the engine drifted the moment they were written twice: the
    hand-written seed shipped ``volatility``/``volume_relative`` and an
    ``inputs`` vocabulary of ``book_20``/``candles_1m``, while the registry that
    actually computes the numbers publishes ``atr_14_pct``/``relative_volume_5m``
    reading ``book:20``/``candles:1m`` — 20 of 28 keys orphaned on one side or
    the other. Every ``feature_snapshots`` row names a ``feature_set_version``
    hashed from these identities, so a catalogue that is not the registry's is a
    table describing an engine nobody ran. This asserts the whole row, not just
    the names: category, version, inputs and parameters all decide the hash.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    expected = {
        row["name"]: (
            row["version"],
            row["category"].value,
            sorted(row["inputs"]),
            row["parameters"],
            row["description"],
        )
        for row in default_definitions_rows()
    }

    async def _catalogue() -> dict[str, tuple[Any, ...]]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT name, version, category::text, inputs, parameters, description "
                        "FROM feature_definitions"
                    )
                )
                return {row[0]: (row[1], row[2], sorted(row[3]), row[4], row[5]) for row in result}
        finally:
            await engine.dispose()

    stored = asyncio.run(_catalogue())
    assert sorted(stored) == sorted(expected), "the seeded keys are not the registry's keys"
    assert len(stored) == 28
    assert stored == expected


def test_reseeding_the_catalogue_rewrites_no_row(seed_db: str) -> None:
    """Running the seed twice is a no-op — no row rewritten, not merely recounted.

    ``xmin`` is the witness. An upsert that writes the same values back still
    gives every row a new version, and a row count cannot see it; a definition
    rewritten under the same ``(name, version)`` is exactly what must never
    happen, because the snapshots that named that identity were produced by the
    stored one.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _row_versions() -> dict[str, str]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text("SELECT name, id::text || ':' || xmin::text FROM feature_definitions")
                )
                return {row[0]: row[1] for row in result}
        finally:
            await engine.dispose()

    before = asyncio.run(_row_versions())
    asyncio.run(seed.seed())
    after = asyncio.run(_row_versions())

    assert len(before) == 28
    assert before == after, "reseeding rewrote feature_definitions rows"


def test_the_seed_refuses_to_rewrite_a_published_feature_definition(seed_db: str) -> None:
    """A published ``(name, version)`` is frozen, like a weight vector (§17.8).

    ``feature_snapshots.feature_set_version`` is a hash of key, version,
    category, inputs and parameters, so changing any of them under a name that
    already exists makes the catalogue lie about every snapshot computed with
    it. The registry answers a real formula change by bumping ``version``; the
    seed's job when the stored identity differs is to stop, not to overwrite.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _tamper() -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE feature_definitions SET inputs = :inputs WHERE name = :name"),
                    {"inputs": ["book:20", "ghost:99"], "name": FROZEN_FEATURE},
                )
        finally:
            await engine.dispose()

    async def _stored_inputs() -> list[str]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                value = await connection.scalar(
                    text("SELECT inputs FROM feature_definitions WHERE name = :name"),
                    {"name": FROZEN_FEATURE},
                )
        finally:
            await engine.dispose()
        return list(value or [])

    asyncio.run(_tamper())
    try:
        with pytest.raises(SystemExit, match="never rewritten"):
            asyncio.run(seed.seed())
        assert asyncio.run(_stored_inputs()) == ["book:20", "ghost:99"], (
            "the refused seed still overwrote the definition"
        )
    finally:
        asyncio.run(_restore_shipped_catalogue(seed_db))


async def _restore_shipped_catalogue(url: str) -> None:
    """Undo the local edit so later tests seed against the shipped catalogue."""
    shipped = next(row for row in default_definitions_rows() if row["name"] == FROZEN_FEATURE)
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE feature_definitions SET inputs = :inputs WHERE name = :name"),
                {"inputs": list(shipped["inputs"]), "name": FROZEN_FEATURE},
            )
    finally:
        await engine.dispose()


async def _activate_v1(url: str, key: str, code_ref: str) -> None:
    """Do to the row exactly what ``infra/scripts/activate_strategy_version.py`` does.

    Same three columns, same order, same ``WHERE activated_at IS NULL`` guard:
    the point is a row frozen the way ops freezes one, not a row hand-built to
    make the seed fail.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE strategy_versions SET status = 'active', activated_at = now(), "
                    "code_ref = :code_ref WHERE version = 'v1' AND activated_at IS NULL "
                    "AND strategy_id = (SELECT id FROM strategies WHERE key = :key)"
                ),
                {"code_ref": code_ref, "key": key},
            )
    finally:
        await engine.dispose()


async def _deactivate_v1(url: str, key: str) -> None:
    """Give the module's shared database back — through a door ops does not have.

    ``SET activated_at = NULL`` is one of the changes ``0002``'s trigger refuses
    on purpose (§16.1), so the restore switches the trigger off for its own
    length. Written out loud, and only here: nothing in ``seed.py`` may do this,
    and leaving an activated row behind would quietly change what every test
    after this one is running against.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "ALTER TABLE strategy_versions DISABLE TRIGGER strategy_versions_freeze_update"
                )
            )
            await connection.execute(
                text(
                    "UPDATE strategy_versions SET status = 'draft', activated_at = NULL, "
                    "code_ref = :code_ref WHERE version = 'v1' AND strategy_id = "
                    "(SELECT id FROM strategies WHERE key = :key)"
                ),
                {"code_ref": f"hunter_indicators.strategies.{key}_v1", "key": key},
            )
            await connection.execute(
                text("ALTER TABLE strategy_versions ENABLE TRIGGER strategy_versions_freeze_update")
            )
    finally:
        await engine.dispose()


async def _frozen_version(url: str, key: str) -> tuple[Any, ...]:
    """The activated row, ``xmin`` included, so a rewrite cannot hide as a re-count."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT xmin::text, code_ref, status::text, activated_at "
                    "FROM strategy_versions WHERE version = 'v1' AND strategy_id = "
                    "(SELECT id FROM strategies WHERE key = :key)"
                ),
                {"key": key},
            )
            return tuple(result.one())
    finally:
        await engine.dispose()


async def _xmins(url: str, table: str, label: str) -> dict[str, str]:
    """``{natural key: xmin}`` for a whole table — the M2 seeds' no-rewrite witness."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(f"SELECT {label}::text, xmin::text FROM {table}")  # noqa: S608  # nosec B608 -- both names are frozen constants in this module, not user input
            )
            return {row[0]: row[1] for row in result}
    finally:
        await engine.dispose()


def test_the_seed_never_touches_an_activated_strategy_version(
    seed_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The seed stays idempotent against a database that has activated a version.

    The HIGH reproduced on the VPS: after the first activation the seed still
    upserted ``code_ref`` back to the registry placeholder, ``0002``'s freeze
    trigger refused the change — correctly, that is what it is for — and because
    the whole seed is one transaction, all eight reference tables rolled back
    with it. Not "strategy_versions was skipped": *nothing was seeded at all*,
    on every deploy from then on.

    The activated row is the truth (§16.1). A registry that has moved on is not
    a seed error and is not the seed's to resolve — that is
    ``activate_strategy_version.py --supersede``, an ops decision — so the seed
    leaves the row exactly as it is, says on stdout that it did, and finishes
    seeding everything else. ``xmin`` is the witness: an upsert writing the same
    values back still makes a new row version, and a row count cannot see it.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())
    counts_before = asyncio.run(_row_counts(seed_db))
    asyncio.run(_activate_v1(seed_db, ACTIVATED_KEY, FROZEN_CODE_REF))
    try:
        frozen_before = asyncio.run(_frozen_version(seed_db, ACTIVATED_KEY))
        catalogue_before = asyncio.run(_xmins(seed_db, "feature_definitions", "name"))
        weights_before = asyncio.run(_xmins(seed_db, "opportunity_weights", "version"))
        assert frozen_before[1] == FROZEN_CODE_REF, "the activation did not take"

        first: dict[str, int] = asyncio.run(seed.seed())
        capsys.readouterr()
        second: dict[str, int] = asyncio.run(seed.seed())
        note = capsys.readouterr().out

        counts_after = asyncio.run(_row_counts(seed_db))
        assert first == second == counts_after == counts_before, (
            "a frozen version stopped the seed from seeding the other seven tables"
        )
        assert asyncio.run(_frozen_version(seed_db, ACTIVATED_KEY)) == frozen_before, (
            "the seed rewrote an activated strategy_version"
        )
        assert asyncio.run(_xmins(seed_db, "feature_definitions", "name")) == catalogue_before
        assert asyncio.run(_xmins(seed_db, "opportunity_weights", "version")) == weights_before
        assert FROZEN_CODE_REF in note, "the seed did not report the frozen row it left alone"
        assert "supersede" in note, "the note does not say how the registry is meant to move on"
    finally:
        asyncio.run(_deactivate_v1(seed_db, ACTIVATED_KEY))


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
    reactivated the shipped version underneath whatever an operator had switched
    to. With the partial unique index on ``is_active`` it would not even fail
    loudly — it would fail the deploy.

    Retargeted at v2 by T2.1: from ``0003`` on, v2 is the active profile, so v2
    is the version an operator could retire. The seed writes ``is_active``
    exactly once, on the run that *creates* the active version's row; by the time
    this test runs that row exists, which is why the promotion cannot come back
    and walk over the rollback below.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _retire_then_reseed() -> tuple[bool, bool]:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE opportunity_weights SET is_active = false WHERE version = 'v2'")
                )
        finally:
            await engine.dispose()
        await seed.seed()
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                active = await connection.scalar(
                    text("SELECT is_active FROM opportunity_weights WHERE version = 'v2'")
                )
                weights = await connection.scalar(
                    text(
                        "SELECT weights -> 'components' ? 'momentum' "
                        "FROM opportunity_weights WHERE version = 'v2'"
                    )
                )
        finally:
            await engine.dispose()
        return bool(active), bool(weights)

    try:
        still_active, weights_refreshed = asyncio.run(_retire_then_reseed())
        assert still_active is False, "re-seeding reactivated a version an operator had retired"
        assert weights_refreshed is True, "the seed lost the published weight vector"
    finally:
        # This module shares one seeded database across its tests, and the point
        # of this one is to leave a profile retired — which is exactly the state
        # the next test must not inherit.
        asyncio.run(_restore_shipped_profile(seed_db))


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


def test_the_seed_ships_v2_active_and_retires_v1(seed_db: str) -> None:
    """The M2 profile is the live one, and v1 survives as history.

    ``opportunity_weights`` is versioned precisely so a score can name the vector
    that produced it, so retiring v1 by deleting or rewriting it would erase what
    every M1-era row meant. It stays, inactive, in its original flat shape — v2
    is nested because the joint decision puts the stage thresholds under
    ``weights["stage"]``, and the shape is read per version, never guessed.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _profiles() -> list[tuple[str, bool, bool]]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text(
                        "SELECT version, is_active, weights ? 'components' "
                        "FROM opportunity_weights ORDER BY version"
                    )
                )
                return [(row[0], bool(row[1]), bool(row[2])) for row in result]
        finally:
            await engine.dispose()

    assert asyncio.run(_profiles()) == [("v1", False, False), ("v2", True, True)]


def test_the_v2_component_weights_sum_to_the_agreed_budget(seed_db: str) -> None:
    """``sum(w_i) = 0.90``, Agent Consensus at zero.

    The joint decision fixes the arithmetic even where it leaves the individual
    weights to T2.4: the remaining 0.10 of the 1.00 budget is the *signed*
    Early-Movement term, ``score = clip(sum(w_i * c_i) + 10 * e, 0, 100)`` with
    ``e in {-1, 0, +1}``. A vector summing to 0.95 would quietly hand every
    component a bonus and put the pre-clip ceiling above 100.

    Summed as ``Decimal`` on purpose: the values are stored as JSON strings
    because 0.05 has no exact binary float, and adding them as floats here would
    be the very bug that storage choice exists to avoid.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _components() -> dict[str, str]:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                weights = await connection.scalar(
                    text(
                        "SELECT weights -> 'components' FROM opportunity_weights "
                        "WHERE version = 'v2'"
                    )
                )
                return cast(dict[str, str], weights)
        finally:
            await engine.dispose()

    components = asyncio.run(_components())
    assert sum(Decimal(value) for value in components.values()) == Decimal("0.90")
    assert Decimal(components["agent_consensus"]) == Decimal("0")


def test_a_live_profile_the_seed_does_not_ship_is_left_alone(seed_db: str) -> None:
    """The promotion is one-shot, and it never demotes a stranger.

    If some future v3 is live and the v2 row has been removed, the seed recreates
    v2 **inactive**: taking the live profile away from a running scorer is not a
    decision a deploy script gets to make. The only version it may retire is the
    one it replaced (``seed_reference.PROMOTED_FROM``).
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _install_v3_then_reseed() -> tuple[str | None, bool]:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("DELETE FROM opportunity_weights WHERE version = 'v2'")
                )
                await connection.execute(
                    text(
                        "INSERT INTO opportunity_weights (id, version, weights, is_active) "
                        "VALUES (gen_random_uuid(), 'v3', '{}'::jsonb, true)"
                    )
                )
        finally:
            await engine.dispose()
        await seed.seed()
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                live = await connection.scalar(
                    text("SELECT version FROM opportunity_weights WHERE is_active")
                )
                present = await connection.scalar(
                    text("SELECT true FROM opportunity_weights WHERE version = 'v2'")
                )
        finally:
            await engine.dispose()
        return live, bool(present)

    try:
        live, v2_present = asyncio.run(_install_v3_then_reseed())
        assert live == "v3", "the seed demoted a profile it does not ship"
        assert v2_present, "the seed must still ensure its own version exists"
    finally:
        asyncio.run(_restore_shipped_profile(seed_db))


async def _restore_shipped_profile(url: str) -> None:
    """Put the shared seed database back the way the other tests expect it.

    Deactivate first, then activate: the partial unique index allows exactly one
    live version, so activating v2 while another test's probe is still active
    fails — the same ordering the seed's own promotion has to obey.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM opportunity_weights WHERE version = 'v3'"))
            await connection.execute(
                text("UPDATE opportunity_weights SET is_active = false WHERE is_active")
            )
            await connection.execute(
                text("UPDATE opportunity_weights SET is_active = true WHERE version = 'v2'")
            )
    finally:
        await engine.dispose()


def test_the_seed_refuses_to_rewrite_a_published_weight_vector(seed_db: str) -> None:
    """A weight version is frozen once published, exactly like a strategy version.

    Every opportunity records ``weights_version``, so rewriting the numbers under
    an existing name changes the meaning of scores already explained by it. The
    concrete regression: T2.4 ratifies v2 and stores ``components_frozen: true``,
    and the next deploy — every deploy runs this script — quietly puts ``false``
    back. The seed has to stop instead, and say to publish a new version.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _ratify_v2() -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "UPDATE opportunity_weights "
                        "SET weights = jsonb_set(weights, '{components_frozen}', 'true') "
                        "WHERE version = 'v2'"
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_ratify_v2())
    try:
        with pytest.raises(SystemExit, match="never rewritten"):
            asyncio.run(seed.seed())

        async def _still_ratified() -> bool:
            engine = async_engine(seed_db)
            try:
                async with engine.connect() as connection:
                    return bool(
                        await connection.scalar(
                            text(
                                "SELECT weights -> 'components_frozen' = 'true'::jsonb "
                                "FROM opportunity_weights WHERE version = 'v2'"
                            )
                        )
                    )
            finally:
                await engine.dispose()

        assert asyncio.run(_still_ratified()), "the refused seed still overwrote the vector"
    finally:
        asyncio.run(_reset_shipped_weights(seed_db))


def test_the_seed_does_not_promote_a_version_it_did_not_create(seed_db: str) -> None:
    """Only the run whose ``INSERT`` created the row may promote it.

    Astra's interleaving: the seed decides "v2 is missing", an operator stages v2
    inactive on purpose while keeping v1 live, and the seed then finds a conflict
    and promotes anyway — overriding a deliberate operational choice. Deciding
    from ``ON CONFLICT DO NOTHING ... RETURNING`` instead of an earlier ``SELECT``
    is what makes that impossible, and this is the deterministic form of that
    race: the row already exists when the seed runs, so the seed must not touch
    ``is_active`` at all.
    """
    _use(seed_db)
    seed = _load_script("seed")
    asyncio.run(seed.seed())

    async def _stage_v2_inactive_with_v1_live() -> None:
        engine = async_engine(seed_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text("UPDATE opportunity_weights SET is_active = false WHERE version = 'v2'")
                )
                await connection.execute(
                    text("UPDATE opportunity_weights SET is_active = true WHERE version = 'v1'")
                )
        finally:
            await engine.dispose()

    async def _live_version() -> str | None:
        engine = async_engine(seed_db)
        try:
            async with engine.connect() as connection:
                return await connection.scalar(
                    text("SELECT version FROM opportunity_weights WHERE is_active")
                )
        finally:
            await engine.dispose()

    asyncio.run(_stage_v2_inactive_with_v1_live())
    try:
        asyncio.run(seed.seed())
        assert asyncio.run(_live_version()) == "v1", (
            "the seed promoted a version it did not create, overriding an operator"
        )
    finally:
        asyncio.run(_restore_shipped_profile(seed_db))


async def _reset_shipped_weights(url: str) -> None:
    """Undo a local edit to a weight vector so later tests see the shipped one."""
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE opportunity_weights "
                    "SET weights = weights - 'components_frozen' "
                    "  || jsonb_build_object('components_frozen', false) "
                    "WHERE version = 'v2'"
                )
            )
    finally:
        await engine.dispose()
