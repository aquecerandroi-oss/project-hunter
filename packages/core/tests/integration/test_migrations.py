"""Every migration applies, reverses, re-applies and matches the models.

Runs in its own database inside the session's Postgres container, so the
``downgrade base`` here cannot pull the schema out from under the other tests.

Anything that drives Alembic is a **sync** test: ``env.py`` calls
``asyncio.run``, which raises inside a running event loop.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Mapping
from datetime import UTC, datetime
from typing import cast

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.db.models import (
    Base,
    list_partition_name,
    list_partitioned_tables,
    partition_name,
    partitioned_tables,
)
from hunter_core.domain.enums import ALL_ENUMS
from hunter_core.domain.types import uuid7

from .conftest import alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

HEAD_REVISION = "0003_analysis"
"""The revision ``upgrade head`` must reach. Bumped by every new revision, on
purpose: it is the one place that notices a revision file that never ran."""

INITIAL_REVISION = "0001_initial_schema"
SHADOW_REVISION = "0002_shadow_lab"


def _frozen_enums() -> tuple[Mapping[str, tuple[str, ...]], ...]:
    """The per-revision frozen ``type -> labels`` mappings, oldest first."""
    enums = migration_ddl("enums")
    return (
        cast("Mapping[str, tuple[str, ...]]", enums.INITIAL_ENUMS),
        cast("Mapping[str, tuple[str, ...]]", enums.SHADOW_ENUMS),
        cast("Mapping[str, tuple[str, ...]]", enums.ANALYSIS_ENUMS),
    )


async def _enum_labels(url: str) -> dict[str, list[str]]:
    """Every enum type in ``public`` and its labels, in ``enumsortorder``."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT t.typname, e.enumlabel FROM pg_type t "
                    "JOIN pg_enum e ON e.enumtypid = t.oid "
                    "JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' ORDER BY t.typname, e.enumsortorder"
                )
            )
            labels: dict[str, list[str]] = {}
            for type_name, label in result:
                labels.setdefault(type_name, []).append(label)
    finally:
        await engine.dispose()
    return labels


@pytest.fixture(scope="module")
def cycle_db_url(container_url: str) -> str:
    return asyncio.run(create_database(container_url, "hunter_migration_cycle"))


@pytest.fixture(scope="module")
def upgraded(cycle_db_url: str) -> Iterator[str]:
    """``alembic upgrade head`` on a clean database — that it does not raise is
    the first assertion of this module.
    """
    command.upgrade(alembic_config(cycle_db_url), "head")
    yield cycle_db_url


@pytest_asyncio.fixture
async def engine(upgraded: str) -> AsyncIterator[AsyncEngine]:
    created = async_engine(upgraded)
    try:
        yield created
    finally:
        await created.dispose()


async def _revision(url: str) -> str | None:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return await connection.scalar(text("SELECT version_num FROM alembic_version"))
    finally:
        await engine.dispose()


_LEGACY_OUTCOMES: dict[str, str] = {
    # label -> the columns a 0001 database could have written
    "resolved": "(signal_id, result, exit_ts) VALUES (:id, 'target', now())",
    "entered": "(signal_id, entry_ts) VALUES (:id, now())",
    "waiting": "(signal_id) VALUES (:id)",
}

_CONTRADICTORY_OUTCOME = "(signal_id, result, exit_ts) VALUES (:id, 'open', now())"
"""Still open, and yet it left: no ``tracking_state`` follows from this row."""


async def _legacy_signals(connection: AsyncConnection, count: int) -> list[uuid.UUID]:
    """``count`` signals of one fresh strategy version on one fresh market."""
    strategy, version, exchange, market = uuid7(), uuid7(), uuid7(), uuid7()
    await connection.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, 'Legacy')"),
        {"id": strategy, "key": f"legacy-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:id, :strategy, 'v1')"
        ),
        {"id": version, "strategy": strategy},
    )
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Legacy')"),
        {"id": exchange, "code": f"legacy-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :exchange, 'BTCUSDT', 'perpetual')"
        ),
        {"id": market, "exchange": exchange},
    )
    signals = [uuid7() for _ in range(count)]
    for signal_id in signals:
        await connection.execute(
            text(
                "INSERT INTO agent_signals (id, strategy_version_id, market_id, "
                "params_hash, direction, confidence) "
                "VALUES (:id, :version, :market, 'legacy', 'long', 0.5)"
            ),
            {"id": signal_id, "version": version, "market": market},
        )
    return signals


async def _seed_legacy_outcomes(url: str) -> dict[str, uuid.UUID]:
    """One ``signal_outcomes`` row per shape ``0001`` could hold, keyed by label."""
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            signals = await _legacy_signals(connection, len(_LEGACY_OUTCOMES))
            ids = dict(zip(_LEGACY_OUTCOMES, signals, strict=True))
            for label, columns in _LEGACY_OUTCOMES.items():
                await connection.execute(
                    text(f"INSERT INTO signal_outcomes {columns}"),
                    {"id": ids[label]},
                )
    finally:
        await engine.dispose()
    return ids


async def _seed_contradictory_outcome(url: str) -> uuid.UUID:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            (signal_id,) = await _legacy_signals(connection, 1)
            await connection.execute(
                text(f"INSERT INTO signal_outcomes {_CONTRADICTORY_OUTCOME}"),
                {"id": signal_id},
            )
    finally:
        await engine.dispose()
    return signal_id


async def _delete_outcome(url: str, signal_id: uuid.UUID) -> None:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM signal_outcomes WHERE signal_id = :id"), {"id": signal_id}
            )
    finally:
        await engine.dispose()


async def _market(connection: AsyncConnection) -> uuid.UUID:
    """A fresh exchange and market, so each test owns its own rows."""
    exchange, market = uuid7(), uuid7()
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Legacy')"),
        {"id": exchange, "code": f"legacy-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :exchange, :symbol, 'perpetual')"
        ),
        {"id": market, "exchange": exchange, "symbol": f"BTC{uuid.uuid4().hex[:6].upper()}"},
    )
    return market


async def _seed_legacy_analysis(url: str) -> uuid.UUID:
    """One anomaly and one opportunity of the shape a ``0002`` database holds.

    Neither carries ``evaluation_state`` or ``stage`` — those columns do not
    exist yet at this point — which is exactly what makes them the rows ``0003``
    has to decide about.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            market = await _market(connection)
            await connection.execute(
                text(
                    "INSERT INTO anomalies (id, market_id, type, severity, confidence, status) "
                    "VALUES (:id, :market, 'VOLUME_SPIKE', 80.00, 0.9000, 'active')"
                ),
                {"id": uuid7(), "market": market},
            )
            await connection.execute(
                text(
                    "INSERT INTO opportunities "
                    "(id, market_id, direction, score, confidence, status) "
                    "VALUES (:id, :market, 'long', 55.00, 0.8000, 'WATCHING')"
                ),
                {"id": uuid7(), "market": market},
            )
    finally:
        await engine.dispose()
    return market


async def _seed_extended_opportunity(url: str) -> uuid.UUID:
    """An opportunity using a label only ``0003`` defines."""
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            market = await _market(connection)
            await connection.execute(
                text(
                    "INSERT INTO opportunities "
                    "(id, market_id, direction, score, confidence, status, stage) "
                    "VALUES (:id, :market, 'long', 88.00, 0.9000, 'EXTENDED', 'EXTENDED')"
                ),
                {"id": uuid7(), "market": market},
            )
    finally:
        await engine.dispose()
    return market


async def _delete_legacy_analysis(url: str, market_id: uuid.UUID) -> None:
    """Drop the market; ``ON DELETE CASCADE`` takes its analysis rows with it.

    The retention marker is set because the cascade reaches ``feature_baselines``,
    whose trigger refuses an undeclared ``DELETE`` however it arrives — a cascade
    is still a deletion. That is deliberate (a market is retired with
    ``delisted_at``, never hard-deleted by the application) and is recorded in
    DATABASE.md §17.2.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL app.baseline_retention = 'on'"))
            await connection.execute(text("DELETE FROM markets WHERE id = :id"), {"id": market_id})
    finally:
        await engine.dispose()


async def _seed_pending_outbox_event(url: str) -> uuid.UUID:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            event_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO outbox_events (event_id, stream) "
                    "VALUES (:id, 'opportunities.updated')"
                ),
                {"id": event_id},
            )
    finally:
        await engine.dispose()
    return event_id


async def _delete_outbox_event(url: str, event_id: uuid.UUID) -> None:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM outbox_events WHERE event_id = :id"), {"id": event_id}
            )
    finally:
        await engine.dispose()


async def _seed_opportunity_referencing_a_baseline(url: str) -> uuid.UUID:
    """A live baseline revision plus a score whose envelope names it."""
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            market = await _market(connection)
            baseline_id = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO feature_baselines "
                    "(id, market_id, feature, algo_version, hour_of_day, window_start, "
                    " window_end, available_at, median, mad, sample_size, expected_size, "
                    " distinct_days, coverage, source, sampling, input_fingerprint) "
                    "VALUES (:id, :market, 'volume_relative', 'mad_v1', 11, "
                    " :start, :end, :available, 1.0, 0.25, 400, 420, 7, 0.95, "
                    " 'live', 'per_minute', 'probe')"
                ),
                {
                    "id": baseline_id,
                    "market": market,
                    "start": datetime(2026, 8, 29, 11, tzinfo=UTC),
                    "end": datetime(2026, 9, 5, 11, 59, tzinfo=UTC),
                    "available": datetime(2026, 9, 5, 12, 1, tzinfo=UTC),
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO opportunities "
                    "(id, market_id, direction, score, confidence, status, feature_snapshot) "
                    "VALUES (:id, :market, 'long', 76.00, 0.9000, 'HOT', "
                    " CAST(:snapshot AS jsonb))"
                ),
                {
                    "id": uuid7(),
                    "market": market,
                    "snapshot": json.dumps({"baseline_ids": [str(baseline_id)]}),
                },
            )
    finally:
        await engine.dispose()
    return market


async def _seed_history_across_two_partitions(url: str) -> uuid.UUID:
    """One open episode with a sample in 2026-09 and another in 2026-10.

    ``opportunity_history`` is RANGE-partitioned by month, and the downgrade
    retypes ``status`` on the parent without ``ONLY`` — the assertion worth
    making is that the rows in *every* child survive that, with their values.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            market = await _market(connection)
            episode = uuid7()
            await connection.execute(
                text(
                    "INSERT INTO opportunities "
                    "(id, market_id, direction, score, confidence, status) "
                    "VALUES (:id, :market, 'long', 76.00, 0.9000, 'HOT')"
                ),
                {"id": episode, "market": market},
            )
            for month in (9, 10):
                await connection.execute(
                    text(
                        "INSERT INTO opportunity_history "
                        "(opportunity_id, ts, score, confidence, status) "
                        "VALUES (:id, :ts, 76.00, 0.9000, 'HOT')"
                    ),
                    {"id": episode, "ts": datetime(2026, month, 15, 12, tzinfo=UTC)},
                )
    finally:
        await engine.dispose()
    return market


async def _scalars(url: str, sql: str, params: dict[str, object]) -> list[str]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(sql), params)
            return [row[0] for row in result]
    finally:
        await engine.dispose()


async def _tracking_states(url: str, ids: dict[str, uuid.UUID]) -> dict[str, str]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT signal_id, tracking_state FROM signal_outcomes "
                    "WHERE signal_id = ANY(:ids)"
                ),
                {"ids": list(ids.values())},
            )
            by_id = {row[0]: row[1] for row in result}
    finally:
        await engine.dispose()
    return {label: by_id[signal_id] for label, signal_id in ids.items()}


async def _scalar_counts(url: str) -> tuple[int, int]:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.scalar(
                text("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
            )
            enums = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE n.nspname = 'public' AND t.typtype = 'e'"
                )
            )
    finally:
        await engine.dispose()
    return int(tables or 0), int(enums or 0)


async def test_upgrade_head_reaches_the_latest_revision(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == HEAD_REVISION


async def test_every_table_in_the_metadata_exists(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        present = {row[0] for row in result}
    missing = set(Base.metadata.tables) - present
    assert not missing, f"declared in the models but absent from the database: {missing}"


async def test_every_enum_type_exists_with_the_expected_labels(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT t.typname, e.enumlabel FROM pg_type t "
                "JOIN pg_enum e ON e.enumtypid = t.oid "
                "JOIN pg_namespace n ON n.oid = t.typnamespace "
                "WHERE n.nspname = 'public' ORDER BY t.typname, e.enumsortorder"
            )
        )
        actual: dict[str, list[str]] = {}
        for type_name, label in result:
            actual.setdefault(type_name, []).append(label)

    expected = {name: [member.value for member in cls] for name, cls in ALL_ENUMS.items()}
    assert actual == expected


async def test_every_partitioned_parent_has_its_initial_partitions(engine: AsyncEngine) -> None:
    partitions = migration_ddl("partitions")
    initial_months: tuple[tuple[int, int], ...] = partitions.INITIAL_MONTHS
    frozen_range: tuple[str, ...] = partitions.PARTITIONED_TABLES
    frozen_list: tuple[tuple[str, tuple[str, ...], str], ...] = partitions.LIST_PARTITIONED_TABLES

    assert set(frozen_range) == set(partitioned_tables()), (
        "a model gained or lost a RANGE postgresql_partition_by without a "
        "migration updating ddl.partitions.PARTITIONED_TABLES"
    )
    assert {name: (values, key) for name, values, key in frozen_list} == {
        name: (values, key) for name, (_column, values, key) in list_partitioned_tables().items()
    }, (
        "a model gained or lost a LIST postgresql_partition_by without a "
        "migration updating ddl.partitions.LIST_PARTITIONED_TABLES"
    )

    async with engine.connect() as connection:
        result = await connection.execute(
            text("SELECT relname FROM pg_class WHERE relispartition AND relkind IN ('r', 'p')")
        )
        present = {row[0] for row in result}

    expected = {
        partition_name(table, year, month)
        for table in frozen_range
        for year, month in initial_months
    }
    for parent, values, _key in frozen_list:
        for value in values:
            intermediate = list_partition_name(parent, value)
            # the timeframe level is itself a partition, and partitioned in turn
            expected.add(intermediate)
            expected |= {
                partition_name(intermediate, year, month) for year, month in initial_months
            }
    assert expected <= present


def test_every_enum_type_belongs_to_exactly_one_revision(upgraded: str) -> None:
    """The frozen per-revision enum tuples still partition ``ALL_ENUMS``.

    ``ddl/enums.py`` used to iterate ``ALL_ENUMS`` live, so adding a type for a
    new revision made ``0001`` create it retroactively and the new revision fail
    with "type already exists". The tuples are frozen now; this is what keeps
    them honest, exactly like the grant-class test does for tables.
    """
    classified = [name for mapping in _frozen_enums() for name in mapping]
    assert len(classified) == len(set(classified)), "an enum type is owned by two revisions"
    assert set(classified) == set(ALL_ENUMS), (
        "an enum was added to ALL_ENUMS without a revision claiming it in ddl/enums.py"
    )


def test_the_new_revision_reverses_and_re_applies(upgraded: str) -> None:
    """``downgrade -1`` then ``upgrade head`` for the head revision alone.

    Cheaper than the full ``downgrade base`` below and much more specific: it is
    the exact operation an operator runs when a deploy has to be rolled back.
    """
    config = alembic_config(upgraded)

    command.downgrade(config, "-1")
    tables, _enums = asyncio.run(_scalar_counts(upgraded))
    assert asyncio.run(_revision(upgraded)) != HEAD_REVISION
    assert tables > 1, "downgrading one revision must not empty the schema"

    command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0002_upgrades_a_database_that_already_has_rows(upgraded: str) -> None:
    """``0002`` on a populated ``0001``, not only on an empty schema.

    Raised by Astra's review of S0: ``signal_outcomes.tracking_state`` arrives
    with the column default ``pending_entry``, so an outcome that had already
    resolved (``result = 'target'``) would violate
    ``ck_signal_outcomes_tracking_state_matches_result`` the moment the CHECK is
    added, and the upgrade would abort — on every database except an empty one.
    The revision backfills from columns that already exist; this proves it.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, INITIAL_REVISION)
    legacy = asyncio.run(_seed_legacy_outcomes(upgraded))

    command.upgrade(config, "head")

    states = asyncio.run(_tracking_states(upgraded, legacy))
    assert states == {"resolved": "terminal", "entered": "active", "waiting": "pending_entry"}
    command.check(config)


def test_0002_refuses_a_contradictory_legacy_row(upgraded: str) -> None:
    """An outcome that is ``open`` *and* has an ``exit_ts`` stops the upgrade.

    Astra's second round: the backfill can derive a tracking state from a
    consistent row, but not from a self-contradictory one, and inventing
    ``pending_entry`` for a tracking that already left would hand a finished
    outcome back to the worker as one waiting to enter. The migration names the
    rows instead of guessing.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, INITIAL_REVISION)
    signal_id = asyncio.run(_seed_contradictory_outcome(upgraded))
    try:
        with pytest.raises(DBAPIError, match="cannot infer a tracking_state"):
            command.upgrade(config, "head")
        assert asyncio.run(_revision(upgraded)) != HEAD_REVISION, "the upgrade must not commit"
    finally:
        asyncio.run(_delete_outcome(upgraded, signal_id))
        command.upgrade(config, "head")


def test_alembic_check_reports_no_drift(upgraded: str) -> None:
    """The models and the migration describe the same schema."""
    command.check(alembic_config(upgraded))


def test_downgrade_base_then_upgrade_head(upgraded: str) -> None:
    """``downgrade()`` really reverses, and the schema can be rebuilt on top."""
    config = alembic_config(upgraded)

    command.downgrade(config, "base")
    tables, enums = asyncio.run(_scalar_counts(upgraded))
    assert tables == 1, "only alembic_version may survive a downgrade to base"
    assert enums == 0, "every enum type must be dropped by the downgrade"

    command.upgrade(config, "head")
    command.check(config)


def test_each_revision_creates_exactly_the_labels_it_froze(upgraded: str) -> None:
    """Stopping at ``0001`` or ``0002`` must reproduce *that* revision's enums.

    The follow-up DATABASE.md §16.5 left open. ``0002`` froze the type *names*
    per revision but still read the labels from ``ALL_ENUMS`` at migration time,
    so this revision — the first to add a member to an existing enum — would
    have changed what ``0001`` builds: a fresh ``upgrade 0001`` would have
    created an ``opportunity_status`` that already contained ``EXTENDED``, and
    ``0003``'s ``ADD VALUE`` would then have been adding a label that was
    already there.

    Order is asserted with the labels, from ``enumsortorder``: ``EXTENDED``
    lands before ``EXPIRED`` and the two detectors before ``SOCIAL_SPIKE``
    because the migration says ``BEFORE``, and the Python classes declare them
    in the same places. A member moved in one and not the other is drift this
    catches.
    """
    initial, shadow, analysis = _frozen_enums()
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, "base")

        command.upgrade(config, INITIAL_REVISION)
        after_initial = asyncio.run(_enum_labels(upgraded))
        assert after_initial == {name: list(v) for name, v in initial.items()}
        assert "EXTENDED" not in after_initial["opportunity_status"]
        assert "UNKNOWN" not in after_initial["market_regime"]

        command.upgrade(config, SHADOW_REVISION)
        after_shadow = asyncio.run(_enum_labels(upgraded))
        assert after_shadow == {
            name: list(v) for mapping in (initial, shadow) for name, v in mapping.items()
        }

        command.upgrade(config, "head")
        after_head = asyncio.run(_enum_labels(upgraded))
        assert after_head == {name: [m.value for m in cls] for name, cls in ALL_ENUMS.items()}
        assert set(analysis) <= set(after_head)
    finally:
        command.upgrade(config, "head")


def test_0003_upgrades_a_database_that_already_holds_analysis_rows(upgraded: str) -> None:
    """``0003`` on a populated ``0002``: the anomaly backfill and the new invariants.

    The interesting row is the pre-existing anomaly. ``ADD COLUMN ... DEFAULT
    'ok'`` writes ``ok`` into every row that already exists, and nobody ever
    checked the data quality behind those — they predate the detectors that set
    the column. The migration backfills them to ``unknown`` instead, which is
    the ``active + unknown`` state the joint decision defines as ineligible.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, "-1")
    market_id = asyncio.run(_seed_legacy_analysis(upgraded))
    try:
        command.upgrade(config, "head")

        states = asyncio.run(
            _scalars(
                upgraded,
                "SELECT evaluation_state::text FROM anomalies WHERE market_id = :market",
                {"market": market_id},
            )
        )
        assert states == ["unknown"], (
            "an anomaly that predates the M2 detectors was assumed to have been "
            "evaluated against good data"
        )
        stages = asyncio.run(
            _scalars(
                upgraded,
                "SELECT stage::text FROM opportunities WHERE market_id = :market",
                {"market": market_id},
            )
        )
        assert stages == ["NONE"], "a legacy opportunity was given a stage nobody computed"
        command.check(config)
    finally:
        asyncio.run(_delete_legacy_analysis(upgraded, market_id))
        command.upgrade(config, "head")


def test_0003_refuses_to_downgrade_while_a_new_enum_label_is_in_use(upgraded: str) -> None:
    """Postgres cannot drop an enum label, so the downgrade rebuilds the type —
    and a row that still says ``EXTENDED`` would lose its meaning in the cast.
    The guard names the rows instead of destroying them.
    """
    market_id = asyncio.run(_seed_extended_opportunity(upgraded))
    try:
        with pytest.raises(DBAPIError, match="opportunity_status label"):
            command.downgrade(alembic_config(upgraded), "-1")
        assert asyncio.run(_revision(upgraded)) == HEAD_REVISION, "the downgrade must not commit"
    finally:
        asyncio.run(_delete_legacy_analysis(upgraded, market_id))


def test_0003_refuses_to_downgrade_while_the_outbox_still_owes_a_publication(
    upgraded: str,
) -> None:
    """Reversing a schema is allowed; losing an obligation is not.

    A row with ``dispatched_at IS NULL`` is an event the system still owes. The
    downgrade drops ``outbox_events``; without this guard it would finish
    successfully, the deploy would look clean, and the event would simply never
    be published — the exact loss the outbox exists to make impossible.
    """
    event_id = asyncio.run(_seed_pending_outbox_event(upgraded))
    try:
        with pytest.raises(DBAPIError, match="outbox_events rows are still pending"):
            command.downgrade(alembic_config(upgraded), "-1")
        assert asyncio.run(_revision(upgraded)) == HEAD_REVISION, "the downgrade must not commit"
    finally:
        asyncio.run(_delete_outbox_event(upgraded, event_id))


def test_0003_refuses_to_downgrade_while_a_sample_still_names_a_baseline(
    upgraded: str,
) -> None:
    """An opportunity that survives its own evidence is worse than no downgrade.

    ``feature_baselines`` has no foreign key pointing at it — the ids live in the
    envelope — so nothing in the DDL stops the drop. The score would remain,
    still saying "this is why", pointing at a revision that no longer exists.
    """
    market = asyncio.run(_seed_opportunity_referencing_a_baseline(upgraded))
    try:
        with pytest.raises(DBAPIError, match="name a feature_baselines revision"):
            command.downgrade(alembic_config(upgraded), "-1")
        assert asyncio.run(_revision(upgraded)) == HEAD_REVISION, "the downgrade must not commit"
    finally:
        asyncio.run(_delete_legacy_analysis(upgraded, market))


def test_history_rows_in_two_partitions_survive_the_downgrade_and_upgrade(
    upgraded: str,
) -> None:
    """The enum rebuild retypes a partitioned column; the data has to come back.

    ``ALTER TABLE ... ALTER COLUMN TYPE`` without ``ONLY`` recurses into every
    child, and this is the round trip with rows in two of them — the cheap
    version of "we reversed the deploy and the score history is still there".
    """
    market = asyncio.run(_seed_history_across_two_partitions(upgraded))
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, "-1")
        command.upgrade(config, "head")

        rows = asyncio.run(
            _scalars(
                upgraded,
                "SELECT h.status::text FROM opportunity_history h "
                "JOIN opportunities o ON o.id = h.opportunity_id "
                "WHERE o.market_id = :market ORDER BY h.ts",
                {"market": market},
            )
        )
        assert rows == ["HOT", "HOT"], "a partitioned history row did not survive the round trip"
        stages = asyncio.run(
            _scalars(
                upgraded,
                "SELECT h.stage::text FROM opportunity_history h "
                "JOIN opportunities o ON o.id = h.opportunity_id "
                "WHERE o.market_id = :market ORDER BY h.ts",
                {"market": market},
            )
        )
        assert stages == ["NONE", "NONE"], "the re-added column did not take its default"
        command.check(config)
    finally:
        asyncio.run(_delete_legacy_analysis(upgraded, market))
        command.upgrade(config, "head")
