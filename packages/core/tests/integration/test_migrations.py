"""Every migration applies, reverses, re-applies and matches the models.

Runs in its own database inside the session's Postgres container, so the
``downgrade base`` here cannot pull the schema out from under the other tests.

Anything that drives Alembic is a **sync** test: ``env.py`` calls
``asyncio.run``, which raises inside a running event loop.
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Iterator, Mapping
from datetime import UTC, datetime
from decimal import Decimal
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

from .conftest import REPO_ROOT, alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

HEAD_REVISION = "0033_meme_operator_3"
"""The revision ``upgrade head`` must reach. Bumped by every new revision, on
purpose: it is the one place that notices a revision file that never ran.
``0033`` (T4.19) sits on ``0032_meme_activity`` (T4.2g), which sits on
``0031_meme_lab_ticks`` (T4.15), which sits on ``0030_meme_gate_v2`` (T4.16) —
those two were written in parallel on ``0029``."""

INITIAL_REVISION = "0001_initial_schema"
SHADOW_REVISION = "0002_shadow_lab"
ANALYSIS_REVISION = "0003_analysis"
OUTBOX_INDEX_REVISION = "0004_outbox_pending_index"
LOCK_GRANT_REVISION = "0005_baseline_lock_grant"
PAPER_WALLET_REVISION = "0006_paper_wallet"
PAPER_ROLES_REVISION = "0007_paper_roles"
PAPER_ROLES_2_REVISION = "0008_paper_roles_2"
PAPER_GEOMETRY_REVISION = "0009_paper_geometry"
STRATEGY_PURPOSE_REVISION = "0010_strategy_purpose"
STRATEGY_ACTIVATION_OWNER_REVISION = "0011_strategy_activation_owner"
REPLAY_RUNS_REVISION = "0013_replay_runs"
LAB_SIGNALS_INDEXES_REVISION = "0014_lab_signals_indexes"
RUNTIME_LOGIN_ROLE_REVISION = "0015_runtime_login_role"
EXCHANGE_STATUS_REVISION = "0016_exchange_status_planned"
ELIGIBILITY_POLICY_REVISION = "0017_eligibility_policy"
BREADTH_REVISION = "0019_market_breadth"
MEME_RADAR_REVISION = "0021_meme_radar"
"""Named because the ``0021`` tests reverse **0021**, and ``"-1"`` stopped meaning
that the day ``0022_meme_lab`` landed on top (the ``0019`` lesson, again)."""
MEME_LAB_REVISION = "0022_meme_lab"
"""The same lesson one revision later: the ``0022`` tests reverse **0022**, and
``"-1"`` stopped meaning that the day ``0023_meme_boards_trades`` landed."""
MEME_BOARDS_REVISION = "0023_meme_boards_trades"
"""And once more: the ``0023`` tests reverse **0023**, and ``"-1"`` stopped meaning
that the day ``0024_meme_graduation`` landed."""
MEME_GRADUATION_REVISION = "0024_meme_graduation"
"""And again: the ``0024`` tests reverse **0024**, and ``"-1"`` stopped meaning
that the day ``0025_meme_mayhem_denominator`` landed."""
MEME_MAYHEM_REVISION = "0025_meme_mayhem_denominator"
"""And again: the ``0025`` tests reverse **0025**, and ``"-1"`` stopped meaning
that the day ``0026_meme_lines`` landed."""
MEME_LINES_REVISION = "0026_meme_lines"
"""And again: the ``0026`` tests reverse **0026**, and ``"-1"`` stopped meaning
that the day ``0027_meme_wallets`` landed."""
MEME_WALLETS_REVISION = "0027_meme_wallets"
"""What reversing **0028** lands on — and where the ``0027`` tests stage the
database first, because ``"-1"`` stopped meaning 0027 the day 0028 landed."""
MEME_LIVE_REVISION = "0028_meme_live"
"""What reversing **0029** lands on (T4.11) — and where the ``0028`` tests must
stage first, because ``"-1"`` stopped meaning 0028 the day 0029 landed."""
MEME_MOONSHOT_REVISION = "0029_meme_moonshot"
"""What reversing **0030** lands on (T4.16) — and where the ``0029`` tests must
stage first, because ``"-1"`` stopped meaning 0029 the day 0030 landed."""
MEME_GATE_V2_REVISION = "0030_meme_gate_v2"
"""What reversing **0031** lands on (T4.15) — and where the ``0030`` tests must
stage first, because ``"-1"`` stopped meaning 0030 the day 0031 landed."""
MEME_LAB_TICKS_REVISION = "0031_meme_lab_ticks"
"""What reversing **0032** lands on (T4.2g) — and where the ``0031`` tests would
stage first, because ``"-1"`` stopped meaning 0031 the day 0032 landed."""
MEME_ACTIVITY_REVISION = "0032_meme_activity"
"""What reversing **0033** lands on (T4.19) — and where the ``0032`` tests would
stage first, because ``"-1"`` stopped meaning 0032 the day 0033 landed."""
"""Named for the same reason as the line below: the two ``0019`` tests are about
reversing **0019**, and ``"-1"`` stopped meaning that the day a revision landed on
top of it. They now stage the database at this revision first, exactly as every
older revision's tests already do."""

REPLAY_SLICE_REVISION = "0018_replay_runs_slice_markets"
"""Named because three tests below are about what reversing **0018** does.

``"-1"`` means "one step back from whatever the head is", which stopped meaning
0018 the day ``0019_market_breadth`` landed: a test whose subject follows the
head is a test that silently changes what it proves."""

_PENDING_PREDICATE = "dispatched_at IS NULL"
"""What makes an index a *pending* index, spelled out here rather than imported:
these tests exist to check ``ddl/outbox_index.py``, so they must not agree with
it by construction."""

_STAGING_SUFFIX = "_rebuilding"
"""The name ``0004`` builds under before renaming; nothing may survive with it."""


def _frozen_enums() -> tuple[Mapping[str, tuple[str, ...]], ...]:
    """The per-revision frozen ``type -> labels`` mappings, oldest first."""
    enums = migration_ddl("enums")
    return (
        cast("Mapping[str, tuple[str, ...]]", enums.INITIAL_ENUMS),
        cast("Mapping[str, tuple[str, ...]]", enums.SHADOW_ENUMS),
        cast("Mapping[str, tuple[str, ...]]", enums.ANALYSIS_ENUMS),
        cast("Mapping[str, tuple[str, ...]]", enums.PAPER_ENUMS),
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


async def _explain(url: str, sql: str, params: dict[str, object]) -> list[str]:
    """The plan for ``sql``, with sequential scans disabled for the statement.

    ``SET LOCAL enable_seqscan = off`` because the table is empty in this
    database and the planner would read three pages faster than any index: the
    question here is whether an index *can* serve the predicates, which is a
    property of the schema, not of how many rows happen to be in it.
    """
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("SET LOCAL enable_seqscan = off"))
            result = await connection.execute(text(f"EXPLAIN {sql}"), params)
            return [row[0] for row in result]
    finally:
        await engine.dispose()


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

    meme_range: tuple[str, ...] = migration_ddl("meme_radar").MEME_PARTITIONED_TABLES_0021
    boards_range: tuple[str, ...] = migration_ddl("meme_boards").MEME_PARTITIONED_TABLES_0023
    gate_range: tuple[str, ...] = migration_ddl("meme_gate_v2").MEME_PARTITIONED_TABLES_0030
    activity_range: tuple[str, ...] = migration_ddl("meme_activity").MEME_PARTITIONED_TABLES_0032
    assert set(frozen_range) | set(meme_range) | set(boards_range) | set(gate_range) | set(
        activity_range
    ) == set(partitioned_tables()), (
        "a model gained or lost a RANGE postgresql_partition_by without a "
        "migration updating ddl.partitions.PARTITIONED_TABLES (0001), "
        "ddl.meme_radar.MEME_PARTITIONED_TABLES_0021, "
        "ddl.meme_boards.MEME_PARTITIONED_TABLES_0023, "
        "ddl.meme_gate_v2.MEME_PARTITIONED_TABLES_0030 or "
        "ddl.meme_activity.MEME_PARTITIONED_TABLES_0032"
    )
    assert not set(frozen_range) & set(meme_range), "a parent is frozen in two revisions"
    assert not (set(frozen_range) | set(meme_range)) & set(boards_range), (
        "a parent is frozen in two revisions"
    )
    assert not (set(frozen_range) | set(meme_range) | set(boards_range)) & set(gate_range), (
        "a parent is frozen in two revisions"
    )
    assert not (set(frozen_range) | set(meme_range) | set(boards_range) | set(gate_range)) & set(
        activity_range
    ), "a parent is frozen in two revisions"
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

    meme_months: tuple[tuple[int, int], ...] = migration_ddl("meme_radar").MEME_INITIAL_MONTHS_0021
    boards_months: tuple[tuple[int, int], ...] = migration_ddl(
        "meme_boards"
    ).MEME_INITIAL_MONTHS_0023
    gate_months: tuple[tuple[int, int], ...] = migration_ddl(
        "meme_gate_v2"
    ).MEME_INITIAL_MONTHS_0030
    activity_months: tuple[tuple[int, int], ...] = migration_ddl(
        "meme_activity"
    ).MEME_INITIAL_MONTHS_0032
    expected = (
        {
            partition_name(table, year, month)
            for table in frozen_range
            for year, month in initial_months
        }
        | {
            partition_name(table, year, month)
            for table in meme_range
            for year, month in meme_months
        }
        | {
            partition_name(table, year, month)
            for table in boards_range
            for year, month in boards_months
        }
        | {
            partition_name(table, year, month)
            for table in gate_range
            for year, month in gate_months
        }
        | {
            partition_name(table, year, month)
            for table in activity_range
            for year, month in activity_months
        }
    )
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
    catches. ``0006`` is held to the same rule: ``paper_v1`` before ``custom``
    and the three v2 risk events in the order RISK_ENGINE.md §8 lists them.
    """
    initial, shadow, analysis, paper = _frozen_enums()
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
        assert set(paper) <= set(after_head)
        # ``0006`` adds four labels to types ``0001`` created; none of them may
        # exist before that revision runs, or the ``ADD VALUE`` is a no-op that
        # nobody notices and ``0001`` no longer describes what it builds.
        assert "paper_v1" not in after_initial["risk_preset"]
        assert "beta_missing" not in after_initial["risk_event_type"]
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
    # Named, not ``-1``: the head moved to ``0004`` and reversing one revision
    # would leave ``0003`` applied, making the seed below meaningless.
    command.downgrade(config, SHADOW_REVISION)
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
        config = alembic_config(upgraded)
        command.downgrade(config, ANALYSIS_REVISION)
        with pytest.raises(DBAPIError, match="opportunity_status label"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == ANALYSIS_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(alembic_config(upgraded), "head")
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
        config = alembic_config(upgraded)
        command.downgrade(config, ANALYSIS_REVISION)
        with pytest.raises(DBAPIError, match="outbox_events rows are still pending"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == ANALYSIS_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(alembic_config(upgraded), "head")
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
        config = alembic_config(upgraded)
        command.downgrade(config, ANALYSIS_REVISION)
        with pytest.raises(DBAPIError, match="name a feature_baselines revision"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == ANALYSIS_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(alembic_config(upgraded), "head")
        asyncio.run(_delete_legacy_analysis(upgraded, market))


async def _pending_index_defs(url: str) -> dict[str, str]:
    """``index name -> indexdef`` for every pending index the database holds.

    Discovered by the *predicate*, not by a hard-coded pair of names: a third
    queue added by a later revision has to show up here, because that is the
    whole point of the freeze tests below.
    """
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = 'public' "
                    "AND indexdef LIKE :predicate"
                ),
                {"predicate": f"%WHERE ({_PENDING_PREDICATE})%"},
            )
            return {name: definition for name, definition in rows}
    finally:
        await engine.dispose()


async def _pending_index_slots(url: str) -> set[tuple[str, str]]:
    """``(table, index)`` for every pending index — the live set the frozen
    per-revision tuples of ``ddl/outbox_index.py`` have to partition."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(
                text(
                    "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public' "
                    "AND indexdef LIKE :predicate"
                ),
                {"predicate": f"%WHERE ({_PENDING_PREDICATE})%"},
            )
            return {(table, index) for table, index in rows}
    finally:
        await engine.dispose()


async def _invalid_and_staging_indexes(url: str) -> tuple[list[str], list[str]]:
    """Indexes Postgres marked invalid, and staging names nobody renamed."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            invalid = list(
                await connection.scalars(
                    text(
                        "SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND NOT i.indisvalid"
                    )
                )
            )
            staging = list(
                await connection.scalars(
                    text(
                        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' "
                        "AND indexname LIKE :suffix"
                    ),
                    {"suffix": f"%{_STAGING_SUFFIX}"},
                )
            )
            return invalid, staging
    finally:
        await engine.dispose()


def _frozen_pending_indexes() -> tuple[tuple[tuple[str, str], ...], ...]:
    """The per-revision frozen ``(table, index)`` tuples, oldest first."""
    outbox_index = migration_ddl("outbox_index")
    return (cast("tuple[tuple[str, str], ...]", outbox_index.PENDING_INDEXES_0004),)


def test_every_pending_outbox_index_belongs_to_exactly_one_revision(upgraded: str) -> None:
    """The frozen per-revision tuples still partition the live pending indexes.

    Same trap as the enum one above (DATABASE.md §16.5), one shape down: while
    ``ddl/outbox_index.py`` exported a single *live* ``PENDING_INDEXES`` read at
    migration time, a ``0005`` that added a third queue and appended it to that
    list would make ``0004`` — which rebuilt two indexes when it ran — try to
    rebuild an index that does not exist yet, and fail on every clean database.
    Each revision names its own tuple; this is what keeps them honest.
    """
    claimed = [slot for frozen in _frozen_pending_indexes() for slot in frozen]
    assert len(claimed) == len(set(claimed)), "a pending index is owned by two revisions"
    assert set(claimed) == asyncio.run(_pending_index_slots(upgraded)), (
        "an outbox queue was added without a revision claiming its pending index"
    )


def test_0004_rebuilds_exactly_the_indexes_that_existed_when_it_was_written(
    upgraded: str,
) -> None:
    """At ``0003`` the database holds precisely what ``0004`` froze.

    This is the half of the freeze that catches the trap in the direction it
    actually happens: appending a future queue to ``PENDING_INDEXES_0004``
    instead of giving it its own tuple passes the partition test above and
    fails here, because at the revision ``0004`` runs against, that index has
    never been created.
    """
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, ANALYSIS_REVISION)
        frozen = cast(
            "tuple[tuple[str, str], ...]", migration_ddl("outbox_index").PENDING_INDEXES_0004
        )
        assert asyncio.run(_pending_index_slots(upgraded)) == set(frozen)
    finally:
        command.upgrade(config, "head")


def test_0004_leaves_no_invalid_or_staging_index_behind(upgraded: str) -> None:
    """``CREATE INDEX CONCURRENTLY`` is the one build that can succeed halfway.

    A failed concurrent build leaves an ``indisvalid = false`` index that the
    planner ignores and ``pg_indexes`` still lists, so "the index is there"
    proves nothing on its own. The revision also builds under a staging name
    before renaming, so a leftover staging index means a rename never happened.
    """
    invalid, staging = asyncio.run(_invalid_and_staging_indexes(upgraded))
    assert invalid == [], invalid
    assert staging == [], staging


def test_0004_keys_both_pending_indexes_on_the_drain_order(upgraded: str) -> None:
    """The dispatcher claims ``ORDER BY created_at, id``; the index must say so.

    Both queues together: they are shape-identical by design (DATABASE.md
    §16.4/§17.5) and the absorption copies rows between them, so an index that
    diverged would make one of the two silently slower.
    """
    definitions = asyncio.run(_pending_index_defs(upgraded))
    assert set(definitions) == {"ix_outbox_events_pending", "ix_shadow_outbox_pending"}
    for name, definition in definitions.items():
        assert "(created_at, id)" in definition, (name, definition)
        assert "(dispatched_at IS NULL)" in definition, (name, definition)


def test_0004_reverses_to_the_index_0002_and_0003_shipped(upgraded: str) -> None:
    """A rollback of this deploy must leave the queues findable, not indexless."""
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, ANALYSIS_REVISION)
        definitions = asyncio.run(_pending_index_defs(upgraded))
        assert set(definitions) == {"ix_outbox_events_pending", "ix_shadow_outbox_pending"}
        for name, definition in definitions.items():
            assert definition.endswith("btree (id) WHERE (dispatched_at IS NULL)"), (
                name,
                definition,
            )
    finally:
        command.upgrade(config, "head")


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
        command.downgrade(config, SHADOW_REVISION)
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


async def _table_privileges(url: str, role: str, table: str) -> set[str]:
    """Which of the four DML privileges ``role`` holds on ``table``, right now."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            held: set[str] = set()
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege(:role, :table, :privilege)"),
                    {"role": role, "table": table, "privilege": privilege},
                )
                if granted:
                    held.add(privilege)
            return held
    finally:
        await engine.dispose()


def _frozen_lock_tables() -> tuple[str, ...]:
    return cast("tuple[str, ...]", migration_ddl("baseline_lock").BASELINE_LOCK_TABLES_0005)


def test_0005_grants_the_row_lock_on_exactly_the_tables_it_froze(upgraded: str) -> None:
    """At head the worker may lock a baseline row; nothing else moved.

    ``UPDATE`` is granted for what PostgreSQL demands it for — a row mark is
    ``ACL_SELECT_FOR_UPDATE``, which *is* ``ACL_UPDATE`` — not because a
    revision became editable. Immutability is the ``feature_baselines_immutable``
    trigger, which refuses every ``UPDATE`` for every role including the owner,
    and is asserted in ``test_schema_analysis.py`` as the worker role itself.
    """
    frozen = _frozen_lock_tables()
    assert frozen, "0005 froze no table to grant"
    for table in frozen:
        held = asyncio.run(_table_privileges(upgraded, "hunter_worker", table))
        assert held == {"SELECT", "INSERT", "UPDATE", "DELETE"}, (table, held)


def test_0005_touches_no_table_0003_had_not_already_classified(upgraded: str) -> None:
    """A grant revision must not smuggle in an unclassified table.

    ``test_schema_privileges.test_the_grant_lists_cover_every_table_exactly_once``
    partitions the schema over the *app*-side classes, so a worker-side grant on
    a table nobody classified would slip past it. The frozen tuple therefore has
    to be a subset of what ``0003`` already owns.
    """
    analysis = migration_ddl("analysis")
    owned = set(cast("tuple[str, ...]", analysis.ANALYSIS_WORKER_APPEND_TABLES))
    assert set(_frozen_lock_tables()) <= owned, (
        "0005 grants on a table 0003 never classified; give it its own grant class"
    )


def test_0005_reverses_to_the_baseline_privileges_0003_shipped(upgraded: str) -> None:
    """Rolling back this deploy restores create-and-expire, not nothing.

    The downgrade revokes the single privilege rather than ``REVOKE ALL``: a
    database rolled back to ``0004`` must still be able to write and expire
    baselines, which is what ``0003`` granted. The scanner degrades again
    (BUG-1) — it probes at startup and says so — but it keeps running.
    """
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, OUTBOX_INDEX_REVISION)
        for table in _frozen_lock_tables():
            held = asyncio.run(_table_privileges(upgraded, "hunter_worker", table))
            assert held == {"SELECT", "INSERT", "DELETE"}, (table, held)
        assert asyncio.run(_revision(upgraded)) == OUTBOX_INDEX_REVISION
    finally:
        command.upgrade(config, "head")
    for table in _frozen_lock_tables():
        assert "UPDATE" in asyncio.run(_table_privileges(upgraded, "hunter_worker", table))
    command.check(config)


def test_0005_leaves_the_api_role_read_only_on_baselines(upgraded: str) -> None:
    """The grant is the worker's alone. ``hunter_app`` reads a baseline to
    explain a score and has never had a reason to write one."""
    for table in _frozen_lock_tables():
        held = asyncio.run(_table_privileges(upgraded, "hunter_app", table))
        assert held == {"SELECT"}, (table, held)


async def _write(url: str, statements: list[tuple[str, dict[str, object]]]) -> None:
    """Run statements as the owner, each with its own parameters."""
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            for statement, parameters in statements:
                await connection.execute(text(statement), parameters)
    finally:
        await engine.dispose()


def _tenant(url: str, slug: str, *, portfolios: int) -> dict[str, uuid.UUID]:
    """An organization, a workspace and ``portfolios`` principal paper wallets."""
    ids: dict[str, uuid.UUID] = {"org": uuid7(), "workspace": uuid7()}
    statements: list[tuple[str, dict[str, object]]] = [
        (
            "INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)",
            {"id": ids["org"], "slug": slug},
        ),
        (
            "INSERT INTO workspaces (id, organization_id, name, objective) "
            "VALUES (:id, :org, :slug, 'paper_trading')",
            {"id": ids["workspace"], "org": ids["org"], "slug": slug},
        ),
    ]
    for index in range(portfolios):
        key = f"portfolio_{index}"
        ids[key] = uuid7()
        statements.append(
            (
                "INSERT INTO portfolios (id, organization_id, workspace_id, name, type, "
                "initial_capital) VALUES (:id, :org, :ws, :name, 'paper', 20000)",
                {
                    "id": ids[key],
                    "org": ids["org"],
                    "ws": ids["workspace"],
                    "name": f"{slug}-{index}",
                },
            )
        )
    asyncio.run(_write(url, statements))
    return ids


def _drop_tenant(url: str, org: uuid.UUID) -> None:
    """Remove the probe tenant, declaring the teardown ``0006`` demands."""
    asyncio.run(
        _write(
            url,
            [
                ("SET LOCAL app.portfolio_teardown = 'on'", {}),
                ("DELETE FROM organizations WHERE id = :id", {"id": org}),
            ],
        )
    )


def test_0006_refuses_a_database_that_already_holds_two_principal_wallets(
    upgraded: str,
) -> None:
    """``0006`` cannot choose which of two wallets is the permanent one.

    The unique index is the directive's "no reset" in schema form, and on a
    database that already violates it there is no honest backfill: marking one of
    them ``is_arena`` is a decision about which history is the real one, and that
    is an operator's, not a migration's. ``0002``'s precedent, restated.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, LOCK_GRANT_REVISION)
    ids = _tenant(upgraded, f"twin-{uuid.uuid4().hex[:8]}", portfolios=2)
    try:
        with pytest.raises(DBAPIError, match="more than one principal paper wallet"):
            command.upgrade(config, "head")
        assert asyncio.run(_revision(upgraded)) != HEAD_REVISION, "the upgrade must not commit"
    finally:
        asyncio.run(
            _write(
                upgraded,
                [("DELETE FROM portfolios WHERE id = :id", {"id": ids["portfolio_1"]})],
            )
        )
        command.upgrade(config, "head")
        _drop_tenant(upgraded, ids["org"])
    command.check(config)


def _open_a_wallet(url: str, slug: str) -> dict[str, uuid.UUID]:
    """A tenant whose wallet is opened: risk state, FX observation and anchor."""
    ids = _tenant(url, slug, portfolios=1)
    ids["fx"] = uuid7()
    asyncio.run(
        _write(
            url,
            [
                (
                    "INSERT INTO portfolio_risk_state (organization_id, portfolio_id, "
                    "peak_equity, peak_equity_at) VALUES (:org, :pf, 20000, now())",
                    {"org": ids["org"], "pf": ids["portfolio_0"]},
                ),
                (
                    "INSERT INTO fx_observations (id, pair, rate, source, observed_at, "
                    "available_at) VALUES (:id, 'USDTBRL', 5, :source, now(), now())",
                    {"id": ids["fx"], "source": f"probe#{slug}"},
                ),
                (
                    "INSERT INTO portfolio_currency_anchor (id, organization_id, portfolio_id, "
                    "origin_amount, credited_amount, fx_observation_id, rate, "
                    "conversion_residual, rounding_policy) VALUES "
                    "(:id, :org, :pf, 100000, 20000, :fx, 5, 0, 'floor_10dp_v1')",
                    {
                        "id": uuid7(),
                        "org": ids["org"],
                        "pf": ids["portfolio_0"],
                        "fx": ids["fx"],
                    },
                ),
            ],
        )
    )
    return ids


def test_0006_refuses_to_downgrade_while_a_wallet_is_open(upgraded: str) -> None:
    """Reversing is allowed; losing the opening of a wallet is not.

    ``portfolio_currency_anchor`` holds the ``F0`` and ``E0`` every BRL number is
    measured from, and the directive forbids opening the wallet again to recreate
    them, so "the migration reversed cleanly" would be the only report of a loss
    that cannot be undone. The guard names it instead.
    """
    config = alembic_config(upgraded)
    ids = _open_a_wallet(upgraded, f"open-{uuid.uuid4().hex[:8]}")
    # The head is ``0007`` since T3.1c, and it reverses cleanly over an opened
    # wallet — it owns grants and three columns, not the opening. So step down to
    # ``0006`` first and make ``-1`` mean this guard again.
    command.downgrade(config, PAPER_WALLET_REVISION)
    try:
        with pytest.raises(DBAPIError, match="anchored to an opening rate"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == PAPER_WALLET_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        _drop_tenant(upgraded, ids["org"])
    command.downgrade(config, "-1")
    command.upgrade(config, "head")
    command.check(config)


def test_0006_refuses_to_downgrade_while_a_reservation_is_still_held(upgraded: str) -> None:
    """A held reservation is cash, risk, exposure and a slot nobody released.

    Dropping the columns releases all four silently, and nothing afterwards knows
    they were ever held: the reservation would simply cease to exist while the
    proposal that owns it survives.
    """
    config = alembic_config(upgraded)
    slug = f"held-{uuid.uuid4().hex[:8]}"
    ids = _tenant(upgraded, slug, portfolios=1)
    exchange, market, proposal = uuid7(), uuid7(), uuid7()
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')",
                    {"id": exchange, "code": f"probe-{slug}"},
                ),
                (
                    "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                    "VALUES (:id, :exchange, :symbol, 'spot')",
                    {"id": market, "exchange": exchange, "symbol": f"S{slug.upper()[:8]}"},
                ),
                (
                    "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                    "direction, idempotency_key, reservation_state, reserved_notional, "
                    "reserved_cash, reserved_risk, reserved_slot, reserved_until) VALUES "
                    "(:id, :org, :pf, :m, 'long', :key, 'held', 1800, 1801, 45, true, now())",
                    {
                        "id": proposal,
                        "org": ids["org"],
                        "pf": ids["portfolio_0"],
                        "m": market,
                        "key": slug,
                    },
                ),
            ],
        )
    )
    command.downgrade(config, PAPER_WALLET_REVISION)  # see the note in the test above
    try:
        with pytest.raises(DBAPIError, match="still hold a reservation"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == PAPER_WALLET_REVISION
    finally:
        _drop_tenant(upgraded, ids["org"])
        asyncio.run(
            _write(
                upgraded,
                [
                    ("DELETE FROM markets WHERE id = :id", {"id": market}),
                    ("DELETE FROM exchanges WHERE id = :id", {"id": exchange}),
                ],
            )
        )
    command.downgrade(config, "-1")
    command.upgrade(config, "head")
    command.check(config)


async def _column_privilege(url: str, role: str, table: str, column: str) -> bool:
    """Whether ``role`` may ``UPDATE`` one column of ``table`` — the 0007 shape."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("SELECT has_column_privilege(:role, :table, :column, 'UPDATE')"),
                    {"role": role, "table": table, "column": column},
                )
            )
    finally:
        await engine.dispose()


def _frozen_worker_columns() -> Mapping[str, tuple[str, ...]]:
    return cast(
        "Mapping[str, tuple[str, ...]]",
        migration_ddl("paper_roles").WORKER_COLUMN_UPDATES_0007,
    )


def _frozen_app_revocations() -> Mapping[str, tuple[str, ...]]:
    return cast(
        "Mapping[str, tuple[str, ...]]",
        migration_ddl("paper_roles").APP_PRIVILEGES_REVOKED_0007,
    )


def test_0007_grants_the_engine_columns_and_never_the_table(upgraded: str) -> None:
    """The engine may move a kill switch and lock an organization; nothing more.

    A *column* grant is the whole point (DATABASE.md §19.1): it satisfies the row
    mark PostgreSQL charges ``ACL_UPDATE`` for and refuses every ``UPDATE`` that
    writes a value, and — unlike a ``current_user`` test — it travels with role
    inheritance. Table-level ``UPDATE`` here would let the worker rename a
    wallet, archive it, flip ``is_arena`` (freeing a second principal wallet,
    §18.8) or block a whole organization with no transition.
    """
    inserts = cast("tuple[str, ...]", migration_ddl("paper_roles").WORKER_INSERT_TABLES_0007)
    for table in inserts:
        # Opening a wallet is one transaction and its first curve point is the
        # engine's, so the wallet row is too — INSERT, and nothing beyond it.
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
        }
    frozen = _frozen_worker_columns()
    assert frozen, "0007 froze no column to grant"
    for table, columns in frozen.items():
        held = asyncio.run(_table_privileges(upgraded, "hunter_worker", table))
        assert "UPDATE" not in held, f"{table} was granted at table level: {held}"
        for column in columns:
            assert asyncio.run(_column_privilege(upgraded, "hunter_worker", table, column)), (
                f"the engine cannot update {table}.{column}"
            )
    for table, column in (("portfolios", "name"), ("organizations", "kill_switch_state")):
        assert not asyncio.run(_column_privilege(upgraded, "hunter_worker", table, column)), (
            f"the engine may write {table}.{column}, which is not its to write"
        )


def test_0007_leaves_the_api_reading_the_curve_and_filing_requests(upgraded: str) -> None:
    """The API reads the equity curve and files a proposal; it decides neither.

    The curve is the evidence a resume reads and the ceiling a rising peak is
    measured against, and RLS does not protect a tenant's numbers from that
    tenant's own request handler (security review of ``0006``, finding 5).
    """
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "portfolio_equity_snapshots")) == {
        "SELECT"
    }
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "trade_proposals")) == {
        "SELECT",
        "INSERT",
    }
    # and the worker keeps the whole surface it writes
    assert asyncio.run(
        _table_privileges(upgraded, "hunter_worker", "portfolio_equity_snapshots")
    ) == {"SELECT", "INSERT", "UPDATE", "DELETE"}


def test_0007_touches_no_table_that_was_not_already_classified(upgraded: str) -> None:
    """A grant revision must not smuggle in an unclassified table — the 0005 rule.

    ``test_schema_privileges.test_the_grant_lists_cover_every_table_exactly_once``
    partitions the schema over the *app*-side classes of ``0001``; a worker-side
    column grant on a table nobody classified would slip past it.
    """
    tables = migration_ddl("tables")
    owned = set(cast("tuple[str, ...]", tables.APP_WRITE_TABLES)) | set(
        cast("tuple[str, ...]", tables.APP_NO_DELETE_TABLES)
    )
    named = (
        set(_frozen_worker_columns())
        | set(_frozen_app_revocations())
        | set(cast("tuple[str, ...]", migration_ddl("paper_roles").WORKER_INSERT_TABLES_0007))
    )
    assert named <= owned, "0007 grants on a table 0001 never classified"


def test_0007_reverses_to_the_privileges_0001_shipped(upgraded: str) -> None:
    """Rolling this deploy back restores ``0001``'s grants exactly — not ``ALL``.

    A database rolled back to ``0006`` has to be usable by the code that ran
    against ``0006``: the API writes the curve and the proposal again, and the
    engine loses the two column grants it never had there.
    """
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, PAPER_WALLET_REVISION)
        for table, privileges in _frozen_app_revocations().items():
            held = asyncio.run(_table_privileges(upgraded, "hunter_app", table))
            assert set(privileges) <= held, (table, held)
        for table, columns in _frozen_worker_columns().items():
            for column in columns:
                assert not asyncio.run(
                    _column_privilege(upgraded, "hunter_worker", table, column)
                ), f"{table}.{column} survived the downgrade"
        for table in cast(
            "tuple[str, ...]", migration_ddl("paper_roles").WORKER_INSERT_TABLES_0007
        ):
            assert "INSERT" not in asyncio.run(
                _table_privileges(upgraded, "hunter_worker", table)
            ), f"the engine kept INSERT on {table} after the downgrade"
    finally:
        command.upgrade(config, "head")
    command.check(config)


def _frozen_execution_read_only() -> tuple[str, ...]:
    return cast("tuple[str, ...]", migration_ddl("paper_roles_2").APP_READ_ONLY_TABLES_0008)


def test_0008_leaves_the_api_reading_execution_and_writing_none_of_it(upgraded: str) -> None:
    """D1: ``orders``, ``fills``, ``positions`` and ``trades`` become read-only to the API.

    The security review of ``0007`` reproduced the whole surface as the role, in
    the *correct* organization, where RLS says yes: a fabricated fill,
    ``positions.qty × 1000``, ``DELETE FROM trades``, ``UPDATE orders``. The
    curve ``0007`` closed is *derived* from these four, so forging the source
    makes the engine compute and sign the forged point itself. ``SELECT`` stays,
    because T3.8a's seven routes read them (§20.1).

    The worker keeps full DML: it is the one that executes.
    """
    frozen = _frozen_execution_read_only()
    assert frozen, "0008 reclassified no table"
    for table in frozen:
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", table)) == {"SELECT"}, table
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
        }, table
    # the one execution table the API still writes, and only files into
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "trade_proposals")) == {
        "SELECT",
        "INSERT",
    }


def test_0008_reclassifies_only_tables_0001_had_already_classified(upgraded: str) -> None:
    """A grant revision must not smuggle in an unclassified table.

    ``test_schema_privileges.test_the_grant_lists_cover_every_table_exactly_once``
    keeps the schema partitioned over the *app*-side classes, and ``0008``'s list
    is a **move** between two of them — so it has to be a subset of what ``0001``
    already owns, or the subtraction that test performs would silently drop a
    table out of the partition. Same role
    ``test_0005_touches_no_table_0003_had_not_already_classified`` plays.
    """
    write = set(cast("tuple[str, ...]", migration_ddl("security").APP_WRITE_TABLES))
    assert set(_frozen_execution_read_only()) <= write, (
        "0008 reclassifies a table 0001 never put in APP_WRITE_TABLES; give it its own class"
    )


def test_0008_reverses_to_the_execution_privileges_0001_shipped(upgraded: str) -> None:
    """Rolling back this deploy gives the API its DML back — and only that.

    The downgrade names ``INSERT``/``UPDATE``/``DELETE`` rather than ``GRANT
    ALL``: a privilege statement should say what it means, and the guards
    ``0008`` installs come off with it, so a database rolled back to ``0007`` is
    usable by the code that ran against ``0007``.
    """
    config = alembic_config(upgraded)
    try:
        command.downgrade(config, PAPER_ROLES_REVISION)
        for table in _frozen_execution_read_only():
            held = asyncio.run(_table_privileges(upgraded, "hunter_app", table))
            assert held == {"SELECT", "INSERT", "UPDATE", "DELETE"}, (table, held)
        assert asyncio.run(_revision(upgraded)) == PAPER_ROLES_REVISION
        assert not asyncio.run(_trigger_exists(upgraded, "portfolios_are_born_audited"))
        assert "kill_switch_reason" not in asyncio.run(
            _trigger_condition(upgraded, "portfolios_kill_switch_is_audited")
        ), "the widened WHEN survived the downgrade"
    finally:
        command.upgrade(config, "head")
    for table in _frozen_execution_read_only():
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", table)) == {"SELECT"}
    assert asyncio.run(_trigger_exists(upgraded, "portfolios_are_born_audited"))
    command.check(config)


async def _trigger_exists(url: str, name: str) -> bool:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE tgname = :name"), {"name": name}
                )
            )
    finally:
        await engine.dispose()


async def _trigger_condition(url: str, name: str) -> str:
    """The ``WHEN`` clause of ``name``, read back from ``pg_get_triggerdef``.

    Alembic never compares a trigger, so the only honest source is the
    catalogue — the same reason §17.3 reads ``pg_indexes.indexdef`` for an index
    predicate.
    """
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text("SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE tgname = :name LIMIT 1"),
                {"name": name},
            )
            return str(definition or "")
    finally:
        await engine.dispose()


def test_0008_widens_both_kill_switch_guards_to_the_motive(upgraded: str) -> None:
    """D4: the guard fires on ``kill_switch_reason`` as well as on the state.

    Before this, ``UPDATE portfolios SET kill_switch_reason = '...'`` rewrote the
    text an OWNER reads with no transition, no actor and no history — the state
    and the story it tells could disagree for ever. Read from
    ``pg_get_triggerdef`` because Alembic does not compare triggers.
    """
    for trigger in ("portfolios_kill_switch_is_audited", "organizations_kill_switch_is_audited"):
        condition = asyncio.run(_trigger_condition(upgraded, trigger))
        assert "kill_switch_state" in condition, (trigger, condition)
        assert "kill_switch_reason" in condition, (trigger, condition)


# --------------------------------------------------------------------------
# 0009_paper_geometry — the geometry of a request, and the dust that is not one
# --------------------------------------------------------------------------


_GEOMETRY = json.dumps(
    {
        "client_key": "operator-0009",
        "market_id": "00000000-0000-7000-8000-000000000009",
        "direction": "long",
        "entry_ref": "100",
        "stop": "97.5",
        "target": None,
        "requested_notional": None,
        "assumed_costs": {"spread_bps": "2", "slippage_bps": "5", "fee_bps": "4"},
    }
)
"""One well-formed ``request_payload``, written out rather than imported from
``hunter_core.admission.sources`` so the migration is checked against the
contract and not against the writer that happens to implement it."""


def _wallet_with_a_market(url: str, slug: str) -> dict[str, uuid.UUID]:
    """A tenant, one wallet and one market — enough to file a request on."""
    ids = _tenant(url, slug, portfolios=1)
    ids["exchange"], ids["market"] = uuid7(), uuid7()
    asyncio.run(
        _write(
            url,
            [
                (
                    "INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')",
                    {"id": ids["exchange"], "code": f"probe-{slug}"},
                ),
                (
                    "INSERT INTO markets (id, exchange_id, symbol, market_type) "
                    "VALUES (:id, :exchange, :symbol, 'spot')",
                    {
                        "id": ids["market"],
                        "exchange": ids["exchange"],
                        "symbol": f"S{slug.upper()[:8]}",
                    },
                ),
            ],
        )
    )
    return ids


def _forget_market(url: str, ids: Mapping[str, uuid.UUID]) -> None:
    asyncio.run(
        _write(
            url,
            [
                ("DELETE FROM markets WHERE id = :id", {"id": ids["market"]}),
                ("DELETE FROM exchanges WHERE id = :id", {"id": ids["exchange"]}),
            ],
        )
    )


async def _column_exists(url: str, table: str, column: str) -> bool:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_name = :table AND column_name = :column"
                    ),
                    {"table": table, "column": column},
                )
            )
    finally:
        await engine.dispose()


async def _index_definition(url: str, name: str) -> str:
    """``pg_indexes.indexdef`` — Alembic never compares an index predicate (§17.3)."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            definition = await connection.scalar(
                text("SELECT indexdef FROM pg_indexes WHERE indexname = :name"), {"name": name}
            )
            return str(definition or "")
    finally:
        await engine.dispose()


_PAIR = re.compile(r"NEW\.(\w+) IS DISTINCT FROM OLD\.(\w+)")
"""One comparison of ``shadow_freeze_strategy_version``'s body, both sides
captured — a body that compared ``NEW.a`` with ``OLD.b`` would be a bug this
must not read past."""


def _frozen_columns(body: str) -> tuple[str, ...]:
    """The column list ``shadow_freeze_strategy_version`` actually compares, in
    the order the installed body compares them.

    Read out of the body rather than asserted with ``in``: a substring check
    passes on a *superset*, so it can never notice a column that a later
    revision quietly added to — or dropped from — the freeze. The list is the
    contract (§22.2, §24, §29.3), so the list is what gets compared.
    """
    pairs: list[tuple[str, str]] = re.findall(_PAIR, body)
    assert all(left == right for left, right in pairs), f"compares two columns: {pairs}"
    return tuple(left for left, _ in pairs)


async def _function_source(url: str, name: str) -> str:
    """The body of a trigger function, read from ``pg_proc``.

    Alembic never compares a function, so the catalogue is the only honest
    source — the same reason §17.3 reads ``pg_indexes.indexdef``.
    """
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            source = await connection.scalar(
                text("SELECT prosrc FROM pg_proc WHERE proname = :name LIMIT 1"), {"name": name}
            )
            return str(source or "")
    finally:
        await engine.dispose()


def test_0009_adds_the_geometry_the_dust_flag_and_the_live_index(upgraded: str) -> None:
    """The two columns, their CHECKs and the partial index exist at head.

    ``request_payload`` closes ``notes-T3.5.md`` §5.1 (a filed request that could
    be identified and never decided) and ``is_residual`` closes item 3 of
    ``review-T3.5.md`` (dust holding a slot for ever). The index is what the
    live-position readers need once their predicate grows a term.
    """
    assert asyncio.run(_column_exists(upgraded, "trade_proposals", "request_payload"))
    assert asyncio.run(_column_exists(upgraded, "positions", "is_residual"))
    definition = asyncio.run(_index_definition(upgraded, "ix_positions_org_portfolio_live"))
    assert "NOT is_residual" in definition, definition
    assert "status <> 'closed'" in definition, definition


def test_0009_teaches_the_request_guard_to_demand_geometry_and_refuse_a_proof(
    upgraded: str,
) -> None:
    """§21.2: the guard body names the payload and the two forged columns.

    Read from ``pg_proc`` rather than asserted through a statement here because
    ``test_schema_paper.py`` already runs the refusals as the real role; what
    this adds is that the **migration** installed the ``0009`` body and not
    ``0007``'s, which is the copy §21.4 freezes.
    """
    body = asyncio.run(_function_source(upgraded, "trade_proposals_the_app_only_files_requests"))
    assert "NEW.request_payload IS NULL" in body
    assert "NEW.request_digest IS NOT NULL" in body
    assert "NEW.kill_switch_snapshot" in body
    # 0007's clause is still there: this revision extends the guard, never
    # replaces what it already refused.
    assert "carrying a decision" in body


def test_0009_refuses_to_downgrade_while_a_request_carries_its_geometry(
    upgraded: str,
) -> None:
    """Reversing is allowed; making every pending request undecidable is not.

    Dropping ``request_payload`` from a database that holds one puts the wallet
    back exactly where ``notes-T3.5.md`` §5.1 found it — a filed order the
    engine can see and never answer — and nothing in the remaining columns can
    reconstruct what a person typed. So the guard counts them and names them.
    """
    config = alembic_config(upgraded)
    slug = f"geo-{uuid.uuid4().hex[:8]}"
    ids = _wallet_with_a_market(upgraded, slug)
    proposal = uuid7()
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                    "direction, status, idempotency_key, source, request_payload) VALUES "
                    "(:id, :org, :pf, :m, 'long', 'pending', :key, 'manual', "
                    "CAST(:payload AS jsonb))",
                    {
                        "id": proposal,
                        "org": ids["org"],
                        "pf": ids["portfolio_0"],
                        "m": ids["market"],
                        "key": f"manual:{slug}",
                        "payload": _GEOMETRY,
                    },
                )
            ],
        )
    )
    # The head is ``0010`` since T3.15, and it reverses cleanly over a filed
    # request — it owns ``purpose`` and the freeze trigger, not the geometry. So
    # step down to ``0009`` first and make ``-1`` mean this guard again (the same
    # idiom ``test_0006_refuses_to_downgrade_while_a_wallet_is_open`` uses).
    command.downgrade(config, PAPER_GEOMETRY_REVISION)
    try:
        with pytest.raises(DBAPIError, match="carry a request_payload"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == PAPER_GEOMETRY_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        _drop_tenant(upgraded, ids["org"])
        _forget_market(upgraded, ids)
        command.upgrade(config, "head")
    command.check(config)


def test_0009_refuses_to_downgrade_while_a_position_is_marked_as_dust(
    upgraded: str,
) -> None:
    """Dropping ``is_residual`` makes dust a live position again.

    Which is precisely the state ``review-T3.5.md`` item 3 reproduced four hours
    after a stop: a slot held for ever, exposure that is not exposure, and the
    next order in that coin refused as a duplicate. Losing the column loses the
    distinction, and "the migration reversed cleanly" would be the only report
    of it.
    """
    config = alembic_config(upgraded)
    slug = f"dust-{uuid.uuid4().hex[:8]}"
    ids = _wallet_with_a_market(upgraded, slug)
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "INSERT INTO positions (id, organization_id, portfolio_id, market_id, "
                    "direction, qty, avg_entry_price, status, is_residual) VALUES "
                    "(:id, :org, :pf, :m, 'long', 0.000482, 100, 'closing', true)",
                    {
                        "id": uuid7(),
                        "org": ids["org"],
                        "pf": ids["portfolio_0"],
                        "m": ids["market"],
                    },
                )
            ],
        )
    )
    # See the note in ``test_0009_refuses_to_downgrade_while_a_request_carries_its_geometry``:
    # head is ``0010`` now, so step down to ``0009`` first.
    command.downgrade(config, PAPER_GEOMETRY_REVISION)
    try:
        with pytest.raises(DBAPIError, match="marked as residual dust"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == PAPER_GEOMETRY_REVISION
    finally:
        _drop_tenant(upgraded, ids["org"])
        _forget_market(upgraded, ids)
        command.upgrade(config, "head")
    command.check(config)


def test_0009_reverses_on_a_populated_database_and_gives_0007s_guard_back(
    upgraded: str,
) -> None:
    """The round trip, over a wallet with rows that do **not** trip either guard.

    A tenant, a wallet, a market, a request with no payload and a position that
    is not dust: everything the revision touches, populated, and none of it an
    obligation the guards protect. Down one, up to head, and ``alembic check``
    at the end — plus the half a privilege test cannot see, which is that the
    downgrade restores the guard ``0007`` describes rather than leaving ``0009``'s
    body pointing at a column that no longer exists.
    """
    config = alembic_config(upgraded)
    slug = f"trip-{uuid.uuid4().hex[:8]}"
    ids = _wallet_with_a_market(upgraded, slug)
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "INSERT INTO trade_proposals (id, organization_id, portfolio_id, market_id, "
                    "direction, status, idempotency_key, source) VALUES "
                    "(:id, :org, :pf, :m, 'long', 'pending', :key, 'manual')",
                    {
                        "id": uuid7(),
                        "org": ids["org"],
                        "pf": ids["portfolio_0"],
                        "m": ids["market"],
                        "key": f"manual:{slug}",
                    },
                ),
                (
                    "INSERT INTO positions (id, organization_id, portfolio_id, market_id, "
                    "direction, qty, avg_entry_price, status) VALUES "
                    "(:id, :org, :pf, :m, 'long', 1.5, 100, 'open')",
                    {
                        "id": uuid7(),
                        "org": ids["org"],
                        "pf": ids["portfolio_0"],
                        "m": ids["market"],
                    },
                ),
            ],
        )
    )
    # Head is ``0010`` since T3.15: step down to ``0009`` first, then ``-1`` is
    # this revision's own downgrade again (see the note above).
    command.downgrade(config, PAPER_GEOMETRY_REVISION)
    try:
        command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == PAPER_ROLES_2_REVISION
        assert not asyncio.run(_column_exists(upgraded, "trade_proposals", "request_payload"))
        assert not asyncio.run(_column_exists(upgraded, "positions", "is_residual"))
        reverted = asyncio.run(
            _function_source(upgraded, "trade_proposals_the_app_only_files_requests")
        )
        assert "request_payload" not in reverted, "0009's body survived its own downgrade"
        assert "carrying a decision" in reverted, "0007's guard did not come back"
    finally:
        command.upgrade(config, "head")
        _drop_tenant(upgraded, ids["org"])
        _forget_market(upgraded, ids)
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


# --------------------------------------------------------------------------
# 0010_strategy_purpose — the wallet a signal may reach, named on the version
# --------------------------------------------------------------------------


def _strategy_version(
    url: str,
    *,
    key: str,
    purpose: str | None = None,
    activated: bool = False,
    policy: str | None = None,
) -> uuid.UUID:
    """A fresh ``strategies``/``strategy_versions`` pair. ``purpose`` omitted
    means "let the column default decide"; ``policy`` is the ``0017`` JSON, as
    text, and omitting it leaves the column ``NULL`` — no gate."""
    strategy_id, version_id = uuid7(), uuid7()
    columns = "id, strategy_id, version, status, code_ref, activated_at"
    placeholders = ":id, :strategy, 'v1', :status, 'hunter_core.strategies.probe', :activated_at"
    params: dict[str, object] = {
        "id": version_id,
        "strategy": strategy_id,
        "status": "active" if activated else "draft",
        "activated_at": datetime(2026, 9, 7, tzinfo=UTC) if activated else None,
    }
    if purpose is not None:
        columns += ", purpose"
        placeholders += ", :purpose"
        params["purpose"] = purpose
    if policy is not None:
        columns += ", eligibility_policy"
        placeholders += ", CAST(:policy AS jsonb)"
        params["policy"] = policy
    asyncio.run(
        _write(
            url,
            [
                (
                    "INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)",
                    {"id": strategy_id, "key": key},
                ),
                (
                    f"INSERT INTO strategy_versions ({columns}) VALUES ({placeholders})",  # noqa: S608
                    params,
                ),
            ],
        )
    )
    return version_id


def _forget_draft_strategy_version(url: str, version_id: uuid.UUID) -> None:
    """Undo :func:`_strategy_version` for a **draft** (never-activated) row.

    ``upgraded`` is a module-scoped database shared by every test in this file
    — unlike the freeze trigger's activated rows, a draft carrying ``purpose =
    'paper'`` left behind here would trip section 22's downgrade guard for
    every *later* test that reverses past ``0010``, for a reason that test
    never created. Only tests that leave the row ``draft`` call this; the one
    that activates one (proving the freeze) leaves it, like every other frozen
    probe row in this file.
    """
    asyncio.run(
        _write(
            url,
            [
                (
                    # ``ON DELETE CASCADE`` (``strategy_versions.strategy_id``)
                    # takes the version row with it; the freeze trigger's own
                    # ``DELETE`` guard only fires when ``activated_at`` is set,
                    # which a draft row never has.
                    "DELETE FROM strategies WHERE id = "
                    "(SELECT strategy_id FROM strategy_versions WHERE id = :id)",
                    {"id": version_id},
                ),
            ],
        )
    )


def test_0010_adds_the_purpose_column_defaulting_research_only(upgraded: str) -> None:
    """Every row this schema has ever had was, and remains, ``research_only`` —
    the honest backfill DATABASE.md section 22 describes."""
    assert asyncio.run(_column_exists(upgraded, "strategy_versions", "purpose"))
    version_id = _strategy_version(upgraded, key=f"purpose-default-{uuid.uuid4().hex[:8]}")
    values = asyncio.run(
        _scalars(
            upgraded,
            "SELECT purpose FROM strategy_versions WHERE id = :id",
            {"id": version_id},
        )
    )
    assert values == ["research_only"]


def test_0010_refuses_a_fourth_label(upgraded: str) -> None:
    """``research_only`` | ``paper`` | ``live`` — nothing else is representable."""
    with pytest.raises(DBAPIError, match="purpose"):
        _strategy_version(upgraded, key=f"purpose-bogus-{uuid.uuid4().hex[:8]}", purpose="bogus")


def test_0010_a_paper_version_carries_the_label_the_worker_reads(upgraded: str) -> None:
    version_id = _strategy_version(
        upgraded, key=f"purpose-paper-{uuid.uuid4().hex[:8]}", purpose="paper"
    )
    try:
        values = asyncio.run(
            _scalars(
                upgraded,
                "SELECT purpose FROM strategy_versions WHERE id = :id",
                {"id": version_id},
            )
        )
        assert values == ["paper"]
    finally:
        _forget_draft_strategy_version(upgraded, version_id)


def test_0010_widens_the_freeze_trigger_to_cover_purpose(upgraded: str) -> None:
    """The trigger installed is ``0010``'s body, not ``0002``'s: same function
    name, wider column list — read from ``pg_proc`` the way ``test_0009_teaches
    _the_request_guard_to_demand_geometry_and_refuse_a_proof`` reads the request
    guard's body, since Alembic never compares a function (§17.3)."""
    body = asyncio.run(_function_source(upgraded, "shadow_freeze_strategy_version"))
    assert "NEW.purpose IS DISTINCT FROM OLD.purpose" in body
    # 0002's own checks are still there: this widens the trigger, it does not
    # replace what it already froze.
    assert "NEW.code_ref IS DISTINCT FROM OLD.code_ref" in body


def test_0010_freezes_purpose_after_activation(upgraded: str) -> None:
    version_id = _strategy_version(
        upgraded,
        key=f"purpose-frozen-{uuid.uuid4().hex[:8]}",
        purpose="research_only",
        activated=True,
    )
    with pytest.raises(DBAPIError, match="frozen"):
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "UPDATE strategy_versions SET purpose = 'paper' WHERE id = :id",
                        {"id": version_id},
                    )
                ],
            )
        )


async def _purpose_column_privilege(url: str, role: str, privilege: str) -> bool:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text(
                        "SELECT has_column_privilege(:role, 'strategy_versions', "
                        "'purpose', :privilege)"
                    ),
                    {"role": role, "privilege": privilege},
                )
            )
    finally:
        await engine.dispose()


def test_0010_revokes_the_workers_write_on_purpose_but_not_its_read(upgraded: str) -> None:
    """Read for both roles, write for nobody but the activation/migration
    connection — DATABASE.md section 22, the same shape ``0007`` used for
    ``portfolio_risk_state``'s lock column, in reverse."""
    assert asyncio.run(_purpose_column_privilege(upgraded, "hunter_worker", "SELECT"))
    assert asyncio.run(_purpose_column_privilege(upgraded, "hunter_app", "SELECT"))
    assert not asyncio.run(_purpose_column_privilege(upgraded, "hunter_worker", "UPDATE"))
    assert not asyncio.run(_purpose_column_privilege(upgraded, "hunter_worker", "INSERT"))
    assert not asyncio.run(_purpose_column_privilege(upgraded, "hunter_app", "UPDATE"))
    assert not asyncio.run(_purpose_column_privilege(upgraded, "hunter_app", "INSERT"))


def test_0010_refuses_to_downgrade_while_a_version_carries_a_non_research_only_purpose(
    upgraded: str,
) -> None:
    """Dropping the column would erase the one thing telling a paper coorte
    apart from shadow evidence — not derivable from anything that remains."""
    config = alembic_config(upgraded)
    # The head is ``0011`` since T3.15c, and it reverses cleanly (grants only) —
    # step down to ``0010`` first and make ``-1`` mean this guard again, the same
    # shape ``test_0006_refuses_to_downgrade_while_a_wallet_is_still_anchored``
    # uses for ``0007`` sitting on top of ``0006``.
    command.downgrade(config, STRATEGY_PURPOSE_REVISION)
    version_id = _strategy_version(
        upgraded, key=f"purpose-guard-{uuid.uuid4().hex[:8]}", purpose="paper"
    )
    try:
        with pytest.raises(DBAPIError, match="purpose other than research_only"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == STRATEGY_PURPOSE_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        _forget_draft_strategy_version(upgraded, version_id)
    command.upgrade(config, "head")
    command.check(config)


def test_0010_reverses_on_a_populated_database_and_gives_0002s_trigger_back(
    upgraded: str,
) -> None:
    """The round trip, over a version that does **not** trip the guard.

    Down one, up to head, and ``alembic check`` at the end — plus the half a
    privilege test cannot see, which is that the downgrade restores the trigger
    ``0002`` describes rather than leaving ``0010``'s wider body pointing at a
    column that no longer exists.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, STRATEGY_PURPOSE_REVISION)  # see the note two tests up
    _strategy_version(upgraded, key=f"purpose-trip-{uuid.uuid4().hex[:8]}")
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == PAPER_GEOMETRY_REVISION
        assert not asyncio.run(_column_exists(upgraded, "strategy_versions", "purpose"))
        reverted = asyncio.run(_function_source(upgraded, "shadow_freeze_strategy_version"))
        assert "purpose" not in reverted, "0010's wider body survived its own downgrade"
        assert "code_ref" in reverted, "0002's trigger did not come back"
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


# --------------------------------------------------------------------------
# 0011_strategy_activation_owner — nothing left for hunter_worker but SELECT
# and a few inert columns
# --------------------------------------------------------------------------


def test_0011_reverses_and_restores_0010s_grant(upgraded: str) -> None:
    """Round trip: grants only (no DDL on the relation, no downgrade guard),
    and ``alembic check`` at the end.

    The behavioural proof (cannot activate, cannot delete, can still SELECT) is
    ``test_schema_privileges.py`` — this is the migration-machinery half: the
    exact state ``0010`` left survives an upgrade/downgrade/upgrade round trip.
    """
    config = alembic_config(upgraded)
    # ``0012`` sits on top since T3.19c, so step down to ``0011`` first and make
    # ``-1`` mean *this* revision again — the same shape the two ``0010`` tests
    # above use for ``0011`` sitting on top of ``0010``.
    command.downgrade(config, STRATEGY_ACTIVATION_OWNER_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == STRATEGY_PURPOSE_REVISION
        held = asyncio.run(_table_privileges(upgraded, "hunter_worker", "strategy_versions"))
        assert held == {"SELECT", "DELETE"}, held
        for column in migration_ddl("strategy_purpose").WORKER_COLUMNS_EXCEPT_PURPOSE:
            assert asyncio.run(
                _column_privilege(upgraded, "hunter_worker", "strategy_versions", column)
            ), f"0010's UPDATE grant on {column} did not come back on downgrade"
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    held = asyncio.run(_table_privileges(upgraded, "hunter_worker", "strategy_versions"))
    assert held == {"SELECT"}, held
    command.check(config)


# --------------------------------------------------------------------------
# 0012_replication — the replication cohort, the promising marker and a
# sibling's lineage — DATABASE.md section 24
# --------------------------------------------------------------------------

REPLICATION_REVISION = "0012_replication"


def _episode(url: str, *, cohort: str) -> uuid.UUID:
    """One ``shadow_episodes`` row on ``cohort``, with its own version and market."""
    version_id = _strategy_version(url, key=f"cohort-{uuid.uuid4().hex[:8]}")
    episode_id = uuid7()

    async def _insert() -> None:
        engine = async_engine(url)
        try:
            async with engine.begin() as connection:
                market_id = await _market(connection)
                await connection.execute(
                    text(
                        "INSERT INTO shadow_episodes (id, strategy_version_id, market_id, "
                        "cohort, episode_id, last_bar_close) VALUES (:id, :version, :market, "
                        ":cohort, :episode, now())"
                    ),
                    {
                        "id": episode_id,
                        "version": version_id,
                        "market": market_id,
                        "cohort": cohort,
                        "episode": uuid7(),
                    },
                )
        finally:
            await engine.dispose()

    asyncio.run(_insert())
    return episode_id


def _forget_episode(url: str, episode_id: uuid.UUID) -> None:
    asyncio.run(_write(url, [("DELETE FROM shadow_episodes WHERE id = :id", {"id": episode_id})]))


_SELF = object()
"""Sentinel for :func:`_sibling`'s ``parent``: "the row this one is derived from"."""


def _sibling(
    url: str,
    *,
    parent_id: uuid.UUID,
    index: int | None,
    parent: object = _SELF,
) -> uuid.UUID:
    """A second version of ``parent_id``'s strategy, carrying a lineage.

    ``parent`` defaults to ``parent_id``; passing it explicitly (including
    ``None``) is how the half-a-lineage tests below write the shapes the CHECK
    has to refuse.
    """
    version_id = uuid7()
    named_parent = parent_id if parent is _SELF else parent
    asyncio.run(
        _write(
            url,
            [
                (
                    "INSERT INTO strategy_versions (id, strategy_id, version, status, "
                    "replication_parent_id, replication_index) SELECT :id, strategy_id, "
                    ":version, 'active', :parent, :index FROM strategy_versions WHERE id = :of",
                    {
                        "id": version_id,
                        "version": f"v{uuid.uuid4().int % 9000 + 1000}",
                        "parent": named_parent,
                        "index": index,
                        "of": parent_id,
                    },
                )
            ],
        )
    )
    return version_id


def test_0012_and_the_domain_constant_agree_on_the_cohort_grammar() -> None:
    """The CHECK and ``hunter_core.domain.enums.SHADOW_COHORT_PATTERN`` are one
    grammar written twice — frozen in ``ddl/replication.py`` on purpose (the
    database's contract must not follow a later edit to a Python constant), so
    this is what keeps the copy honest.

    It also proves the *shape* of the change: ``0002``'s two branches survive
    inside ``0012``'s pattern character for character, which is the promise this
    revision makes about every prospective and replay episode already stored.
    """
    from hunter_core.domain.enums import SHADOW_COHORT_PATTERN

    ddl = migration_ddl("replication")
    assert ddl.COHORT_PATTERN_0012 == SHADOW_COHORT_PATTERN
    kept = ddl.COHORT_PATTERN_0002.removeprefix("^(").removesuffix(")$")
    assert ddl.COHORT_PATTERN_0012.startswith(f"^({kept}|replication:")


@pytest.mark.parametrize("arm", [1, 9, 10, 99])
def test_0012_accepts_a_replication_arm(upgraded: str, arm: int) -> None:
    parent = uuid7()
    episode_id = _episode(upgraded, cohort=f"replication:{parent}:{arm}")
    try:
        stored = asyncio.run(
            _scalars(
                upgraded, "SELECT cohort FROM shadow_episodes WHERE id = :id", {"id": episode_id}
            )
        )
        assert stored == [f"replication:{parent}:{arm}"]
    finally:
        _forget_episode(upgraded, episode_id)


def test_0012_keeps_the_two_cohorts_0002_shipped(upgraded: str) -> None:
    """A superset, never a replacement: the populations already on record keep
    the exact labels ``0002_shadow_lab`` gave them."""
    for cohort in ("prospective", f"replay:{uuid7()}"):
        episode_id = _episode(upgraded, cohort=cohort)
        try:
            assert asyncio.run(
                _scalars(
                    upgraded,
                    "SELECT cohort FROM shadow_episodes WHERE id = :id",
                    {"id": episode_id},
                )
            ) == [cohort]
        finally:
            _forget_episode(upgraded, episode_id)


@pytest.mark.parametrize(
    "cohort",
    [
        "replication:{parent}:0",
        "replication:{parent}:01",
        "replication:{parent}:100",
        "replication:{parent}",
        "replication:{parent}:1x",
        "replication:not-a-uuid:1",
    ],
)
def test_0012_refuses_a_cohort_that_is_not_an_arm(upgraded: str, cohort: str) -> None:
    """``:0`` is not an arm, ``:01`` is a second spelling of arm 1 — a second
    population under a name the report already uses — and ``:100`` is past the
    bound the pattern states."""
    with pytest.raises(DBAPIError, match="cohort_format"):
        _episode(upgraded, cohort=cohort.format(parent=uuid7()))


def test_0012_adds_the_promising_marker_and_the_lineage(upgraded: str) -> None:
    """Four nullable columns, no default: a version written before this revision
    honestly has no marker and honestly is not a sibling (section 24)."""
    for column in ("promising_at", "promising_by", "replication_parent_id", "replication_index"):
        assert asyncio.run(_column_exists(upgraded, "strategy_versions", column)), column
    version_id = _strategy_version(upgraded, key=f"replication-null-{uuid.uuid4().hex[:8]}")
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM strategy_versions WHERE id = :id "
            "AND promising_at IS NULL AND promising_by IS NULL "
            "AND replication_parent_id IS NULL AND replication_index IS NULL",
            {"id": version_id},
        )
    ) == ["1"]


def test_0012_writes_a_whole_lineage(upgraded: str) -> None:
    parent_id = _strategy_version(upgraded, key=f"replication-lineage-{uuid.uuid4().hex[:8]}")
    sibling_id = _sibling(upgraded, parent_id=parent_id, index=7)
    try:
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT replication_index::text FROM strategy_versions WHERE id = :id "
                "AND replication_parent_id = :parent",
                {"id": sibling_id, "parent": parent_id},
            )
        ) == ["7"]
    finally:
        _forget_draft_strategy_version(upgraded, parent_id)


@pytest.mark.parametrize(
    ("index", "parent_kind"),
    [
        (None, "parent"),  # a parent with no arm: indistinguishable from its siblings
        (3, "none"),  # an arm with no parent: an experiment nobody can find again
        (0, "parent"),  # 0 is not an arm
        (100, "parent"),  # past the bound the cohort grammar can express
        (1, "self"),  # a version is not its own sibling
    ],
)
def test_0012_refuses_half_a_lineage(upgraded: str, index: int | None, parent_kind: str) -> None:
    parent_id = _strategy_version(upgraded, key=f"replication-half-{uuid.uuid4().hex[:8]}")
    try:
        with pytest.raises(DBAPIError, match="replication_lineage"):
            if parent_kind == "self":
                asyncio.run(
                    _write(
                        upgraded,
                        [
                            (
                                "UPDATE strategy_versions SET replication_parent_id = id, "
                                "replication_index = :index WHERE id = :id",
                                {"id": parent_id, "index": index},
                            )
                        ],
                    )
                )
            else:
                _sibling(
                    upgraded,
                    parent_id=parent_id,
                    index=index,
                    parent=parent_id if parent_kind == "parent" else None,
                )
    finally:
        _forget_draft_strategy_version(upgraded, parent_id)


@pytest.mark.parametrize(
    ("promising_at", "promising_by"),
    [
        ("now()", "NULL"),  # a marker nobody can attribute is a date, not evidence
        ("NULL", "'scoreboard'"),  # an attribution for a marker that does not exist
        ("now()", "''"),  # the empty string attributes nothing (section 16.2)
    ],
)
def test_0012_refuses_a_marker_nobody_attributed(
    upgraded: str, promising_at: str, promising_by: str
) -> None:
    version_id = _strategy_version(upgraded, key=f"promising-half-{uuid.uuid4().hex[:8]}")
    try:
        with pytest.raises(DBAPIError, match="promising_is_attributed"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            f"UPDATE strategy_versions SET promising_at = {promising_at}, "  # noqa: S608
                            f"promising_by = {promising_by} WHERE id = :id",
                            {"id": version_id},
                        )
                    ],
                )
            )
    finally:
        _forget_draft_strategy_version(upgraded, version_id)


def test_0012_gives_an_arm_to_exactly_one_sibling(upgraded: str) -> None:
    """``UNIQUE (replication_parent_id, replication_index)`` — and, because
    Postgres treats NULLs as distinct, it costs nothing to every version that is
    not a sibling."""
    parent_id = _strategy_version(upgraded, key=f"replication-arm-{uuid.uuid4().hex[:8]}")
    _sibling(upgraded, parent_id=parent_id, index=1)
    try:
        with pytest.raises(DBAPIError, match="uq_strategy_versions_replication_arm"):
            _sibling(upgraded, parent_id=parent_id, index=1)
        # two non-siblings coexist: the UNIQUE is about arms, not about rows
        _strategy_version(upgraded, key=f"replication-arm-b-{uuid.uuid4().hex[:8]}")
        _strategy_version(upgraded, key=f"replication-arm-c-{uuid.uuid4().hex[:8]}")
    finally:
        _forget_draft_strategy_version(upgraded, parent_id)


def test_0012_freezes_the_lineage_but_leaves_the_marker_writable(upgraded: str) -> None:
    """The two halves of section 24's freeze decision, on one activated row.

    Re-pointing a sibling at another parent would silently re-attribute an
    experiment whose signals are already on record, so the lineage joins the
    frozen list. ``promising_at`` cannot join it: it is written *after*
    activation by definition — a version has to run before it can be promising —
    and freezing it would make the column unwritable on every row that could
    ever earn one.
    """
    body = asyncio.run(_function_source(upgraded, "shadow_freeze_strategy_version"))
    assert "NEW.replication_parent_id IS DISTINCT FROM OLD.replication_parent_id" in body
    assert "NEW.replication_index IS DISTINCT FROM OLD.replication_index" in body
    assert "NEW.promising_at" not in body, "the marker must stay writable after activation"
    # 0010's and 0002's own columns are still there: this widens the trigger.
    assert "NEW.purpose IS DISTINCT FROM OLD.purpose" in body
    assert "NEW.code_ref IS DISTINCT FROM OLD.code_ref" in body

    version_id = _strategy_version(
        upgraded, key=f"replication-freeze-{uuid.uuid4().hex[:8]}", activated=True
    )
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "UPDATE strategy_versions SET promising_at = now(), "
                    "promising_by = 'scoreboard:validada' WHERE id = :id",
                    {"id": version_id},
                )
            ],
        )
    )
    with pytest.raises(DBAPIError, match="frozen"):
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "UPDATE strategy_versions SET replication_index = 2 WHERE id = :id",
                        {"id": version_id},
                    )
                ],
            )
        )
    # leave the shared database without a marker the downgrade guards would trip
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "UPDATE strategy_versions SET promising_at = NULL, promising_by = NULL "
                    "WHERE id = :id",
                    {"id": version_id},
                )
            ],
        )
    )


@pytest.mark.parametrize(
    ("offender", "expected"),
    [
        ("promising", "carry a promising_at"),
        ("lineage", "carry a replication parent"),
        ("cohort", "carry a replication cohort"),
    ],
)
def test_0012_refuses_to_downgrade_while_a_replication_is_on_record(
    upgraded: str, offender: str, expected: str
) -> None:
    """Reversing is allowed; losing the marker block 1 counts from, the lineage
    that makes ten siblings one experiment, or an episode whose cohort ``0002``
    cannot represent, is not (§17.7)."""
    config = alembic_config(upgraded)
    # ``0013`` sits on top since T3.19d, so step down to ``0012`` first and make
    # ``-1`` mean *this* guard again — the same shape the ``0010`` and ``0011``
    # tests above use.
    command.downgrade(config, REPLICATION_REVISION)
    parent_id = _strategy_version(upgraded, key=f"replication-guard-{uuid.uuid4().hex[:8]}")
    sibling_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    if offender == "promising":
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "UPDATE strategy_versions SET promising_at = now(), "
                        "promising_by = 'scoreboard:validada' WHERE id = :id",
                        {"id": parent_id},
                    )
                ],
            )
        )
    elif offender == "lineage":
        sibling_id = _sibling(upgraded, parent_id=parent_id, index=1)
    else:
        episode_id = _episode(upgraded, cohort=f"replication:{parent_id}:1")
    try:
        with pytest.raises(DBAPIError, match=expected):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == REPLICATION_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        if episode_id is not None:
            _forget_episode(upgraded, episode_id)
        if sibling_id is not None:
            asyncio.run(
                _write(
                    upgraded,
                    [("DELETE FROM strategy_versions WHERE id = :id", {"id": sibling_id})],
                )
            )
        _forget_draft_strategy_version(upgraded, parent_id)
        command.upgrade(config, "head")


def test_0012_reverses_on_a_populated_database_and_gives_0010s_trigger_back(
    upgraded: str,
) -> None:
    """The round trip an operator runs to roll a deploy back: down one, up to
    head, ``alembic check`` at the end — over rows that do **not** trip a guard.

    Plus the half a column test cannot see: the downgrade puts back the trigger
    ``0010`` describes instead of leaving ``0012``'s wider body naming columns
    that no longer exist, and it narrows the cohort CHECK back to ``0002``'s two
    branches rather than leaving the widened one behind.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, REPLICATION_REVISION)  # see the note two tests up
    _strategy_version(upgraded, key=f"replication-trip-{uuid.uuid4().hex[:8]}")
    prospective = _episode(upgraded, cohort="prospective")
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == STRATEGY_ACTIVATION_OWNER_REVISION
        for column in ("promising_at", "replication_parent_id"):
            assert not asyncio.run(_column_exists(upgraded, "strategy_versions", column)), column
        reverted = asyncio.run(_function_source(upgraded, "shadow_freeze_strategy_version"))
        assert "replication_parent_id" not in reverted, "0012's wider body survived its downgrade"
        assert "purpose" in reverted, "0010's trigger did not come back"
        with pytest.raises(DBAPIError, match="cohort_format"):
            _episode(upgraded, cohort=f"replication:{uuid7()}:1")
    finally:
        command.upgrade(config, "head")
        _forget_episode(upgraded, prospective)
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


# --------------------------------------------------------------------------
# 0013_replay_runs — the durable receipt of a replay slice
# — DATABASE.md section 25
# --------------------------------------------------------------------------

_RECEIPT_COLUMNS = (
    "id, run_id, cohort, strategy_version_id, window_from, window_to, markets, started_at, "
    "finished_at, bars_evaluated, signals, outcomes_resolved, outcomes_open, seconds, "
    "decision_lag_s, workers, evaluations_by_state, errors"
)
_RECEIPT_VALUES = (
    ":id, :run_id, :cohort, :version, :window_from, :window_to, CAST(:markets AS text[]), "
    ":started_at, :finished_at, :bars, :signals, :resolved, :open, CAST(:seconds AS numeric), "
    ":lag_s, :workers, CAST(:states AS jsonb), :errors"
)


def _receipt_row(
    *,
    version_id: uuid.UUID,
    run_id: uuid.UUID,
    day_from: int,
    day_to: int,
    markets: list[str] | None = None,
) -> dict[str, object]:
    """One well-formed ``replay_runs`` slice, ready to be overridden per test.

    ``markets_digest`` (``0018``) is deliberately **not** in the statement: the
    trigger derives it from ``markets``, and leaving it out here is what proves
    that every writer predating that revision — this helper, the API's own
    fixtures, an operator's ``INSERT`` — keeps working and gets the right key.
    The tests that assert about the digest itself send one explicitly.
    """
    return {
        "id": uuid7(),
        "run_id": run_id,
        "cohort": f"replay:{run_id}",
        "version": version_id,
        "window_from": datetime(2026, 8, day_from, tzinfo=UTC),
        "window_to": datetime(2026, 8, day_to, tzinfo=UTC),
        "markets": markets if markets is not None else ["binance:BTCUSDT", "binance:ETHUSDT"],
        "started_at": datetime(2026, 9, 8, 10, tzinfo=UTC),
        "finished_at": datetime(2026, 9, 8, 10, 30, tzinfo=UTC),
        "bars": 864,
        "signals": 13,
        "resolved": 13,
        "open": 0,
        "seconds": "220.031",
        "lag_s": 2,
        "workers": 3,
        "states": json.dumps({"triggered": 20, "not_triggered": 844}),
        "errors": 0,
    }


def _write_receipt(url: str, row: dict[str, object]) -> None:
    asyncio.run(
        _write(
            url,
            [(f"INSERT INTO replay_runs ({_RECEIPT_COLUMNS}) VALUES ({_RECEIPT_VALUES})", row)],  # noqa: S608
        )
    )


def _forget_receipts(url: str, run_id: uuid.UUID) -> None:
    """Clear the module-scoped database again: ``upgraded`` is shared, and a
    receipt left behind trips 0013's downgrade guard for every later test."""
    asyncio.run(_write(url, [("DELETE FROM replay_runs WHERE run_id = :id", {"id": run_id})]))


def test_0013_and_the_domain_constant_agree_on_the_replay_grammar() -> None:
    """The CHECK, the frozen copy in ``ddl/replay_runs.py`` and
    ``hunter_core.domain.enums.REPLAY_COHORT_PATTERN`` are one grammar written
    three times — frozen in the ``ddl`` module on purpose (the contract of the
    database must not follow a later edit to a Python constant), so this is what
    keeps the copies honest.

    It also proves the *shape*: 0013's pattern is the replay branch of 0012's
    wider one, character for character, so a receipt can never carry a cohort
    ``shadow_episodes`` would reject, or the other way round.
    """
    from hunter_core.domain.enums import REPLAY_COHORT_PATTERN, SHADOW_COHORT_PATTERN

    ddl = migration_ddl("replay_runs")
    assert ddl.REPLAY_COHORT_PATTERN_0013 == REPLAY_COHORT_PATTERN
    branch = REPLAY_COHORT_PATTERN.removeprefix("^").removesuffix("$")
    assert f"|{branch}|" in SHADOW_COHORT_PATTERN


def test_0013_keeps_one_receipt_per_slice_of_a_run(upgraded: str) -> None:
    """Two slices of one run are two rows; the same slice twice is one.

    That is the decision of section 25.1 in a single assertion: the unit is the
    slice (summing them reconstructs a run, and no ``UPDATE`` is ever needed),
    and ``uq_replay_runs_slice`` is what makes re-running a slice idempotent
    instead of doubling the throughput number.
    """
    version_id = _strategy_version(upgraded, key=f"replay-slices-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    try:
        _write_receipt(
            upgraded, _receipt_row(version_id=version_id, run_id=run_id, day_from=8, day_to=11)
        )
        _write_receipt(
            upgraded, _receipt_row(version_id=version_id, run_id=run_id, day_from=11, day_to=14)
        )
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT sum(bars_evaluated)::text FROM replay_runs WHERE run_id = :id",
                {"id": run_id},
            )
        ) == ["1728"], "bars_evaluated is the column that sums across slices"
        with pytest.raises(DBAPIError, match="uq_replay_runs_slice"):
            _write_receipt(
                upgraded, _receipt_row(version_id=version_id, run_id=run_id, day_from=8, day_to=11)
            )
    finally:
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)


@pytest.mark.parametrize(
    ("field", "value", "constraint"),
    [
        ("cohort", "prospective", "cohort_is_a_replay_cohort"),
        ("cohort", "replication:{run}:1", "cohort_is_a_replay_cohort"),
        ("cohort", "replay:not-a-uuid", "cohort_is_a_replay_cohort"),
        ("cohort", "replay:11111111-1111-4111-8111-111111111111", "cohort_names_the_run"),
        ("window_to", datetime(2026, 8, 8, tzinfo=UTC), "window_is_half_open"),
        ("finished_at", datetime(2026, 9, 8, 9, tzinfo=UTC), "finished_after_it_started"),
        ("bars", -1, "counts_are_not_negative"),
        ("seconds", "-0.001", "counts_are_not_negative"),
        ("resolved", 14, "resolved_within_the_population"),
        ("markets", [], "a_slice_visited_a_market"),
        ("workers", 0, "a_slice_had_at_least_one_worker"),
        ("states", "[]", "evaluations_is_an_object"),
    ],
)
def test_0013_refuses_a_receipt_that_contradicts_itself(
    upgraded: str, field: str, value: object, constraint: str
) -> None:
    """One case per way of writing a receipt that is not one.

    The two cohort clauses say different things and both are needed: a run is
    never ``prospective`` and never a replication arm (those populations belong
    to the live clock), and the label may not name a run other than ``run_id``
    — the redundancy of section 25.2, made unable to drift.
    """
    version_id = _strategy_version(upgraded, key=f"replay-refuse-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    row = _receipt_row(version_id=version_id, run_id=run_id, day_from=8, day_to=11)
    row[field] = value.format(run=run_id) if isinstance(value, str) and "{run}" in value else value
    try:
        with pytest.raises(DBAPIError, match=constraint):
            _write_receipt(upgraded, row)
    finally:
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)


def test_0013_refuses_to_downgrade_while_a_receipt_exists(upgraded: str) -> None:
    """Section 17.7 again: reversing is allowed, losing evidence is not.

    ``system_events`` holds the same JSON for 30 days and then deletes it, and
    the JSONL exists only if somebody kept the file — so this row is the *only*
    durable proof of how many simulated decisions a version accumulated, which
    is the number ``docs/plans/REPLICATION.md`` reasons about.
    """
    config = alembic_config(upgraded)
    version_id = _strategy_version(upgraded, key=f"replay-guard-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    _write_receipt(
        upgraded, _receipt_row(version_id=version_id, run_id=run_id, day_from=8, day_to=11)
    )
    try:
        # 0014 sits above 0013 and reverses freely, so "-1" from head is not
        # this guard's step: walk down to the revision under test first, the
        # way the 0003 guards above already do.
        command.downgrade(config, REPLAY_RUNS_REVISION)
        with pytest.raises(DBAPIError, match="replay_runs rows would be dropped"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == REPLAY_RUNS_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(config, "head")
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)


def test_0013_reverses_on_a_database_that_never_replayed(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back: down one, up to
    head, ``alembic check`` at the end — over a database that trips no guard.

    A database where no replay ever ran counts zero receipts, and the guard is
    then exactly what it claims to be: a refusal to lose evidence, never a
    refusal to reverse.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, REPLAY_RUNS_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == REPLICATION_REVISION
        assert not asyncio.run(_relation_exists(upgraded, "replay_runs"))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_relation_exists(upgraded, "replay_runs"))
    command.check(config)


async def _relation_exists(url: str, name: str) -> bool:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(await connection.scalar(text("SELECT to_regclass(:name)"), {"name": name}))
    finally:
        await engine.dispose()


def test_0014_installs_the_two_cohort_indexes_and_reverses(upgraded: str) -> None:
    """The indexes exist at head, name the cohort expression, and go away.

    Read from ``pg_indexes.indexdef`` rather than from the model: Alembic does
    not compare an index expression (§17.3 makes the same argument about a
    predicate), so the catalogue is the only place that can say the index the
    planner will see is the one the revision meant to build.
    """
    config = alembic_config(upgraded)
    for name in ("ix_agent_signals_cohort_emitted", "ix_agent_signals_version_cohort_emitted"):
        definition = asyncio.run(_index_definition(upgraded, name))
        assert "supporting_features ->> 'cohort'" in definition, definition
        assert "emitted_at" in definition and definition.rstrip().endswith("id)"), definition

    # Named, not ``-1``: ``0015`` is head now, and a relative step would land on
    # ``0014`` and assert nothing about the indexes it is here to check.
    command.downgrade(config, REPLAY_RUNS_REVISION)
    try:
        assert asyncio.run(_revision(upgraded)) == REPLAY_RUNS_REVISION
        for name in ("ix_agent_signals_cohort_emitted", "ix_agent_signals_version_cohort_emitted"):
            assert asyncio.run(_index_definition(upgraded, name)) == ""
        assert asyncio.run(_relation_exists(upgraded, "agent_signals")), (
            "dropping an index must not touch the table"
        )
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0014_cannot_index_the_envelope_copy_of_decision_at(upgraded: str) -> None:
    """Why the sort key is ``emitted_at`` and not ``supporting_features->>'decision_at'``.

    ``text -> timestamptz`` runs ``timestamptz_in``, which is ``STABLE`` (it
    accepts ``'now'`` and reads ``TimeZone``), so Postgres refuses to build any
    index on that cast — and would refuse a ``GENERATED`` column for it too.
    The two indexes T3.37a asked for are not writable as written; this test is
    the reason DATABASE.md §26 tells the API to name the column instead.
    """
    engine = async_engine(upgraded)

    async def attempt() -> str:
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "CREATE INDEX ix_agent_signals_decision_at_probe ON agent_signals "
                        "(((supporting_features ->> 'decision_at')::timestamptz), id)"
                    )
                )
        except DBAPIError as error:
            return str(error)
        finally:
            await engine.dispose()
        return ""

    message = asyncio.run(attempt())
    assert "must be marked IMMUTABLE" in message, message
    assert asyncio.run(_index_definition(upgraded, "ix_agent_signals_decision_at_probe")) == ""


# ---------------------------------------------------------------------------
# 0015_runtime_login_role — DATABASE.md §27
# ---------------------------------------------------------------------------


async def _role_attributes(url: str, role: str) -> dict[str, bool] | None:
    """The seven ``pg_roles`` flags that decide what a login may do."""
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, "
                        "rolcreatedb, rolreplication, rolinherit "
                        "FROM pg_roles WHERE rolname = :role"
                    ),
                    {"role": role},
                )
            ).first()
    finally:
        await engine.dispose()
    if row is None:
        return None
    keys = ("login", "super", "bypassrls", "createrole", "createdb", "replication", "inherit")
    return dict(zip(keys, row, strict=True))


async def _memberships(url: str, role: str) -> dict[str, tuple[bool, bool]]:
    """``{granted role: (may SET ROLE, inherits its privileges)}``.

    Asked through ``pg_has_role`` rather than read out of ``pg_auth_members``:
    "may become" and "already holds" are two different questions, and it is the
    second one that ``NOINHERIT`` exists to answer *no* to (§27.1).
    """
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        "SELECT g.rolname, pg_has_role(:role, g.rolname, 'MEMBER'), "
                        "pg_has_role(:role, g.rolname, 'USAGE') "
                        "FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
                        "WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = :role)"
                    ),
                    {"role": role},
                )
            ).all()
    finally:
        await engine.dispose()
    return {name: (member, usage) for name, member, usage in rows}


def test_0015_creates_a_login_that_owns_nothing_and_bypasses_nothing(upgraded: str) -> None:
    """The seven attributes of the runtime login, read from the catalogue.

    Every one of them is a way the T3.15d finding stays open if it is wrong:
    ``rolsuper``/``rolbypassrls`` make the ``SET LOCAL ROLE`` decorative again,
    ``rolcreaterole`` lets the process mint itself a better credential, and
    ``rolinherit`` hands it the union of both application roles without any
    ``SET ROLE`` — which is what makes the schema's own guards stop firing
    (§27.1).
    """
    runtime = migration_ddl("runtime_login_role")
    role = cast(str, runtime.RUNTIME_ROLE)

    attributes = asyncio.run(_role_attributes(upgraded, role))

    assert attributes is not None, f"{role} was not created by 0015"
    assert attributes == {
        "login": True,
        "super": False,
        "bypassrls": False,
        "createrole": False,
        "createdb": False,
        "replication": False,
        "inherit": False,
    }


def test_0015_grants_exactly_two_memberships_and_inherits_neither(upgraded: str) -> None:
    """``hunter_app`` and ``hunter_worker``, reachable by ``SET ROLE`` and only so.

    The third assertion is the security boundary itself: this login has no
    privilege of its own, so *which roles it may become* is the whole of what it
    can do. A membership nobody wrote down would widen that silently, and the
    migration refuses one — this is the test that proves the refusal has
    something true to protect.
    """
    runtime = migration_ddl("runtime_login_role")
    role = cast(str, runtime.RUNTIME_ROLE)
    expected = set(cast(tuple[str, ...], runtime.RUNTIME_MEMBER_OF_0015))

    memberships = asyncio.run(_memberships(upgraded, role))

    assert set(memberships) == expected, memberships
    for granted, (may_set_role, inherits) in memberships.items():
        assert may_set_role, f"{role} cannot SET ROLE {granted}"
        assert not inherits, f"{role} inherits {granted}'s privileges without SET ROLE"


def test_0015_reverses_by_taking_the_membership_away(upgraded: str) -> None:
    """``downgrade -1`` leaves the login unable to become anything, and re-applying
    restores it.

    The role itself may survive the downgrade and that is deliberate (§27.3): it
    is a *cluster* object, and another database in this same container is still
    on ``0015`` with its own ``GRANT CONNECT`` in ``pg_shdepend``. What the
    downgrade has to remove is the *reach*, and the reach is the membership —
    which is exactly what is asserted here rather than "the role is gone".
    """
    runtime = migration_ddl("runtime_login_role")
    role = cast(str, runtime.RUNTIME_ROLE)
    config = alembic_config(upgraded)

    # The head is ``0016`` since T3.44c, and it reverses cleanly (one enum label)
    # — step down to ``0015`` first so ``-1`` means *this* revision again, the
    # same shape ``test_0010_refuses_to_downgrade_...`` uses for ``0011`` sitting
    # on top of ``0010``.
    command.downgrade(config, RUNTIME_LOGIN_ROLE_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == LAB_SIGNALS_INDEXES_REVISION
        assert asyncio.run(_memberships(upgraded, role)) == {}, (
            "the downgrade must leave the runtime login unable to SET ROLE anywhere"
        )
    finally:
        command.upgrade(config, "head")

    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert set(asyncio.run(_memberships(upgraded, role))) == set(
        cast(tuple[str, ...], runtime.RUNTIME_MEMBER_OF_0015)
    )
    command.check(config)


def test_0015_is_idempotent_over_a_role_that_already_exists(upgraded: str) -> None:
    """Re-applying ``0015`` on a cluster that already has the role is a no-op.

    Roles are cluster-wide, so the *second* database migrated in a cluster always
    hits this path — ``CREATE ROLE`` raises ``duplicate_object`` and everything
    after it has to be idempotent anyway. Proved by running the whole revision
    again over itself, which is what ``downgrade``/``upgrade`` in another database
    of the same container amounts to.
    """
    runtime = migration_ddl("runtime_login_role")
    role = cast(str, runtime.RUNTIME_ROLE)
    config = alembic_config(upgraded)

    # Down *past* ``0015`` (the head is ``0016`` since T3.44c, and ``-1`` alone
    # would stop on top of the role instead of dropping it), then back up, twice.
    command.downgrade(config, LAB_SIGNALS_INDEXES_REVISION)
    command.upgrade(config, "head")
    command.downgrade(config, LAB_SIGNALS_INDEXES_REVISION)
    command.upgrade(config, "head")

    attributes = asyncio.run(_role_attributes(upgraded, role))
    assert attributes is not None
    assert attributes["login"] and not attributes["inherit"] and not attributes["bypassrls"]
    assert set(asyncio.run(_memberships(upgraded, role))) == set(
        cast(tuple[str, ...], runtime.RUNTIME_MEMBER_OF_0015)
    )
    command.check(config)


# --------------------------------------------------------------------------
# 0016_exchange_status_planned — a venue nobody collects stops being a broken
# feed
# --------------------------------------------------------------------------


async def _write_exchange(url: str, code: str, status: str) -> uuid.UUID:
    """One ``exchanges`` row with an explicit ``status``, as the seed writes it."""
    exchange_id = uuid7()
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO exchanges (id, code, name, status, capabilities) "
                    "VALUES (:id, :code, :name, CAST(:status AS exchange_status), '{}'::jsonb)"
                ),
                {"id": exchange_id, "code": code, "name": code.title(), "status": status},
            )
    finally:
        await engine.dispose()
    return exchange_id


async def _forget_exchange(url: str, exchange_id: uuid.UUID) -> None:
    engine = async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM exchanges WHERE id = :id"), {"id": exchange_id}
            )
    finally:
        await engine.dispose()


def test_0016_adds_planned_before_active_and_nowhere_else(upgraded: str) -> None:
    """The label exists, in the position the contract fixes, on one type only.

    ``enumsortorder`` is part of the contract (§17.1) and
    ``hunter_core.domain.enums.ExchangeStatus`` declares ``PLANNED`` first;
    ``test_each_revision_creates_exactly_the_labels_it_froze`` compares the two
    at head, so what is left to prove here is the *shape* of the change — one
    type, one label, ``BEFORE 'active'``, and ``inactive`` untouched behind it.
    """
    labels = asyncio.run(_enum_labels(upgraded))
    assert labels["exchange_status"] == ["planned", "active", "inactive"]


def test_0016_lets_a_venue_be_catalogued_without_a_collector(upgraded: str) -> None:
    """The label the whole revision exists for: writable, and the default is not it.

    ``0001`` gave ``exchanges.status`` ``server_default 'active'`` and this
    revision deliberately leaves it there — a venue is active unless somebody
    says otherwise, and ``planned`` is said by the seed, never inherited.
    """
    planned = asyncio.run(_write_exchange(upgraded, f"planned-{uuid.uuid4().hex[:6]}", "planned"))
    try:
        stored = asyncio.run(
            _scalars(
                upgraded,
                "SELECT status::text FROM exchanges WHERE id = :id",
                {"id": planned},
            )
        )
        assert stored == ["planned"]
        default = asyncio.run(
            _scalars(
                upgraded,
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'exchanges' AND column_name = 'status'",
                {},
            )
        )
        assert default == ["'active'::exchange_status"]
    finally:
        asyncio.run(_forget_exchange(upgraded, planned))


def test_0016_refuses_to_downgrade_while_a_venue_is_planned(upgraded: str) -> None:
    """Rebuilding the type under such a row would have to rewrite it into a
    label that means something else — ``active`` puts it straight back into the
    market-status aggregate this revision exists to fix, ``inactive`` claims
    somebody switched it off. The guard counts and names them instead.
    """
    config = alembic_config(upgraded)
    planned = asyncio.run(_write_exchange(upgraded, f"guard-{uuid.uuid4().hex[:6]}", "planned"))
    try:
        # The head is ``0017`` since T3.52 — step down to ``0016`` first so
        # ``-1`` means *this* revision again (the shape the ``0015`` tests use).
        command.downgrade(config, EXCHANGE_STATUS_REVISION)
        with pytest.raises(DBAPIError, match="still status = 'planned'"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == EXCHANGE_STATUS_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(config, "head")
        asyncio.run(_forget_exchange(upgraded, planned))
    command.check(config)


def test_0016_reverses_on_a_database_where_nothing_is_planned(upgraded: str) -> None:
    """The round trip over a populated ``exchanges``, and what the rebuild keeps.

    A retype that dropped the server default, or reordered the two surviving
    labels, would leave ``alembic check`` clean and every future ``INSERT``
    wrong — so the default and the label order are read back from the catalogue
    at the bottom of the trip, not assumed from the fact that it ran.
    """
    config = alembic_config(upgraded)
    active = asyncio.run(_write_exchange(upgraded, f"trip-{uuid.uuid4().hex[:6]}", "active"))
    try:
        # Head is ``0017`` since T3.52: reach ``0016`` before stepping over it.
        command.downgrade(config, EXCHANGE_STATUS_REVISION)
        command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == RUNTIME_LOGIN_ROLE_REVISION
        assert asyncio.run(_enum_labels(upgraded))["exchange_status"] == ["active", "inactive"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_name = 'exchanges' AND column_name = 'status'",
                {},
            )
        ) == ["'active'::exchange_status"]
        assert asyncio.run(
            _scalars(upgraded, "SELECT status::text FROM exchanges WHERE id = :id", {"id": active})
        ) == ["active"]
    finally:
        command.upgrade(config, "head")
        asyncio.run(_forget_exchange(upgraded, active))
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


# --------------------------------------------------------------------------
# 0017_eligibility_policy — the context a version is allowed to decide in
# --------------------------------------------------------------------------

_GATE = '{"regime": {"allow": ["SIDEWAYS"], "scope": "btc"}}'


def _forget_gated_draft(url: str, version_id: uuid.UUID) -> None:
    """:func:`_forget_draft_strategy_version` by another name — a draft carrying
    a policy left behind would trip section 29's downgrade guard for every later
    test that reverses past ``0017``, for a reason that test never created."""
    _forget_draft_strategy_version(url, version_id)


def test_0017_adds_a_nullable_policy_column_with_no_default(upgraded: str) -> None:
    """``NULL`` is the honest backfill: every version that exists decides in
    every regime, and that is what "no policy" means (DATABASE.md §29)."""
    assert asyncio.run(_column_exists(upgraded, "strategy_versions", "eligibility_policy"))
    shape = asyncio.run(
        _scalars(
            upgraded,
            "SELECT data_type || '/' || is_nullable || '/' || coalesce(column_default, 'none') "
            "FROM information_schema.columns WHERE table_name = 'strategy_versions' "
            "AND column_name = 'eligibility_policy'",
            {},
        )
    )
    assert shape == ["jsonb/YES/none"]
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM strategy_versions WHERE eligibility_policy IS NOT NULL",
            {},
        )
    ) == ["0"]


def test_0017_widens_the_freeze_trigger_to_cover_the_policy(upgraded: str) -> None:
    """The installed body is ``0017``'s, and it still carries everything
    ``0002``, ``0010`` and ``0012`` froze — this widens the trigger, it does not
    replace what it already protected (read from ``pg_proc``: Alembic never
    compares a function, §17.3).

    The ``0012`` lines are the ones worth naming: a revision that had copied
    ``0010``'s column list would have *narrowed* the trigger back and unfrozen
    the replication lineage without a word.

    The comparison is the **whole list**, in order, and not a handful of ``in``
    checks: a substring passes on any superset, so it can see a column arrive
    but never see one leave. The promising marker is asserted against the list
    for the same reason — the words ``promising_at`` do appear in the body, in
    the ``HINT`` that tells the operator it stays mutable, and a body-wide
    substring check on them was a test that could only ever pass.
    """
    expected = cast("tuple[str, ...]", migration_ddl("eligibility_policy")._FROZEN_COLUMNS_0017)
    body = asyncio.run(_function_source(upgraded, "shadow_freeze_strategy_version"))
    assert _frozen_columns(body) == expected
    assert len(expected) == 11, "0012's ten columns plus eligibility_policy — no more, no fewer"
    assert "eligibility_policy" in expected
    assert {"purpose", "code_ref", "replication_parent_id", "replication_index"} <= set(expected)
    assert not {"promising_at", "promising_by"} & set(expected), (
        "the marker is written after activation, by definition"
    )
    assert "promising_at and deprecated_at stay mutable" in body, "and the HINT still says so"


def test_0017_freezes_the_policy_after_activation(upgraded: str) -> None:
    """A gate that could move after activation would silently change what every
    already-measured cohort of that version meant.

    The probe is activated **without** a policy and the ``UPDATE`` tries to give
    it one, rather than the other way round, for a reason about this file and
    not about the trigger: an activated row can never be deleted (that is what
    ``0002``'s delete guard is for), so a gated activated row would sit in this
    module-scoped database forever and trip section 29's downgrade guard for
    every later test that reverses past ``0017``. The trigger compares ``IS
    DISTINCT FROM``, so adding a gate and changing one are the same code path —
    proved once, without leaving a landmine.
    """
    version_id = _strategy_version(
        upgraded, key=f"gate-frozen-{uuid.uuid4().hex[:8]}", activated=True
    )
    with pytest.raises(DBAPIError, match="eligibility_policy cannot change"):
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "UPDATE strategy_versions SET eligibility_policy = "
                        "CAST(:policy AS jsonb) WHERE id = :id",
                        {"id": version_id, "policy": _GATE},
                    )
                ],
            )
        )
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM strategy_versions WHERE id = :id "
            "AND eligibility_policy IS NULL",
            {"id": version_id},
        )
    ) == ["1"]


def test_0017_lets_a_draft_be_gated_before_it_is_activated(upgraded: str) -> None:
    """``derive_variant.py`` writes the policy into a ``draft`` row and the
    activation only flips ``status``/``activated_at``/``changelog``: the trigger
    must not stand in the way of the path that actually writes this column."""
    version_id = _strategy_version(upgraded, key=f"gate-draft-{uuid.uuid4().hex[:8]}")
    try:
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "UPDATE strategy_versions SET eligibility_policy = CAST(:policy AS jsonb) "
                        "WHERE id = :id",
                        {"id": version_id, "policy": _GATE},
                    )
                ],
            )
        )
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT eligibility_policy->'regime'->>'scope' FROM strategy_versions "
                "WHERE id = :id",
                {"id": version_id},
            )
        ) == ["btc"]
    finally:
        _forget_gated_draft(upgraded, version_id)


def test_0017_leaves_the_gate_readable_by_both_roles_and_writable_by_neither(
    upgraded: str,
) -> None:
    """No ``GRANT`` in this revision, and that is the point: ``0010`` re-granted
    ``strategy_versions`` column by column, so a column added later is outside
    every grant the table has — only the owner connection writes it (§29)."""
    for role in ("hunter_worker", "hunter_app"):
        assert not asyncio.run(
            _column_privilege(upgraded, role, "strategy_versions", "eligibility_policy")
        ), f"{role} may UPDATE the gate"
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT has_column_privilege(:role, 'strategy_versions', "
                "'eligibility_policy', 'INSERT')::text",
                {"role": role},
            )
        ) == ["false"], f"{role} may INSERT the gate"
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT has_column_privilege(:role, 'strategy_versions', "
                "'eligibility_policy', 'SELECT')::text",
                {"role": role},
            )
        ) == ["true"], f"{role} cannot read the gate"


def test_0017_refuses_to_downgrade_while_a_version_is_gated(upgraded: str) -> None:
    """Dropping the column would widen a version built for one regime back to
    every regime, silently, with nothing left to reconstruct the intent from."""
    config = alembic_config(upgraded)
    version_id = _strategy_version(upgraded, key=f"gate-guard-{uuid.uuid4().hex[:8]}", policy=_GATE)
    try:
        # The head is ``0018`` since T3.67 — step down to ``0017`` first so
        # ``-1`` means *this* revision again (the shape the 0013/0016 tests use).
        command.downgrade(config, ELIGIBILITY_POLICY_REVISION)
        with pytest.raises(DBAPIError, match="carry an eligibility_policy"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == ELIGIBILITY_POLICY_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(config, "head")
        _forget_gated_draft(upgraded, version_id)
    command.check(config)


def test_0017_reverses_on_a_database_where_nothing_is_gated(upgraded: str) -> None:
    """The round trip, and what the reversal restores: ``0012``'s trigger — the
    lineage and ``purpose`` still frozen, and no idea what an
    ``eligibility_policy`` is."""
    config = alembic_config(upgraded)
    try:
        # Head is ``0018`` since T3.67: reach ``0017`` before stepping over it.
        command.downgrade(config, ELIGIBILITY_POLICY_REVISION)
        command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == EXCHANGE_STATUS_REVISION
        assert not asyncio.run(_column_exists(upgraded, "strategy_versions", "eligibility_policy"))
        restored = cast("tuple[str, ...]", migration_ddl("replication")._FROZEN_COLUMNS_0012)
        reverted = asyncio.run(_function_source(upgraded, "shadow_freeze_strategy_version"))
        assert _frozen_columns(reverted) == restored
        assert len(restored) == 10, "0017's eleven minus eligibility_policy"
        assert {"purpose", "replication_parent_id", "replication_index"} <= set(restored)
        assert "eligibility_policy" not in reverted
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_column_exists(upgraded, "strategy_versions", "eligibility_policy"))
    command.check(config)


# --------------------------------------------------------------------------
# 0018_replay_runs_slice_markets — a slice is a window and the markets it saw
# --------------------------------------------------------------------------

_T362_SLICES: tuple[tuple[str, ...], ...] = (
    ("binance:ETHUSDT", "binance:SOLUSDT", "binance:XRPUSDT", "binance:DOGEUSDT"),
    ("binance:BTCUSDT", "binance:BNBUSDT", "binance:ZECUSDT", "binance:SUIUSDT"),
    ("binance:NEARUSDT", "binance:UNIUSDT", "binance:ARBUSDT", "binance:TAOUSDT"),
    ("binance:LINKUSDT", "binance:DASHUSDT", "binance:PROMUSDT", "binance:SAHARAUSDT"),
)
"""The four market slices of one window that T3.62 ran under one cohort, and of
which ``0013``'s key kept exactly one (``.claude/state/notes-T3.62.md`` §2.3)."""


def _write_receipt_with_digest(url: str, row: dict[str, object], digest: str) -> None:
    """Insert a receipt naming its own digest, the way ``replay/ledger.py`` does.

    ``_write_receipt`` leaves the column out and lets the trigger derive it;
    this is the other half — the writer sending the value it computed, which is
    what makes the Python and the SQL digest compared on every insert instead of
    assumed equal.
    """
    columns = f"{_RECEIPT_COLUMNS}, markets_digest"
    values = f"{_RECEIPT_VALUES}, :digest"
    statement = f"INSERT INTO replay_runs ({columns}) VALUES ({values})"  # noqa: S608
    asyncio.run(_write(url, [(statement, {**row, "digest": digest})]))


def test_0018_the_python_digest_and_the_sql_expression_are_one_function(upgraded: str) -> None:
    """The writer hashes in Python; the backfill and the trigger hash in SQL.

    They are a copy of one another on purpose (the database's contract must not
    follow a later edit to a Python constant — ``ddl/paper_geometry.py``), so
    this is what keeps the copy honest. If the two ever drifted, a receipt
    written by the worker would be refused by the trigger *or*, worse, two
    market slices would hash alike again and one of them would vanish under
    ``ON CONFLICT DO NOTHING`` — the T3.62 failure, re-armed.

    The collation case is the one worth naming: the SQL side sorts ``COLLATE
    "C"`` and Python sorts code points. Under the database's default collation
    ``{"A","a","B"}`` orders differently, so the mixed-case list here is what
    would fail if that clause were ever dropped.
    """
    from hunter_core.domain.digests import MARKETS_DIGEST_PATTERN, markets_digest

    ddl = migration_ddl("replay_runs_slice_markets")
    assert ddl.MARKETS_DIGEST_PATTERN_0018 == MARKETS_DIGEST_PATTERN
    assert ddl.SLICE_KEY_0018 == (*ddl.SLICE_KEY_0013, "markets_digest"), (
        "the new key must be a strict superset of 0013's, or a stored row could start colliding"
    )
    lists = [
        list(_T362_SLICES[0]),
        list(reversed(_T362_SLICES[0])),
        ["binance:BTCUSDT"],
        ["A", "a", "B"],
        ["a", "bc"],
        ["ab", "c"],
        ["binance:BTCUSDT", "binance:BTCUSDT"],
    ]
    query = f"SELECT {ddl.digest_sql('CAST(:markets AS text[])')}"
    for markets in lists:
        assert asyncio.run(_scalars(upgraded, query, {"markets": markets})) == [
            markets_digest(markets)
        ], f"the two halves of the digest disagree on {markets}"


def test_0018_keeps_the_four_market_slices_of_one_window(upgraded: str) -> None:
    """The bug this revision exists for, as one assertion.

    T3.62 ran 32 slices under four cohorts — four market slices inside each
    window — and ``replay_runs`` kept **8** rows, because
    ``ON CONFLICT (run_id, window_from, window_to) DO NOTHING`` treated the
    second, third and fourth as the first replayed twice. Nothing failed and
    nothing logged above ``info``: the receipt read ``mkts = 4, bars = 5760``
    for work that was 16 markets and 47 616 bars.

    The second half is the property that makes the digest a *key* and not a
    label: the same four markets in the other dispatch order are the same
    slice, and re-running it still writes one receipt, not two.
    """
    version_id = _strategy_version(upgraded, key=f"slice-markets-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    try:
        for markets in _T362_SLICES:
            _write_receipt(
                upgraded,
                _receipt_row(
                    version_id=version_id,
                    run_id=run_id,
                    day_from=8,
                    day_to=23,
                    markets=list(markets),
                ),
            )
        measured = asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*) || '/' || count(DISTINCT markets_digest) || '/' || "
                "sum(bars_evaluated) FROM replay_runs WHERE run_id = :id",
                {"id": run_id},
            )
        )
        assert measured == ["4/4/3456"], (
            "four market slices of one window are four receipts, and bars_evaluated sums"
        )
        with pytest.raises(DBAPIError, match="uq_replay_runs_slice"):
            _write_receipt(
                upgraded,
                _receipt_row(
                    version_id=version_id,
                    run_id=run_id,
                    day_from=8,
                    day_to=23,
                    markets=list(reversed(_T362_SLICES[0])),
                ),
            )
    finally:
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)


@pytest.mark.parametrize("digest", ["a" * 64, "legacy", ""])
def test_0018_refuses_a_digest_that_does_not_name_its_own_markets(
    upgraded: str, digest: str
) -> None:
    """A copy that can disagree with its source is worse than no copy (§18.2).

    A *wrong* digest is not a cosmetic error here: two different market slices
    that happen to share one collide on the slice key again, and the second is
    discarded in silence — exactly the failure being closed. ``'legacy'`` is in
    the list because a sentinel is the obvious shortcut a future backfill would
    reach for, and the schema has to be the thing that refuses it.
    """
    version_id = _strategy_version(upgraded, key=f"digest-lies-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    try:
        with pytest.raises(DBAPIError, match="does not name its own markets"):
            _write_receipt_with_digest(
                upgraded,
                _receipt_row(version_id=version_id, run_id=run_id, day_from=8, day_to=11),
                digest,
            )
    finally:
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)


def test_0018_derives_a_stored_receipt_instead_of_stamping_a_sentinel(upgraded: str) -> None:
    """The backfill, proved over a real round trip on a populated table.

    ``markets text[] NOT NULL`` has been on the row since ``0013``, so the
    digest of a receipt written before this revision is *derivable* — the
    ``0002`` boundary (backfill what the columns imply, refuse what they merely
    suggest). This drops the column with a receipt in the table and puts it
    back, then checks the value came back **byte for byte**: nothing was
    invented, and there is no ``'legacy'`` placeholder to invent it with.
    """
    from hunter_core.domain.digests import markets_digest

    config = alembic_config(upgraded)
    version_id = _strategy_version(upgraded, key=f"digest-backfill-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    markets = list(_T362_SLICES[0])
    read = "SELECT markets_digest FROM replay_runs WHERE run_id = :id"
    _write_receipt(
        upgraded,
        _receipt_row(version_id=version_id, run_id=run_id, day_from=8, day_to=11, markets=markets),
    )
    try:
        before = asyncio.run(_scalars(upgraded, read, {"id": run_id}))
        assert before == [markets_digest(markets)]
        command.downgrade(config, ELIGIBILITY_POLICY_REVISION)
        assert not asyncio.run(_column_exists(upgraded, "replay_runs", "markets_digest"))
        command.upgrade(config, "head")
        assert asyncio.run(_scalars(upgraded, read, {"id": run_id})) == before, (
            "the backfill re-derived a different value than the one it lost"
        )
    finally:
        command.upgrade(config, "head")
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)


def test_0018_refuses_to_downgrade_while_a_window_holds_two_market_slices(upgraded: str) -> None:
    """§17.7: reversing is allowed, losing evidence is not.

    ``0013``'s key is *narrower*, so a database that already recorded what this
    revision made recordable cannot go back without deleting receipts of
    replays that really ran. Postgres would refuse the constraint anyway; the
    guard refuses **first**, counting the windows and naming the export, rather
    than dying inside ``ADD CONSTRAINT`` with a message that names no way out
    (the ``0016`` argument, §28.3).
    """
    config = alembic_config(upgraded)
    version_id = _strategy_version(upgraded, key=f"slice-guard-{uuid.uuid4().hex[:8]}")
    run_id = uuid7()
    for markets in _T362_SLICES[:2]:
        _write_receipt(
            upgraded,
            _receipt_row(
                version_id=version_id, run_id=run_id, day_from=8, day_to=23, markets=list(markets)
            ),
        )
    try:
        # Down to 0018 first: this test is about **0018**'s guard, and the
        # revisions above it have guards of their own that would fire (or not)
        # for reasons that have nothing to do with a replay slice.
        command.downgrade(config, REPLAY_SLICE_REVISION)
        with pytest.raises(DBAPIError, match="hold more than one market slice"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == REPLAY_SLICE_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        command.upgrade(config, "head")
        _forget_receipts(upgraded, run_id)
        _forget_draft_strategy_version(upgraded, version_id)
    command.check(config)


def test_0018_reverses_on_a_database_whose_windows_hold_one_slice_each(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back — down one, up to
    head, ``alembic check`` at the end — over a database that trips no guard.

    What the reversal restores is asserted, not assumed: ``0013``'s three-column
    key, no column, no trigger, no function. Dropping the column is deliberately
    *not* guarded (unlike ``0013``'s own downgrade, which refuses while any
    receipt exists): the digest is derived from ``markets``, which stays, so
    nothing that survives the reversal is unrecoverable.
    """
    config = alembic_config(upgraded)
    key_of = (
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'uq_replay_runs_slice'"
    )
    # Named, not ``-1``: this test is about what reversing **0018** restores, and
    # ``-1`` means "one step back from whatever the head is". It stopped meaning
    # 0017 the day 0019 landed, and a test whose subject moves with the head is
    # a test that silently changes what it proves.
    command.downgrade(config, ELIGIBILITY_POLICY_REVISION)
    try:
        assert asyncio.run(_revision(upgraded)) == ELIGIBILITY_POLICY_REVISION
        assert not asyncio.run(_column_exists(upgraded, "replay_runs", "markets_digest"))
        assert asyncio.run(_scalars(upgraded, key_of, {})) == [
            "UNIQUE (run_id, window_from, window_to)"
        ]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM pg_trigger "
                "WHERE tgname = 'replay_runs_digest_names_the_markets'",
                {},
            )
        ) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM pg_proc "
                "WHERE proname = 'replay_runs_digest_names_the_markets'",
                {},
            )
        ) == ["0"]
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_scalars(upgraded, key_of, {})) == [
        "UNIQUE (run_id, window_from, window_to, markets_digest)"
    ]
    command.check(config)


def test_0018_leaves_replay_runs_global_and_append_only(upgraded: str) -> None:
    """The column changes what a receipt *is*, never who may touch one.

    Three properties, asserted because "did not need to change" and "was
    forgotten" are indistinguishable from outside (§25.5): ``replay_runs`` is
    still global — no ``organization_id``, therefore no RLS policy, and tenant
    isolation here is the *absence* of tenant data, not a policy someone could
    forget; the worker still reads and appends the new column through the table
    grant ``0013`` gave it; and it still cannot ``UPDATE`` or ``DELETE`` a
    receipt, the property that decided the slice-per-row shape (§25.1).
    """
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM information_schema.columns "
            "WHERE table_name = 'replay_runs' AND column_name = 'organization_id'",
            {},
        )
    ) == ["0"]
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
            "WHERE c.relname = 'replay_runs'",
            {},
        )
    ) == ["0"]
    for role, privilege, expected in (
        ("hunter_worker", "SELECT", "true"),
        ("hunter_worker", "INSERT", "true"),
        ("hunter_worker", "UPDATE", "false"),
        ("hunter_app", "SELECT", "true"),
        ("hunter_app", "INSERT", "false"),
    ):
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT has_column_privilege(:role, 'replay_runs', 'markets_digest', "
                ":privilege)::text",
                {"role": role, "privilege": privilege},
            )
        ) == [expected], f"{role} / {privilege} on markets_digest"
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT has_table_privilege('hunter_worker', 'replay_runs', 'DELETE')::text",
            {},
        )
    ) == ["false"]


# --------------------------------------------------------------------------
# 0019_market_breadth — the amplitude of the universe becomes a series
# --------------------------------------------------------------------------

_READING_INSERT = (
    "INSERT INTO market_breadth (id, exchange_id, end_time, window_minutes, breadth_version, "
    "universe_size, covered, falling, value, coverage, usable, reason, inputs) "
    "VALUES (:id, :exchange, :end_time, 5, 'breadth_v1', 200, 194, 188, 0.969072, 0.970000, "
    "true, NULL, '{}'::jsonb)"
)
"""The storm minute of 2026-09-09 22:08Z — 194 of 200 monitored perpetuals
falling together — which is the row this whole revision exists to hold."""

_GATE_LOOKUP = (
    "SELECT b.id, b.end_time, b.value, b.usable, b.reason, b.covered, b.universe_size "
    "  FROM market_breadth b JOIN exchanges e ON e.id = b.exchange_id "
    " WHERE e.code = :exchange AND b.breadth_version = :version "
    "   AND b.window_minutes = :window AND b.end_time = :cut"
)
"""``hunter_strategy_worker.breadth_gate._LOOKUP``, written out again rather than
imported: ``packages/core`` may not depend on a service, and a copy is also what
makes this an assertion about the *schema* — four equality predicates on the four
columns of ``uq_market_breadth_reading``, in its order — instead of an assertion
about whatever the gate happens to spell today."""


def _write_reading(url: str, exchange_id: uuid.UUID, *, minute: int = 8) -> uuid.UUID:
    reading_id = uuid7()
    asyncio.run(
        _write(
            url,
            [
                (
                    _READING_INSERT,
                    {
                        "id": reading_id,
                        "exchange": exchange_id,
                        "end_time": datetime(2026, 9, 9, 22, minute, tzinfo=UTC),
                    },
                )
            ],
        )
    )
    return reading_id


def _forget_readings(url: str, exchange_id: uuid.UUID) -> None:
    """``upgraded`` is module-scoped, and one reading left behind trips 0019's
    downgrade guard for every later test — the ``_forget_receipts`` rule."""
    asyncio.run(
        _write(
            url,
            [
                ("DELETE FROM market_breadth WHERE exchange_id = :id", {"id": exchange_id}),
                ("DELETE FROM exchanges WHERE id = :id", {"id": exchange_id}),
            ],
        )
    )


def test_0019_names_its_constraints_the_way_the_model_does(upgraded: str) -> None:
    """``0019`` writes literal SQL, so the three constraint names are spelled out
    in it; left implicit, Postgres would mint ``market_breadth_pkey`` and
    ``market_breadth_exchange_id_fkey`` while
    ``hunter_core.db.base.NAMING_CONVENTION`` says otherwise.

    ``alembic check`` does not compare constraint names, so nothing else would
    notice — until the revision that partitions this table has to
    ``DROP CONSTRAINT`` by name to put ``end_time`` into the primary key (§15.2)
    and is written against a name that is not there.
    """
    names = asyncio.run(
        _scalars(
            upgraded,
            "SELECT conname FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE t.relname = 'market_breadth' AND c.contype IN ('p', 'f', 'u') "
            "ORDER BY conname",
            {},
        )
    )
    assert names == [
        "fk_market_breadth_exchange_id_exchanges",
        "pk_market_breadth",
        "uq_market_breadth_reading",
    ]


def test_0019_carries_one_reading_index_and_answers_the_gates_probe_from_it(
    upgraded: str,
) -> None:
    """One btree, and it is the unique key's — T3.77c dropped the two redundant
    ones (a copy of the unique's columns, and a standalone index on its leading
    ``exchange_id``) before the revision ever shipped.

    Both halves matter. The count is the write path: this table takes one row per
    minute per venue, and three indexes to maintain where one answers everything
    is a cost paid forever. The plan is the read path: with sequential scans off,
    the gate's four equality predicates have to land on
    ``uq_market_breadth_reading`` — if they did not, dropping the copy would have
    cost the gate its index, which is the one way this change could be wrong.
    """
    indexes = asyncio.run(
        _scalars(
            upgraded,
            "SELECT indexname FROM pg_indexes WHERE tablename = 'market_breadth' "
            "ORDER BY indexname",
            {},
        )
    )
    assert indexes == ["pk_market_breadth", "uq_market_breadth_reading"]

    plan = "\n".join(
        asyncio.run(
            _explain(
                upgraded,
                _GATE_LOOKUP,
                {
                    "exchange": "binance",
                    "version": "breadth_v1",
                    "window": 5,
                    "cut": datetime(2026, 9, 9, 22, 8, tzinfo=UTC),
                },
            )
        )
    )
    assert "uq_market_breadth_reading" in plan, plan


def test_0019_refuses_a_downgrade_that_would_lose_a_reading(upgraded: str) -> None:
    """§17.7: reversing is allowed, losing evidence is not.

    The series is the one thing here that is **not recomputable after the fact**.
    A reading is the share of the *monitored* universe that fell, and
    ``markets.is_monitored`` is overwritten in place by every refresh — so the
    universe a minute of 2026-09-09 was measured against stops existing the
    moment the row does. Folding those candles again tomorrow answers a different
    question with the same name.
    """
    config = alembic_config(upgraded)
    exchange_id = asyncio.run(_write_exchange(upgraded, f"br-{uuid.uuid4().hex[:8]}", "active"))
    _write_reading(upgraded, exchange_id)
    try:
        # Stage at 0019 first — the pattern every older revision's tests use, and
        # necessary since 0020/0021 landed on top: ``"-1"`` from the head reverses
        # *them*, and this test is about what reversing **0019** refuses to do.
        command.downgrade(config, BREADTH_REVISION)
        with pytest.raises(DBAPIError, match="market_breadth readings exist"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == BREADTH_REVISION, "the downgrade must not commit"
        assert asyncio.run(_relation_exists(upgraded, "market_breadth")), (
            "a refused downgrade must leave the table exactly where it was"
        )
    finally:
        command.upgrade(config, "head")
        _forget_readings(upgraded, exchange_id)
    command.check(config)


def test_0019_reverses_on_a_database_that_never_read_the_universe(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back — down one, up to
    head, ``alembic check`` at the end — over a database that trips no guard.

    A database where the producer never ran counts zero readings, and the guard
    is then exactly what it claims to be: a refusal to lose evidence, never a
    refusal to reverse. What comes back is asserted too, because "the table
    returned" and "the table returned with its grants" are different facts:
    ``0019`` re-grants ``SELECT`` to ``hunter_app`` and ``SELECT``/``INSERT`` to
    ``hunter_worker``, and a re-applied revision that forgot them would leave the
    scanner unable to write and nothing else would say so.
    """
    config = alembic_config(upgraded)
    command.downgrade(config, BREADTH_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == REPLAY_SLICE_REVISION
        assert not asyncio.run(_relation_exists(upgraded, "market_breadth"))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_relation_exists(upgraded, "market_breadth"))
    for role, privilege, expected in (
        ("hunter_worker", "SELECT", "true"),
        ("hunter_worker", "INSERT", "true"),
        ("hunter_worker", "UPDATE", "false"),
        ("hunter_worker", "DELETE", "false"),
        ("hunter_app", "SELECT", "true"),
        ("hunter_app", "INSERT", "false"),
    ):
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT has_table_privilege(:role, 'market_breadth', :privilege)::text",
                {"role": role, "privilege": privilege},
            )
        ) == [expected], f"{role} / {privilege} on market_breadth"
    command.check(config)


def test_every_revision_id_fits_the_alembic_version_column() -> None:
    """``alembic_version.version_num`` is ``VARCHAR(32)`` (§17.6), and the way
    the project learned that was expensive: ``0005_feature_baselines_lock_grant``
    (33 characters) ran the whole revision and only then failed on the final
    ``UPDATE alembic_version``.

    Every revision docstring since states its own length, which is prose. This
    is the check (DATABASE.md §30): the declared ``revision`` of every file in
    ``versions/`` fits, and it is also the file's own name — a revision whose id
    and filename disagree is one that ``-k <id>`` cannot select and a history
    nobody can read in ``ls``.
    """
    versions = REPO_ROOT / "infra" / "migrations" / "versions"
    ids: list[str] = []
    for path in sorted(versions.glob("[0-9][0-9][0-9][0-9]_*.py")):
        declared = re.search(r'^revision: str = "([^"]+)"', path.read_text("utf-8"), re.MULTILINE)
        assert declared is not None, f"{path.name} declares no revision id"
        revision_id = declared.group(1)
        assert len(revision_id) <= 32, (
            f"{revision_id} is {len(revision_id)} characters; alembic_version.version_num is "
            "VARCHAR(32) and the failure lands after the revision has already run"
        )
        assert revision_id == path.stem, f"{path.name} declares {revision_id}"
        ids.append(revision_id)
    assert len(ids) == len(set(ids)), "two revision files declare the same id"
    assert ids[-1] == HEAD_REVISION, "the newest revision file is not the head these tests assert"


# ---------------------------------------------------------------------------
# 0021_meme_radar — the pump.fun storage, and what a downgrade may not lose
# ---------------------------------------------------------------------------

MEME_TABLES = (
    "meme_curve_snapshots",
    "meme_features_1m",
    "meme_ingest_gaps",
    "meme_tokens",
    "meme_trades",
)

_A_TOKEN = (
    "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at) "
    "VALUES (:mint, 'pumpportal_ws', now(), now())"
)

_RETENTION_MARKER: tuple[str, dict[str, object]] = ("SET LOCAL app.meme_retention = 'on'", {})


def test_0021_keeps_the_meme_tables_global_and_free_of_policies(upgraded: str) -> None:
    """The absence is **asserted**, not assumed (§25.5's rule).

    "Needs no policy" and "somebody forgot the policy" are indistinguishable from
    outside, and a tenant column appearing on one of these tables later would make
    RLS mandatory — this is the test that forces that conversation instead of
    letting the column arrive quietly.
    """
    tenant_columns = asyncio.run(
        _scalars(
            upgraded,
            "SELECT table_name || '.' || column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'organization_id' "
            "AND table_name LIKE 'meme%'",
            {},
        )
    )
    assert tenant_columns == []
    policies = asyncio.run(
        _scalars(
            upgraded,
            "SELECT c.relname FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
            "WHERE c.relname LIKE 'meme%'",
            {},
        )
    )
    assert policies == []


def test_0021_grants_read_to_the_api_and_append_to_the_worker(upgraded: str) -> None:
    """Four append-only tables, one upsert table, and ``SELECT`` for the API.

    ``meme_tokens`` is the single exception and a deliberate one: retention cannot
    drop a partition of a table keyed on the mint, so the worker has ``DELETE``
    there — gated by ``app.meme_retention`` in a trigger, the ``feature_baselines``
    precedent (§17.2).
    """
    for table in ("meme_curve_snapshots", "meme_features_1m", "meme_ingest_gaps", "meme_trades"):
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
        }, f"{table} is not append-only for the engine"
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", table)) == {"SELECT"}
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_tokens")) == {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    }
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "meme_tokens")) == {"SELECT"}
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "meme_radar_features_v1")) == {
        "SELECT"
    }


def test_0021_hardens_every_meme_partition_it_created(upgraded: str) -> None:
    """Access goes through the parent: Postgres checks a query naming a child
    against the **child's** privileges, which is how ``DELETE FROM
    audit_logs_2026_09`` once got through (§15.6)."""
    meme = migration_ddl("meme_radar")
    parents = cast("tuple[str, ...]", meme.MEME_PARTITIONED_TABLES_0021)
    months = cast("tuple[tuple[int, int], ...]", meme.MEME_INITIAL_MONTHS_0021)
    children = [f"{parent}_{year:04d}_{month:02d}" for parent in parents for year, month in months]
    assert len(children) == 12

    present = set(
        asyncio.run(
            _scalars(
                upgraded,
                "SELECT relname FROM pg_class WHERE relispartition AND relkind = 'r' "
                "AND relname LIKE 'meme%'",
                {},
            )
        )
    )
    assert set(children) <= present
    for child in children:
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", child)) == set(), child
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", child)) == set(), child


def test_0021_generates_the_market_cap_and_a_zero_reserve_is_not_an_outage(
    upgraded: str,
) -> None:
    """§15.8 kept intact: a feed's zero yields a NULL market cap, not a failed
    insert. A plain division would raise inside the statement, which is worse than
    the CHECK that section refuses to put on market data."""
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "INSERT INTO meme_curve_snapshots (observed_at, mint, source, "
                    "virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, "
                    "real_token_reserves, total_supply, complete) VALUES "
                    "('2026-10-05T12:00:00Z', 'MCAP', 'solana_rpc', 30, 1073000000, 0, "
                    "793100000, 1000000000, false), "
                    "('2026-10-05T12:00:00Z', 'ZERO', 'solana_rpc', 30, 0, 0, 0, "
                    "1000000000, true)",
                    {},
                )
            ],
        )
    )
    try:
        values = asyncio.run(
            _scalars(
                upgraded,
                "SELECT coalesce(mcap_sol::text, 'null') FROM meme_curve_snapshots "
                "WHERE mint IN ('MCAP', 'ZERO') ORDER BY mint",
                {},
            )
        )
        assert values[0].startswith("27.95899347"), values
        assert values[1] == "null"
    finally:
        asyncio.run(
            _write(
                upgraded,
                [("DELETE FROM meme_curve_snapshots WHERE mint IN ('MCAP', 'ZERO')", {})],
            )
        )


def test_0021_refuses_a_downgrade_that_would_lose_discovery(upgraded: str) -> None:
    """§17.7: reversing is allowed, losing evidence is not.

    Discovery is the one thing here that cannot be recovered after the fact: the
    PumpPortal feed is ephemeral and the REST mirror only lists what is recent, so
    the universe of creations every graduation and rug rate is counted against
    stops existing the moment the rows do.
    """
    config = alembic_config(upgraded)
    asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "GUARD_MINT"})]))
    try:
        # Stage at 0021 first: ``0022`` sits on top and ``"-1"`` from the head
        # would reverse *it* (the seed alone reverses), not the radar.
        command.downgrade(config, MEME_RADAR_REVISION)
        with pytest.raises(DBAPIError, match="meme_tokens rows exist"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == MEME_RADAR_REVISION, (
            "the downgrade must not commit"
        )
        assert asyncio.run(_relation_exists(upgraded, "meme_tokens")), (
            "a refused downgrade must leave the schema exactly where it was"
        )
    finally:
        command.upgrade(config, "head")
        asyncio.run(
            _write(
                upgraded,
                [
                    _RETENTION_MARKER,
                    ("DELETE FROM meme_tokens WHERE mint = :mint", {"mint": "GUARD_MINT"}),
                ],
            )
        )
    command.check(config)


def test_0021_reverses_on_a_database_that_never_watched_a_mint(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back, over a database that
    trips no guard — and what comes back is checked, because "the tables returned"
    and "the tables returned with their grants and their view" are different
    facts."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_RADAR_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) not in (HEAD_REVISION, MEME_RADAR_REVISION)
        for table in MEME_TABLES:
            assert not asyncio.run(_relation_exists(upgraded, table)), table
        assert not asyncio.run(_relation_exists(upgraded, "meme_radar_features_v1"))
        assert not asyncio.run(_trigger_exists(upgraded, "meme_tokens_identity_is_written_once"))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    for table in MEME_TABLES:
        assert asyncio.run(_relation_exists(upgraded, table)), table
    assert asyncio.run(_relation_exists(upgraded, "meme_radar_features_v1"))
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_features_1m")) == {
        "SELECT",
        "INSERT",
    }
    command.check(config)


def test_0021_freezes_an_identity_and_still_lets_the_lifecycle_move(upgraded: str) -> None:
    """The trigger is the lock, not the grant: ``UPDATE`` is granted because a
    token's lifecycle genuinely moves, and what keeps that from becoming a rewrite
    of history is a refusal that applies to **every** role, owner included — which
    is what this test runs as."""
    asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "FREEZE_MINT"})]))
    try:
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "UPDATE meme_tokens SET name = 'First', mayhem_state = 'active' "
                        "WHERE mint = :mint",
                        {"mint": "FREEZE_MINT"},
                    )
                ],
            )
        )
        with pytest.raises(DBAPIError, match="written once"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            "UPDATE meme_tokens SET name = 'Second' WHERE mint = :mint",
                            {"mint": "FREEZE_MINT"},
                        )
                    ],
                )
            )
        with pytest.raises(DBAPIError, match="declaring retention"):
            asyncio.run(
                _write(
                    upgraded,
                    [("DELETE FROM meme_tokens WHERE mint = :mint", {"mint": "FREEZE_MINT"})],
                )
            )
        states = asyncio.run(
            _scalars(
                upgraded,
                "SELECT name || '/' || mayhem_state FROM meme_tokens WHERE mint = :mint",
                {"mint": "FREEZE_MINT"},
            )
        )
        assert states == ["First/active"], "the lifecycle stopped moving with the freeze"
    finally:
        asyncio.run(
            _write(
                upgraded,
                [
                    _RETENTION_MARKER,
                    ("DELETE FROM meme_tokens WHERE mint = :mint", {"mint": "FREEZE_MINT"}),
                ],
            )
        )


# ---------------------------------------------------------------------------
# 0022_meme_lab — the continuous paper Lab: rule sets, proposals, bets, commands
# ---------------------------------------------------------------------------

MEME_LAB_TABLES = ("meme_rule_sets", "meme_proposals", "meme_paper_bets", "meme_operator_commands")
MEME_LAB_VIEWS = ("meme_lab_scoreboard_v1", "meme_desk_v1")
_RESEARCH_RULE_SET = "01994d00-6c1a-7000-8000-000000000001"

_A_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at) VALUES (:id, 'GUARD_MINT', :rule_set, 'operator', "
    "  'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now())"
)
_A_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params) VALUES (:id, :proposal, :rule_set, 'GUARD_MINT', :mode, now(), "
    "  '{}'::jsonb, 0.05, '{}'::jsonb)"
)


def test_0022_seeds_the_two_rule_sets_the_contract_names(upgraded: str) -> None:
    """The seed is part of the revision: a Lab with no rule set would be a loop
    that runs and proposes nothing while looking alive."""
    # By id: ``0026`` seeds two more active sets on top (``trendline_v0``,
    # ``hype_probe_v0``) and ``0029`` three more while retiring ``operator/1``
    # (``operator/2`` takes over); this test is about the two ``0022`` planted.
    seeds = {"a": _RESEARCH_RULE_SET, "b": "01994d00-6c1a-7000-8000-000000000002"}
    rows = asyncio.run(
        _scalars(
            upgraded,
            "SELECT name || '/' || version || ':' || kind || ':' || coalesce(exp_ref, '-') "
            "|| ':' || status FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY name",
            dict(seeds),
        )
    )
    assert rows == [
        "meme_paper_v0/1:research_only:EXP-M1:active",
        "operator/1:operator:-:retired",
    ]
    sizes = asyncio.run(
        _scalars(
            upgraded,
            "SELECT (params ->> 'max_sol_per_bet') || '/' || (params ->> 'wallet_max_sol') || '/' "
            "|| (params ->> 'daily_loss_cap_sol') FROM meme_rule_sets WHERE id IN (:a, :b) "
            "ORDER BY name",
            dict(seeds),
        )
    )
    assert sizes == ["0.05/2.0/0.20", "0.05/2.0/0.20"]


def test_0022_grants_the_desk_two_writes_and_the_loop_its_upserts(upgraded: str) -> None:
    """The contract's grants, as privileges: the API decides and orders, the loop
    proposes, fills and marks, and nobody deletes."""
    app, worker = "hunter_app", "hunter_worker"
    assert asyncio.run(_table_privileges(upgraded, app, "meme_rule_sets")) == {"SELECT"}
    assert asyncio.run(_table_privileges(upgraded, app, "meme_paper_bets")) == {"SELECT"}
    assert asyncio.run(_table_privileges(upgraded, app, "meme_operator_commands")) == {
        "SELECT",
        "INSERT",
    }
    assert asyncio.run(_table_privileges(upgraded, app, "meme_proposals")) == {"SELECT", "INSERT"}
    for column in ("status", "decision", "decided_by", "decided_at"):
        assert asyncio.run(_column_privilege(upgraded, app, "meme_proposals", column)), column
    for column in ("quote", "reasons", "bet_id", "refusal", "mint"):
        assert not asyncio.run(_column_privilege(upgraded, app, "meme_proposals", column)), column
    assert asyncio.run(_table_privileges(upgraded, worker, "meme_rule_sets")) == {"SELECT"}
    for table in ("meme_proposals", "meme_paper_bets"):
        assert asyncio.run(_table_privileges(upgraded, worker, table)) == {
            "SELECT",
            "INSERT",
            "UPDATE",
        }, table
    assert asyncio.run(_table_privileges(upgraded, worker, "meme_operator_commands")) == {"SELECT"}
    for column in ("applied_at", "result"):
        assert asyncio.run(_column_privilege(upgraded, worker, "meme_operator_commands", column))
    assert not asyncio.run(_column_privilege(upgraded, worker, "meme_operator_commands", "command"))
    for view in MEME_LAB_VIEWS:
        assert asyncio.run(_table_privileges(upgraded, app, view)) == {"SELECT"}
        assert asyncio.run(_table_privileges(upgraded, worker, view)) == {"SELECT"}


def test_0022_locks_every_bet_to_paper_for_every_role(upgraded: str) -> None:
    """``mode`` is a CHECK, not a convention: even the owner cannot write ``live``."""
    proposal = uuid7()
    asyncio.run(_write(upgraded, [(_A_PROPOSAL, {"id": proposal, "rule_set": _RESEARCH_RULE_SET})]))
    try:
        with pytest.raises(DBAPIError, match="every_bet_is_paper"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            _A_BET,
                            {
                                "id": uuid7(),
                                "proposal": proposal,
                                "rule_set": _RESEARCH_RULE_SET,
                                "mode": "live",
                            },
                        )
                    ],
                )
            )
    finally:
        asyncio.run(
            _write(upgraded, [("DELETE FROM meme_proposals WHERE id = :id", {"id": proposal})])
        )


def test_0022_refuses_a_downgrade_that_would_lose_a_bet(upgraded: str) -> None:
    """§17.7: the ledger is evidence — count, name, stop; the schema stays."""
    config = alembic_config(upgraded)
    proposal, bet = uuid7(), uuid7()
    asyncio.run(
        _write(
            upgraded,
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": _RESEARCH_RULE_SET}),
                (
                    _A_BET,
                    {
                        "id": bet,
                        "proposal": proposal,
                        "rule_set": _RESEARCH_RULE_SET,
                        "mode": "paper",
                    },
                ),
            ],
        )
    )
    try:
        # Stage at 0022 first: ``0023`` sits on top and ``"-1"`` from the head
        # would reverse *it*, not the Lab.
        command.downgrade(config, MEME_LAB_REVISION)
        with pytest.raises(DBAPIError, match="meme_paper_bets rows exist"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == MEME_LAB_REVISION, (
            "the downgrade must not commit"
        )
        assert asyncio.run(_relation_exists(upgraded, "meme_paper_bets"))
    finally:
        command.upgrade(config, "head")
        asyncio.run(
            _write(
                upgraded,
                [
                    ("DELETE FROM meme_paper_bets WHERE id = :id", {"id": bet}),
                    ("DELETE FROM meme_proposals WHERE id = :id", {"id": proposal}),
                ],
            )
        )
    command.check(config)


def test_0022_reverses_with_the_seed_alone_and_comes_back_seeded(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back: the seed is not
    evidence, so it reverses; and what comes back is seeded and granted again."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_LAB_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_RADAR_REVISION
        for relation in (*MEME_LAB_TABLES, *MEME_LAB_VIEWS):
            assert not asyncio.run(_relation_exists(upgraded, relation)), relation
        for table in MEME_TABLES:
            assert asyncio.run(_relation_exists(upgraded, table)), f"0021 lost {table}"
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    for relation in (*MEME_LAB_TABLES, *MEME_LAB_VIEWS):
        assert asyncio.run(_relation_exists(upgraded, relation)), relation
    # ``0022``'s two plus ``0026``'s two plus ``0029``'s three plus ``0030``'s two,
    # minus ``operator/1`` (retired by ``0029``), all re-seeded on the way back up.
    # ``0030`` retires nothing: ``meme_paper_v0/1`` and ``hype_probe_v0/1`` leave by
    # the audited ``infra/scripts/meme_rule_set.py --deprecate``, not by a deploy.
    assert asyncio.run(
        _scalars(upgraded, "SELECT count(*)::text FROM meme_rule_sets WHERE status = 'active'", {})
    ) == ["8"]
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_paper_bets")) == {
        "SELECT",
        "INSERT",
        "UPDATE",
    }
    command.check(config)


# ---------------------------------------------------------------------------
# 0023_meme_boards_trades — the site's boards, the risk reads, the tape columns
# ---------------------------------------------------------------------------

MEME_BOARDS_TABLES = ("meme_board_observations", "meme_risk_snapshots")

_A_BOARD_MINUTE = (
    "INSERT INTO meme_board_observations (observed_at, board, mint, minute_end, version, "
    "  position, first_seen_in_board_at, last_seen_in_board_at, source) VALUES "
    "('2026-10-05T12:00:30Z', 'new', :mint, '2026-10-05T12:01:00Z', 1, 0, "
    "  '2026-10-05T12:00:00Z', '2026-10-05T12:00:30Z', 'trenches_ws')"
)
_A_SWAP_TRADE = (
    "INSERT INTO meme_trades (block_time, signature, event_index, mint, slot, trader, side, "
    "  sol_lamports, token_amount, price, quote_mint, token_decimals, commitment, source) VALUES "
    "('2026-10-05T12:00:00Z', :signature, 0, 'TAPE_MINT', 446373814, 'TRADER', 'buy', 724716993, "
    "  16800146.527261, 0.0000000431, '11111111111111111111111111111111', 6, :commitment, "
    "  'swap_api')"
)


def test_0023_adds_the_tape_columns_and_relaxes_the_trade_commitment(upgraded: str) -> None:
    """The fifteen columns exist; a trade may say nothing about finality and may
    not say something other than ``confirmed``/``finalized``."""
    frozen = cast("tuple[str, ...]", migration_ddl("meme_boards_guards").FEATURE_COLUMNS_0023)
    names = ", ".join(f"'{column}'" for column in frozen)
    present = asyncio.run(
        _scalars(
            upgraded,
            "SELECT column_name FROM information_schema.columns "  # noqa: S608
            f"WHERE table_name = 'meme_features_1m' AND column_name IN ({names})",
            {},
        )
    )
    assert set(present) == set(frozen)
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'meme_trades' AND column_name = 'commitment'",
            {},
        )
    ) == ["YES"]
    asyncio.run(_write(upgraded, [(_A_SWAP_TRADE, {"signature": "SIG_NULL", "commitment": None})]))
    try:
        with pytest.raises(DBAPIError, match="commitment_is_a_known_label"):
            asyncio.run(
                _write(
                    upgraded,
                    [(_A_SWAP_TRADE, {"signature": "SIG_BAD", "commitment": "pending"})],
                )
            )
        # The 0021 reasons are all given; ``holders`` is NULL and ``holders_reason``
        # is not — an absence without a reason, the shape the biconditional refuses.
        with pytest.raises(DBAPIError, match="holders_is_null_with_a_reason"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            "INSERT INTO meme_features_1m (end_time, mint, features_version, "
                            "coverage, curve_reason, progress_reason, unique_buyers_reason, "
                            "buy_sell_ratio_reason, top10_share_reason, creator_sold_reason, "
                            "dev_share_reason, snipers_reason, tape_reason, "
                            "creator_net_seller_reason) VALUES ('2026-10-05T12:00:00Z', "
                            "'NO_REASON', 'meme_features_v1', 1, 'not_polled', 'not_polled', "
                            "'no_trade_feed', 'no_trade_feed', 'no_holders_reader', "
                            "'no_trade_feed', 'no_holders_reader', 'no_holders_reader', "
                            "'no_trade_feed', 'no_trade_feed')",
                            {},
                        )
                    ],
                )
            )
    finally:
        asyncio.run(
            _write(
                upgraded,
                [
                    ("DELETE FROM meme_trades WHERE mint = 'TAPE_MINT'", {}),
                    ("DELETE FROM meme_features_1m WHERE mint = 'NO_REASON'", {}),
                ],
            )
        )


def test_0023_grants_read_to_the_api_and_append_to_the_worker(upgraded: str) -> None:
    for table in MEME_BOARDS_TABLES:
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
        }, f"{table} is not append-only for the engine"
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", table)) == {"SELECT"}


def test_0023_hardens_every_partition_it_created(upgraded: str) -> None:
    boards = migration_ddl("meme_boards")
    parents = cast("tuple[str, ...]", boards.MEME_PARTITIONED_TABLES_0023)
    months = cast("tuple[tuple[int, int], ...]", boards.MEME_INITIAL_MONTHS_0023)
    children = [f"{parent}_{year:04d}_{month:02d}" for parent in parents for year, month in months]
    assert len(children) == 8
    present = set(
        asyncio.run(
            _scalars(
                upgraded,
                "SELECT relname FROM pg_class WHERE relispartition AND relkind = 'r' "
                "AND relname LIKE 'meme%'",
                {},
            )
        )
    )
    assert set(children) <= present
    for child in children:
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", child)) == set(), child
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", child)) == set(), child


def test_0023_refuses_a_downgrade_that_would_lose_a_board_minute(upgraded: str) -> None:
    """§17.7: a minute of exposure nobody can re-observe — count, name, stop."""
    config = alembic_config(upgraded)
    asyncio.run(_write(upgraded, [(_A_BOARD_MINUTE, {"mint": "GUARD_MINT"})]))
    try:
        # Stage at 0023 first: ``0024`` sits on top and ``"-1"`` from the head
        # would reverse *it* (six columns, no rows carrying them), not the boards.
        command.downgrade(config, MEME_BOARDS_REVISION)
        with pytest.raises(DBAPIError, match="meme_board_observations rows exist"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == MEME_BOARDS_REVISION, (
            "the downgrade must not commit"
        )
        assert asyncio.run(_relation_exists(upgraded, "meme_board_observations"))
    finally:
        command.upgrade(config, "head")
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        "DELETE FROM meme_board_observations WHERE mint = :mint",
                        {"mint": "GUARD_MINT"},
                    )
                ],
            )
        )
    command.check(config)


def test_0023_reverses_on_a_database_with_no_boards_and_comes_back(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back, and what comes back
    is checked: the two tables, their grants, the fifteen columns and the
    relaxed commitment."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_BOARDS_REVISION)
    command.downgrade(config, "-1")
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_LAB_REVISION
        for table in MEME_BOARDS_TABLES:
            assert not asyncio.run(_relation_exists(upgraded, table)), table
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM information_schema.columns "
                "WHERE table_name = 'meme_features_1m' AND column_name = 'curve_volume_1m_sol'",
                {},
            )
        ) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'meme_trades' AND column_name = 'commitment'",
                {},
            )
        ) == ["NO"]
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    for table in MEME_BOARDS_TABLES:
        assert asyncio.run(_relation_exists(upgraded, table)), table
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
        }
    command.check(config)


# ---------------------------------------------------------------------------
# 0024_meme_graduation — four completion signals, the denominator's source, the matrix
# ---------------------------------------------------------------------------

_A_COMPLETE_SNAPSHOT = (
    "INSERT INTO meme_curve_snapshots (observed_at, mint, source, virtual_sol_reserves, "
    "  virtual_token_reserves, real_sol_reserves, real_token_reserves, total_supply, complete) "
    "VALUES (:at, :mint, 'pumpfun_rest', 115.005359057, 279900000, :real_sol, 0, 1000000000, true)"
)
_A_GRADUATED_BOARD_MINUTE = (
    "INSERT INTO meme_board_observations (observed_at, board, mint, minute_end, version, "
    "  position, first_seen_in_board_at, last_seen_in_board_at, source, graduated_at) VALUES "
    "('2026-10-05T12:00:30Z', 'graduated', :mint, '2026-10-05T12:01:00Z', 1, 0, "
    "  '2026-10-05T12:00:10Z', '2026-10-05T12:00:30Z', 'trenches_ws', :gd)"
)
_SIGNALS = (
    "SELECT COALESCE(completed_at::text, '-') || '|' "
    "|| COALESCE(rest_complete_seen_at::text, '-') || '|' "
    "|| COALESCE(curve_filled_seen_at::text, '-') || '|' "
    "|| COALESCE(graduated_board_seen_at::text, '-') || '|' "
    "|| COALESCE(pool_created_at::text, '-') || '|' || COALESCE(pool_created_source, '-') "
    "|| '|' || COALESCE(progress_denominator_source, '-') "
    "FROM meme_tokens WHERE mint = :mint"
)
_CLEAN_TOKENS: tuple[tuple[str, dict[str, object]], ...] = (
    _RETENTION_MARKER,
    ("DELETE FROM meme_tokens WHERE mint LIKE 'G24_%'", {}),
    ("DELETE FROM meme_curve_snapshots WHERE mint LIKE 'G24_%'", {}),
    ("DELETE FROM meme_board_observations WHERE mint LIKE 'G24_%'", {}),
)


def test_0024_adds_the_six_columns_their_checks_and_the_matrix_view(upgraded: str) -> None:
    frozen = cast("tuple[str, ...]", migration_ddl("meme_graduation").GRADUATION_COLUMNS_0024)
    names = ", ".join(f"'{column}'" for column in frozen)
    for relation in ("meme_tokens", "meme_radar_features_v1"):
        present = asyncio.run(
            _scalars(
                upgraded,
                "SELECT column_name FROM information_schema.columns "  # noqa: S608
                f"WHERE table_name = '{relation}' AND column_name IN ({names})",
                {},
            )
        )
        assert set(present) == set(frozen), relation
    assert asyncio.run(_relation_exists(upgraded, "meme_graduation_matrix_v1"))
    for role in ("hunter_app", "hunter_worker"):
        assert asyncio.run(_table_privileges(upgraded, role, "meme_graduation_matrix_v1")) == {
            "SELECT"
        }, role
    asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "G24_CHECK"})]))
    try:
        for statement, constraint in (
            ("UPDATE meme_tokens SET pool_created_at = now()", "a_pool_names_its_source"),
            (
                "UPDATE meme_tokens SET pool_created_at = now(), pool_created_source = 'blog'",
                "pool_source_is_a_known_label",
            ),
            (
                "UPDATE meme_tokens SET initial_real_token_reserves = 793100000",
                "a_denominator_names_its_source",
            ),
            (
                "UPDATE meme_tokens SET initial_real_token_reserves = 793100000, "
                "progress_denominator_source = 'blog'",
                "denominator_source_is_a_known_label",
            ),
        ):
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(
                    _write(upgraded, [(f"{statement} WHERE mint = :mint", {"mint": "G24_CHECK"})])
                )
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS)))


def test_0024_writes_each_signal_once_and_lets_completed_at_move_only_earlier(
    upgraded: str,
) -> None:
    """The stamps are first sightings (``NULL -> value`` once); ``completed_at``
    is their reduction and may only ever move earlier — the indexer's ``gd`` is
    retrospective — never later and never back to NULL."""
    asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "G24_ONCE"})]))
    update = "UPDATE meme_tokens SET {} WHERE mint = :mint"
    try:
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        update.format(
                            "rest_complete_seen_at = '2026-10-05T12:01:00Z', "
                            "completed_at = '2026-10-05T12:01:00Z'"
                        ),
                        {"mint": "G24_ONCE"},
                    )
                ],
            )
        )
        with pytest.raises(DBAPIError, match="rest_complete_seen_at is written once"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            update.format("rest_complete_seen_at = '2026-10-05T12:02:00Z'"),
                            {"mint": "G24_ONCE"},
                        )
                    ],
                )
            )
        asyncio.run(
            _write(
                upgraded,
                [(update.format("completed_at = '2026-10-05T12:00:00Z'"), {"mint": "G24_ONCE"})],
            )
        )
        for later in ("'2026-10-05T12:03:00Z'", "NULL"):
            with pytest.raises(DBAPIError, match="may only move earlier"):
                asyncio.run(
                    _write(
                        upgraded,
                        [(update.format(f"completed_at = {later}"), {"mint": "G24_ONCE"})],
                    )
                )
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT completed_at::text FROM meme_tokens WHERE mint = :mint",
                {"mint": "G24_ONCE"},
            )
        ) == ["2026-10-05 12:00:00+00"]
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS)))


def test_0024_backfills_the_signals_from_the_evidence_tables(upgraded: str) -> None:
    """A database of ``0023`` with the three shapes the plantão measured, upgraded:
    the REST-only zero-reserve coin (the 77) keeps its photo as a signal and loses
    its ``completed_at``; the migrated coin on the graduated board gets the pool
    (from the frame this radar heard) and the board signal, and its
    ``completed_at`` is the earliest; the coin whose complete photo carried SOL
    is completed at that photo; every denominator held is ``observed_virgin``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_BOARDS_REVISION)
    at = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # asyncpg binds instants, not ISO text
    gd = datetime(2026, 10, 5, 11, 59, 50, tzinfo=UTC)
    asyncio.run(
        _write(
            upgraded,
            [
                (
                    "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, "
                    "last_seen_at, completed_at, initial_real_token_reserves) "
                    "VALUES ('G24_ZERO', 'pumpfun_rest', :at, :at, :at, 793100000)",
                    {"at": at},
                ),
                (_A_COMPLETE_SNAPSHOT, {"at": at, "mint": "G24_ZERO", "real_sol": 0}),
                (
                    "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, "
                    "last_seen_at, migrated_at, migrated_pool) "
                    "VALUES ('G24_POOL', 'pumpportal_ws', :at, :at, '2026-10-05T12:00:20Z', "
                    "'pump-amm')",
                    {"at": at},
                ),
                (_A_GRADUATED_BOARD_MINUTE, {"mint": "G24_POOL", "gd": gd}),
                (_A_TOKEN, {"mint": "G24_SOL"}),
                (_A_COMPLETE_SNAPSHOT, {"at": at, "mint": "G24_SOL", "real_sol": 85.005359057}),
            ],
        )
    )
    try:
        command.upgrade(config, "head")
        rows = {
            mint: asyncio.run(_scalars(upgraded, _SIGNALS, {"mint": mint}))[0]
            for mint in ("G24_ZERO", "G24_POOL", "G24_SOL")
        }
        assert rows["G24_ZERO"] == "-|2026-10-05 12:00:00+00|-|-|-|-|observed_virgin", (
            "a REST complete with a zero reserve keeps its photo and loses its verdict"
        )
        assert rows["G24_POOL"] == (
            "2026-10-05 12:00:10+00|-|-|2026-10-05 12:00:10+00|2026-10-05 12:00:20+00|"
            "pumpportal_ws|-"
        ), "the frame this radar heard is the pool; the board's first sighting is earlier"
        assert rows["G24_SOL"] == "2026-10-05 12:00:00+00|2026-10-05 12:00:00+00|-|-|-|-|-"
        matrix = asyncio.run(
            _scalars(
                upgraded,
                "SELECT mints::text || '/' || completed || '/' || rest_complete || '/' "
                "|| graduated_board || '/' || pool_created || '/' || signals_1 || '/' "
                "|| signals_2 || '/' || disagree_rest_board || '/' || rest_only_unclassified "
                "FROM meme_graduation_matrix_v1 WHERE day_brt = '2026-10-05'",
                {},
            )
        )
        assert matrix == ["3/2/2/1/1/2/1/3/1"]
    finally:
        command.upgrade(config, "head")
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS)))
    command.check(config)


def test_0024_refuses_a_downgrade_that_would_lose_a_completion_signal(upgraded: str) -> None:
    """§17.7: the first sighting of a graduation is not re-observable — count, name, stop."""
    config = alembic_config(upgraded)
    asyncio.run(
        _write(
            upgraded,
            [
                (_A_TOKEN, {"mint": "G24_GUARD"}),
                (
                    "UPDATE meme_tokens SET graduated_board_seen_at = now() WHERE mint = :mint",
                    {"mint": "G24_GUARD"},
                ),
            ],
        )
    )
    try:
        # Stage at 0024 first: ``0025`` sits on top and its own guard counts
        # only ``mayhem_state`` rows, so this step passes; ``"-1"`` is then 0024.
        command.downgrade(config, MEME_GRADUATION_REVISION)
        with pytest.raises(DBAPIError, match="carry a completion signal"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == MEME_GRADUATION_REVISION, (
            "the downgrade must not commit"
        )
        assert asyncio.run(_relation_exists(upgraded, "meme_graduation_matrix_v1"))
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS)))
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0024_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The round trip an operator runs to roll a deploy back: the columns and the
    matrix go, ``0021``'s view and its trigger come back exactly (``completed_at``
    written once again), and the upgrade restores the six, the view, the grants."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_BOARDS_REVISION)  # through 0025, then 0024
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_BOARDS_REVISION
        assert not asyncio.run(_relation_exists(upgraded, "meme_graduation_matrix_v1"))
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM information_schema.columns "
                "WHERE table_name IN ('meme_tokens', 'meme_radar_features_v1') "
                "AND column_name = 'pool_created_at'",
                {},
            )
        ) == ["0"]
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", "meme_radar_features_v1")) == {
            "SELECT"
        }
        asyncio.run(
            _write(
                upgraded,
                [
                    (_A_TOKEN, {"mint": "G24_BACK"}),
                    (
                        "UPDATE meme_tokens SET completed_at = now() WHERE mint = :mint",
                        {"mint": "G24_BACK"},
                    ),
                ],
            )
        )
        with pytest.raises(DBAPIError, match="completed_at is written once"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        (
                            "UPDATE meme_tokens SET completed_at = now() - interval '1 hour' "
                            "WHERE mint = :mint",
                            {"mint": "G24_BACK"},
                        )
                    ],
                )
            )
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS[:2])))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_relation_exists(upgraded, "meme_graduation_matrix_v1"))
    for role in ("hunter_app", "hunter_worker"):
        assert asyncio.run(_table_privileges(upgraded, role, "meme_graduation_matrix_v1")) == {
            "SELECT"
        }
    command.check(config)


# ---------------------------------------------------------------------------
# 0025_meme_mayhem_denominator — the third provenance of the denominator (T4.2e)
# ---------------------------------------------------------------------------

_A_MAYHEM_DENOMINATOR = (
    "UPDATE meme_tokens SET initial_real_token_reserves = 793100000, "
    "progress_denominator_source = 'mayhem_state' WHERE mint = :mint"
)
_CLEAN_TOKENS_0025: tuple[tuple[str, dict[str, object]], ...] = (
    _RETENTION_MARKER,
    ("DELETE FROM meme_tokens WHERE mint LIKE 'G25_%'", {}),
)


def test_0025_widens_the_denominator_label_and_keeps_the_pair_rule(upgraded: str) -> None:
    """``mayhem_state`` is a known label now; a made-up one still is not, and a
    denominator without a source (or a source without a denominator) is still
    refused by ``0024``'s pair CHECK, which this revision does not touch."""
    frozen = cast("tuple[str, ...]", migration_ddl("meme_mayhem").DENOMINATOR_SOURCES_0025)
    assert frozen == ("observed_virgin", "global_params", "mayhem_state")
    asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "G25_LABEL"})]))
    try:
        asyncio.run(_write(upgraded, [(_A_MAYHEM_DENOMINATOR, {"mint": "G25_LABEL"})]))
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT progress_denominator_source FROM meme_tokens WHERE mint = :mint",
                {"mint": "G25_LABEL"},
            )
        ) == ["mayhem_state"]
        asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "G25_PAIR"})]))
        for statement, constraint in (
            (
                "UPDATE meme_tokens SET initial_real_token_reserves = 793100000, "
                "progress_denominator_source = 'blog'",
                "denominator_source_is_a_known_label",
            ),
            (
                "UPDATE meme_tokens SET progress_denominator_source = 'mayhem_state'",
                "a_denominator_names_its_source",
            ),
        ):
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(
                    _write(upgraded, [(f"{statement} WHERE mint = :mint", {"mint": "G25_PAIR"})])
                )
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS_0025)))


def test_0025_refuses_a_downgrade_that_would_lose_a_mayhem_denominator(upgraded: str) -> None:
    """§17.7: an on-chain reconciliation the ``0024`` schema cannot hold — count, name, stop."""
    config = alembic_config(upgraded)
    asyncio.run(
        _write(
            upgraded,
            [(_A_TOKEN, {"mint": "G25_GUARD"}), (_A_MAYHEM_DENOMINATOR, {"mint": "G25_GUARD"})],
        )
    )
    try:
        # Stage at 0025 first: ``0026`` sits on top and its own guard counts
        # only legs, lines and its seeds' references, so this step passes;
        # ``"-1"`` is then 0025.
        command.downgrade(config, MEME_MAYHEM_REVISION)
        with pytest.raises(DBAPIError, match="mayhem_state"):
            command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == MEME_MAYHEM_REVISION, (
            "the downgrade must not commit"
        )
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS_0025)))
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0025_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: at ``0024`` the label is refused again; the
    upgrade accepts it once more."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_GRADUATION_REVISION)  # through 0026, then 0025
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_GRADUATION_REVISION
        asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "G25_BACK"})]))
        with pytest.raises(DBAPIError, match="denominator_source_is_a_known_label"):
            asyncio.run(_write(upgraded, [(_A_MAYHEM_DENOMINATOR, {"mint": "G25_BACK"})]))
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS_0025)))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    asyncio.run(_write(upgraded, [(_A_TOKEN, {"mint": "G25_BACK"})]))
    try:
        asyncio.run(_write(upgraded, [(_A_MAYHEM_DENOMINATOR, {"mint": "G25_BACK"})]))
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_TOKENS_0025)))
    command.check(config)


# ---------------------------------------------------------------------------
# 0026_meme_lines — the drawn lines and the hype as columns, probe and scale legs (T4.10)
# ---------------------------------------------------------------------------

_TRENDLINE_RULE_SET = "01994d00-6c1a-7000-8000-000000000003"
_HYPE_PROBE_RULE_SET = "01994d00-6c1a-7000-8000-000000000004"
_REASON_COLUMNS = (
    "progress_reason, curve_reason, unique_buyers_reason, buy_sell_ratio_reason, "
    "top10_share_reason, creator_sold_reason, holders_reason, dev_share_reason, "
    "snipers_reason, tape_reason, creator_net_seller_reason"
)
_REASON_VALUES = (
    "'not_polled', 'not_polled', 'no_trade_feed', 'no_trade_feed', 'no_holders_reader', "
    "'no_trade_feed', 'no_holders_reader', 'no_holders_reader', 'no_holders_reader', "
    "'no_trade_feed', 'no_trade_feed'"
)
_A_V3_ROW = (
    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage, "  # noqa: S608
    f"  {_REASON_COLUMNS}, line_points, line_reason, support_line_sol, support_line_slope, "
    "  higher_lows, distance_to_support_pct, high_15m_sol, low_15m_sol, hype_score, hype_reason) "
    f"VALUES ('2026-10-05T12:00:00Z', :mint, 'meme_features_v3', 1, {_REASON_VALUES}, "
    "  :points, :line_reason, :support, :slope, :higher, :distance, :high, :low, :hype, "
    "  :hype_reason)"
)
_A_V2_ROW = (
    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage, "  # noqa: S608
    f"  {_REASON_COLUMNS}) VALUES ('2026-10-05T12:00:00Z', :mint, 'meme_features_v2', 1, "
    f"  {_REASON_VALUES})"
)
_A_LEGGED_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params, leg, parent_bet_id) VALUES (:id, :proposal, :rule_set, "
    "  'GUARD_MINT', 'paper', now(), '{}'::jsonb, 0.01, '{}'::jsonb, :leg, "
    "  CAST(:parent AS uuid))"
)
_CLEAN_0026: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_features_1m WHERE mint LIKE 'L26_%'", {}),
)
_NO_SUPPORT: dict[str, object] = {
    "support": None,
    "slope": None,
    "higher": None,
    "distance": None,
}


def _a_v3_row(mint: str, **overrides: object) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "mint": mint,
        "points": 15,
        "line_reason": None,
        "support": Decimal("48"),
        "slope": Decimal("1"),
        "higher": True,
        "distance": Decimal("0.166667"),
        "high": Decimal("56"),
        "low": Decimal("36"),
        "hype": Decimal("0.7"),
        "hype_reason": None,
    }
    params.update(overrides)
    return _A_V3_ROW, params


def _a_legged_bet(
    ordinal: int, rule_set: str, leg: str, parent: str | None
) -> list[tuple[str, dict[str, object]]]:
    proposal = f"00000000-0000-4000-8000-0000000002{ordinal:02d}"
    bet = f"00000000-0000-4000-8000-0000000003{ordinal:02d}"
    return [
        (_A_PROPOSAL, {"id": proposal, "rule_set": rule_set}),
        (
            _A_LEGGED_BET,
            {"id": bet, "proposal": proposal, "rule_set": rule_set, "leg": leg, "parent": parent},
        ),
    ]


def test_0026_adds_the_columns_their_checks_and_seeds_the_two_arms(upgraded: str) -> None:
    """Thirteen columns on the minute, two on the bet, eight plus two CHECKs, and
    the two pre-registered rule sets with the brief's frozen parameters. A row
    folded before the lines (no ``line_points``) is still a legal row."""
    lines = migration_ddl("meme_lines")
    features = cast("tuple[str, ...]", lines.FEATURE_COLUMNS_0026)
    bets = cast("tuple[str, ...]", lines.BET_COLUMNS_0026)
    for table, frozen in (("meme_features_1m", features), ("meme_paper_bets", bets)):
        names = ", ".join(f"'{column}'" for column in frozen)
        present = asyncio.run(
            _scalars(
                upgraded,
                "SELECT column_name FROM information_schema.columns "  # noqa: S608
                f"WHERE table_name = '{table}' AND column_name IN ({names})",
                {},
            )
        )
        assert set(present) == set(frozen), table
    seeds = asyncio.run(
        _scalars(
            upgraded,
            "SELECT name || '/' || version || ':' || kind || ':' || exp_ref || ':' || status "
            "|| ':' || (params ->> 'size_sol') || ':' || coalesce(params ->> 'scale_size_sol', '-') "
            "|| ':' || coalesce(params ->> 'scale_gate', '-') || ':' "
            "|| coalesce(params ->> 'min_hype_score', '-') || ':' "
            "|| coalesce(params ->> 'exit_on_line_break', '-') || ':' "
            "|| (params ->> 'max_open_positions') "
            "FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY name",
            {"a": _TRENDLINE_RULE_SET, "b": _HYPE_PROBE_RULE_SET},
        )
    )
    assert seeds == [
        "hype_probe_v0/1:research_only:EXP-M3:active:0.01:0.04:trendline_v0/1:0.6:-:5",
        "trendline_v0/1:research_only:EXP-M2:active:0.05:-:-:-:true:3",
    ]
    asyncio.run(_write(upgraded, [_a_v3_row("L26_OK")]))
    asyncio.run(_write(upgraded, [_a_v3_row("L26_FLAT", line_reason="flat", **_NO_SUPPORT)]))
    asyncio.run(_write(upgraded, [_a_v3_row("L26_PARTIAL", hype_reason="partial")]))
    asyncio.run(_write(upgraded, [(_A_V2_ROW, {"mint": "L26_OLD"})]))
    try:
        refused: list[tuple[dict[str, object], str]] = [
            (dict(_NO_SUPPORT), "support_line_is_null_with_a_reason"),
            ({"slope": None}, "support_group_is_absent_together"),
            ({"line_reason": "blog", **_NO_SUPPORT}, "line_reason_is_a_known_label"),
            ({"low": None}, "window_extremes_are_absent_together"),
            ({"hype": None}, "hype_is_null_without_both_sources"),
            ({"hype": None, "hype_reason": "partial"}, "hype_is_null_without_both_sources"),
            ({"hype_reason": "blog"}, "hype_reason_is_a_known_label"),
            ({"hype": Decimal("1.5")}, "hype_score_is_a_fraction"),
        ]
        for overrides, constraint in refused:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, [_a_v3_row("L26_BAD", **overrides)]))
        asyncio.run(_write(upgraded, _a_legged_bet(1, _HYPE_PROBE_RULE_SET, "probe", None)))
        probe = "00000000-0000-4000-8000-000000000301"
        for leg, parent, constraint in (
            ("scale", None, "a_scale_leg_names_its_probe"),
            ("probe", probe, "a_scale_leg_names_its_probe"),
            ("hedge", None, "leg_is_a_known_label"),
        ):
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, _a_legged_bet(2, _HYPE_PROBE_RULE_SET, leg, parent)))
        asyncio.run(_write(upgraded, _a_legged_bet(3, _HYPE_PROBE_RULE_SET, "scale", probe)))
        legs = asyncio.run(
            _scalars(
                upgraded,
                "SELECT leg || ':' || coalesce(parent_bet_id::text, '-') FROM meme_paper_bets "
                "WHERE mint = 'GUARD_MINT' ORDER BY leg",
                {},
            )
        )
        assert legs == ["probe:-", f"scale:{probe}"]
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0026)))


def test_0026_refuses_a_downgrade_that_would_lose_a_leg_or_a_line(upgraded: str) -> None:
    """§17.7: a probe and the lines a fold drew are evidence — count, name, stop.
    Staged at **0026** first (``"-1"`` stopped meaning 0026 the day ``0027``
    and ``0028`` landed on top), then put back at ``head``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_LINES_REVISION)
    try:
        asyncio.run(_write(upgraded, _a_legged_bet(4, _RESEARCH_RULE_SET, "probe", None)))
        try:
            with pytest.raises(DBAPIError, match="carry a leg"):
                command.downgrade(config, "-1")
            assert asyncio.run(_revision(upgraded)) == MEME_LINES_REVISION, (
                "the downgrade must not commit"
            )
        finally:
            asyncio.run(_write(upgraded, list(_CLEAN_0026)))
        asyncio.run(_write(upgraded, [_a_v3_row("L26_GUARD")]))
        try:
            with pytest.raises(DBAPIError, match="carry the lines"):
                command.downgrade(config, "-1")
            assert asyncio.run(_revision(upgraded)) == MEME_LINES_REVISION
        finally:
            asyncio.run(_write(upgraded, list(_CLEAN_0026)))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0026_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: the columns and the seed go, the ``0025`` schema
    is exactly what it was, and the upgrade restores both."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_MAYHEM_REVISION)  # through 0028, 0027, then 0026
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_MAYHEM_REVISION
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM information_schema.columns "
                "WHERE (table_name = 'meme_features_1m' "
                "       AND column_name IN ('support_line_sol', 'hype_score', 'line_points')) "
                "OR (table_name = 'meme_paper_bets' AND column_name IN ('leg', 'parent_bet_id'))",
                {},
            )
        ) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM meme_rule_sets WHERE id IN (:a, :b)",
                {"a": _TRENDLINE_RULE_SET, "b": _HYPE_PROBE_RULE_SET},
            )
        ) == ["0"]
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM meme_rule_sets WHERE id IN (:a, :b) AND status = 'active'",
            {"a": _TRENDLINE_RULE_SET, "b": _HYPE_PROBE_RULE_SET},
        )
    ) == ["2"]
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_paper_bets")) == {
        "SELECT",
        "INSERT",
        "UPDATE",
    }
    command.check(config)


# ---------------------------------------------------------------------------
# 0029_meme_moonshot — marks on the pool tape, the venue of a trade, the 10x/25x arms (T4.11)
# ---------------------------------------------------------------------------

_MOONSHOT_10X_RULE_SET = "01994d00-6c1a-7000-8000-000000000005"
_MOONSHOT_25X_RULE_SET = "01994d00-6c1a-7000-8000-000000000006"
_OPERATOR_2_RULE_SET = "01994d00-6c1a-7000-8000-000000000007"
_OPERATOR_1_RULE_SET = "01994d00-6c1a-7000-8000-000000000002"
_A_MARKED_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, entry_at, entry, "
    "  initial_risk_sol, params, mark_sol, mark_at, mark_source, mark_stale_s) VALUES (:id, "
    "  :proposal, :rule_set, 'GUARD_MINT', 'paper', now(), '{}'::jsonb, 0.02, '{}'::jsonb, "
    "  CAST(:mark_sol AS numeric), CAST(:mark_at AS timestamptz), :mark_source, "
    "  CAST(:stale AS integer))"
)
_A_VENUE_TRADE = (
    "INSERT INTO meme_trades (block_time, signature, event_index, mint, slot, trader, side, "
    "  sol_lamports, token_amount, price, quote_mint, token_decimals, source, program) VALUES "
    "('2026-10-05T12:00:00Z', :signature, 0, 'POOL_MINT', 446390104, 'TRADER', 'sell', 54396031, "
    "  113499.73695, 0.0000004793, '11111111111111111111111111111111', 6, 'swap_api', :program)"
)
_CLEAN_0029: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_trades WHERE mint = 'POOL_MINT'", {}),
)
_SEEDED_0029 = {"a": _MOONSHOT_10X_RULE_SET, "b": _MOONSHOT_25X_RULE_SET, "c": _OPERATOR_2_RULE_SET}


def _a_marked_bet(
    ordinal: int,
    rule_set: str,
    *,
    mark_sol: Decimal | None = Decimal("0.01"),
    mark_source: str | None = "curve",
    stale: int | None = None,
) -> list[tuple[str, dict[str, object]]]:
    proposal = f"00000000-0000-4000-8000-0000000004{ordinal:02d}"
    bet = f"00000000-0000-4000-8000-0000000005{ordinal:02d}"
    return [
        (_A_PROPOSAL, {"id": proposal, "rule_set": rule_set}),
        (
            _A_MARKED_BET,
            {
                "id": bet,
                "proposal": proposal,
                "rule_set": rule_set,
                "mark_sol": mark_sol,
                "mark_at": None if mark_sol is None else datetime(2026, 10, 5, 12, tzinfo=UTC),
                "mark_source": mark_source,
                "stale": stale,
            },
        ),
    ]


def test_0029_adds_the_mark_and_venue_columns_and_seeds_the_moonshot_arms(upgraded: str) -> None:
    """Two columns on the bet, one on the trade, their CHECKs, the two arms and
    ``operator/2`` with the brief's frozen parameters, ``operator/1`` retired."""
    ddl = migration_ddl("meme_moonshot")
    for table, frozen in (
        ("meme_paper_bets", cast("tuple[str, ...]", ddl.BET_COLUMNS_0029)),
        ("meme_trades", cast("tuple[str, ...]", ddl.TRADE_COLUMNS_0029)),
    ):
        names = ", ".join(f"'{column}'" for column in frozen)
        present = asyncio.run(
            _scalars(
                upgraded,
                "SELECT column_name FROM information_schema.columns "  # noqa: S608
                f"WHERE table_name = '{table}' AND column_name IN ({names})",
                {},
            )
        )
        assert set(present) == set(frozen), table
    seeds = asyncio.run(
        _scalars(
            upgraded,
            "SELECT name || '/' || version || ':' || kind || ':' || coalesce(exp_ref, '-') || ':' "
            "|| status || ':' || (params ->> 'target_x') || ':' || (params ->> 'size_sol') || ':' "
            "|| (params ->> 'trailing_pct') || ':' || (params ->> 'trailing_arm_x') || ':' "
            "|| (params ->> 'max_hold_s') || ':' || (params ->> 'exit_on_migration') || ':' "
            "|| (params ->> 'exit_on_dead') || ':' || (params ->> 'dead_stale_s') || ':' "
            "|| (params ->> 'dead_mark_pct') || ':' || (params ->> 'max_open_positions') || ':' "
            "|| (params ->> 'daily_loss_cap_sol') || ':' || (params ->> 'gate_key') "
            "FROM meme_rule_sets WHERE id IN (:a, :b, :c) ORDER BY name, version",
            dict(_SEEDED_0029),
        )
    )
    assert seeds == [
        "moonshot_v0/1:research_only:EXP-M4:active:10:0.02:50:3:7200:false:true:900:50:8:0.20"
        ":sonda_de_hype",
        "moonshot_v0/2:research_only:EXP-M4:active:25:0.02:50:3:7200:false:true:900:50:8:0.20"
        ":sonda_de_hype",
        # ``0033`` (T4.19) retires ``operator/2`` for ``operator/3``; the params are 0029's.
        "operator/2:operator:-:retired:10:0.05:50:3:7200:false:true:900:50:3:0.20"
        ":comprar_cedo_na_curva",
    ]
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT status || ':' || (retired_at IS NOT NULL)::text FROM meme_rule_sets "
            "WHERE id = :id",
            {"id": _OPERATOR_1_RULE_SET},
        )
    ) == ["retired:true"]
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT name || '/' || version FROM meme_rule_sets WHERE name = 'operator' "
            "AND status = 'active'",
            {},
        )
    ) == ["operator/3"], "exactly one active operator set for the desk's manual buys (0033's)"
    try:
        asyncio.run(
            _write(
                upgraded, _a_marked_bet(1, _RESEARCH_RULE_SET, mark_source="pool_tape", stale=930)
            )
        )
        asyncio.run(
            _write(upgraded, _a_marked_bet(2, _RESEARCH_RULE_SET, mark_sol=None, mark_source=None))
        )
        refused: list[tuple[dict[str, object], str]] = [
            ({"mark_source": "blog"}, "mark_source_is_a_known_label"),
            ({"mark_source": None}, "a_mark_names_its_source"),
            ({"mark_sol": None, "mark_source": "curve"}, "a_mark_names_its_source"),
            ({"stale": -1}, "mark_stale_s_is_not_negative"),
        ]
        for overrides, constraint in refused:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, _a_marked_bet(3, _RESEARCH_RULE_SET, **overrides)))  # type: ignore[arg-type]
        asyncio.run(
            _write(
                upgraded, [(_A_VENUE_TRADE, {"signature": "SIG_POOL_0029", "program": "pump_amm"})]
            )
        )
        with pytest.raises(DBAPIError, match="program_is_a_known_label"):
            asyncio.run(
                _write(
                    upgraded,
                    [(_A_VENUE_TRADE, {"signature": "SIG_RAY_0029", "program": "raydium_cpmm"})],
                )
            )
        venues = asyncio.run(
            _scalars(
                upgraded,
                "SELECT coalesce(program, '-') FROM meme_trades WHERE mint = 'POOL_MINT'",
                {},
            )
        )
        assert venues == ["pump_amm"]
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0029)))


def test_0029_refuses_a_downgrade_that_would_lose_the_pool_tape_or_a_moonshot(
    upgraded: str,
) -> None:
    """§17.7: a pool trade, a pool-marked bet and a bet under a seeded set are
    evidence — count, name, stop. Staged at **0029** first (``0030`` and
    ``0031`` sit on top), then put back at ``head``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_MOONSHOT_REVISION)
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_VENUE_TRADE, {"signature": "SIG_POOL_GUARD", "program": "pump_amm"})],
            "pool trades exist",
        ),
        (
            _a_marked_bet(4, _RESEARCH_RULE_SET, mark_source="pool_tape", stale=0),
            "marked or closed on the pool",
        ),
        (_a_marked_bet(5, _MOONSHOT_10X_RULE_SET), "reference the seeded moonshot"),
    ]
    try:
        for statements, message in guarded:
            asyncio.run(_write(upgraded, statements))
            try:
                with pytest.raises(DBAPIError, match=message):
                    command.downgrade(config, "-1")
                assert asyncio.run(_revision(upgraded)) == MEME_MOONSHOT_REVISION, (
                    "the downgrade must not commit"
                )
            finally:
                asyncio.run(_write(upgraded, list(_CLEAN_0029)))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0029_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: the columns and the seed go, ``operator/1``
    comes back active, the ``0028`` schema is what it was; the upgrade restores all."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_LIVE_REVISION)  # through 0031 and 0030, then 0029
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_LIVE_REVISION
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM information_schema.columns "
                "WHERE (table_name = 'meme_paper_bets' "
                "       AND column_name IN ('mark_source', 'mark_stale_s')) "
                "OR (table_name = 'meme_trades' AND column_name = 'program')",
                {},
            )
        ) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM meme_rule_sets WHERE id IN (:a, :b, :c)",
                dict(_SEEDED_0029),
            )
        ) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT status || ':' || (retired_at IS NOT NULL)::text FROM meme_rule_sets "
                "WHERE id = :id",
                {"id": _OPERATOR_1_RULE_SET},
            )
        ) == ["active:false"], "operator/1 is the desk's set again below 0029"
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM meme_rule_sets WHERE id IN (:a, :b, :c) "
            "AND status = 'active'",
            dict(_SEEDED_0029),
        )
    ) == ["2"], "the two arms; operator/2 is retired again by 0033 on the way back up"
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT status FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY id",
            {"a": _OPERATOR_1_RULE_SET, "b": _OPERATOR_2_RULE_SET},
        )
    ) == ["retired", "retired"]
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_trades")) == {
        "SELECT",
        "INSERT",
    }
    command.check(config)


# ---------------------------------------------------------------------------
# 0027_meme_wallets — the observed wallet's real fills and positions (T4.12)
# ---------------------------------------------------------------------------

_W27 = "W27_6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F"
_A_WALLET_TRADE = (
    "INSERT INTO meme_wallet_trades (wallet, signature, event_index, slot, block_time, mint, "
    "  side, venue, sol_lamports, token_amount, fee_lamports, decode, raw, lab_context) "
    "VALUES (:wallet, :signature, 0, 1, CAST(:block_time AS timestamptz), :mint, :side, :venue, "
    "  :sol, :tokens, :fee, :decode, CAST(:raw AS jsonb), CAST(:lab AS jsonb))"
)
_A_WALLET_POSITION = (
    "INSERT INTO meme_wallet_positions (wallet, mint, status, tokens_held, sol_spent, "
    "  sol_received, open_cost_sol, realized_pnl_sol, buys, sells, first_buy_at, last_trade_at, "
    "  mark_sol, mark_at, mark_source, mark_reason, unrealized_pnl_sol, r_multiple) "
    "VALUES (:wallet, :mint, :status, :held, :spent, :received, :open_cost, :realized, :buys, "
    "  :sells, CAST(:first_buy_at AS timestamptz), CAST(:last_trade_at AS timestamptz), "
    "  :mark_sol, CAST(:mark_at AS timestamptz), :mark_source, :mark_reason, :unrealized, :r)"
)
_CLEAN_0027: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_wallet_positions WHERE wallet LIKE 'W27_%'", {}),
    ("DELETE FROM meme_wallet_trades WHERE wallet LIKE 'W27_%'", {}),
)


def _a_wallet_trade(signature: str, **overrides: object) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "wallet": _W27,
        "signature": signature,
        "block_time": datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
        "mint": "W27_MINT",
        "side": "buy",
        "venue": "curve",
        "sol": 977_777_777,
        "tokens": Decimal("22628881.309131"),
        "fee": 12_310_723,
        "decode": "trade_event",
        "raw": "{}",
        "lab": None,
    }
    params.update(overrides)
    return _A_WALLET_TRADE, params


def _a_wallet_position(**overrides: object) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "wallet": _W27,
        "mint": "W27_MINT",
        "status": "open",
        "held": Decimal(5),
        "spent": Decimal(3),
        "received": Decimal("4.5"),
        "open_cost": Decimal(1),
        "realized": Decimal("2.5"),
        "buys": 2,
        "sells": 1,
        "first_buy_at": datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
        "last_trade_at": datetime(2026, 10, 5, 12, 2, tzinfo=UTC),
        "mark_sol": Decimal("1.5"),
        "mark_at": datetime(2026, 10, 5, 12, 3, tzinfo=UTC),
        "mark_source": "tape",
        "mark_reason": None,
        "unrealized": Decimal("0.5"),
        "r": Decimal(1),
    }
    params.update(overrides)
    return _A_WALLET_POSITION, params


def test_0027_creates_the_ledger_the_positions_the_board_rows_and_the_grants(
    upgraded: str,
) -> None:
    """Two tables with their CHECKs, dedupe by signature as the schema's own
    fact, the API reading and the loop appending/updating, and the wallet on
    the scoreboard as ``wallet:<8>`` / ``real_observed`` with no dollar figure."""
    wallets = migration_ddl("meme_wallets")
    tables = cast("tuple[str, ...]", wallets.MEME_WALLET_TABLES_0027)
    present = asyncio.run(
        _scalars(
            upgraded,
            "SELECT tablename FROM pg_tables WHERE tablename LIKE 'meme_wallet_%'",
            {},
        )
    )
    assert set(present) == set(tables) == {"meme_wallet_trades", "meme_wallet_positions"}
    for table in tables:
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", table)) == {"SELECT"}
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
            "UPDATE",
        }
    try:
        asyncio.run(_write(upgraded, [_a_wallet_trade("W27_BUY", lab='{"reason": null}')]))
        asyncio.run(_write(upgraded, [_a_wallet_trade("W27_SELL", side="sell", sol=724_716_993)]))
        asyncio.run(
            _write(
                upgraded,
                [
                    _a_wallet_trade(
                        "W27_GHOST",
                        side="unknown",
                        venue=None,
                        mint=None,
                        sol=None,
                        tokens=None,
                        fee=None,
                        decode="none",
                        raw='{"reason": "transaction_not_found"}',
                    )
                ],
            )
        )
        refused: list[tuple[dict[str, object], str]] = [
            ({"side": "unknown", "decode": "none", "raw": None}, "an_unknown_keeps_the_raw"),
            ({"decode": "none"}, "an_unknown_is_what_nothing_decoded"),
            ({"mint": None}, "a_fill_carries_its_numbers"),
            ({"side": "sell", "lab": "{}"}, "lab_context_belongs_to_a_buy"),
            ({"venue": "dex"}, "venue_is_a_known_label"),
        ]
        for overrides, constraint in refused:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, [_a_wallet_trade("W27_BAD", **overrides)]))
        with pytest.raises(DBAPIError, match="pk_meme_wallet_trades"):  # dedupe by signature
            asyncio.run(_write(upgraded, [_a_wallet_trade("W27_BUY")]))
        asyncio.run(_write(upgraded, [_a_wallet_position()]))
        refused_positions: list[tuple[dict[str, object], str]] = [
            ({"mint": "W27_X", "status": "closed"}, "a_closed_position_holds_nothing"),
            ({"mint": "W27_X", "mark_at": None}, "a_mark_names_its_source_and_when"),
            ({"mint": "W27_X", "buys": 0}, "a_buy_says_when"),
            ({"mint": "W27_X", "mark_source": "oracle"}, "mark_source_is_a_known_label"),
        ]
        for overrides, constraint in refused_positions:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, [_a_wallet_position(**overrides)]))
        asyncio.run(
            _write(
                upgraded,
                [
                    _a_wallet_position(
                        mint="W27_DONE",
                        status="closed",
                        held=Decimal(0),
                        open_cost=Decimal(0),
                        mark_sol=None,
                        mark_at=None,
                        mark_source=None,
                        mark_reason="closed",
                        unrealized=None,
                        r=Decimal("0.8333"),
                    )
                ],
            )
        )
        board = asyncio.run(
            _scalars(
                upgraded,
                "SELECT name || ':' || version || ':' || kind || ':' || coalesce(exp_ref, '-') "
                "|| ':' || rule_set_status || ':' || day_brt::text || ':' || bets || ':' || closed "
                "|| ':' || wins || ':' || coalesce(pnl_sol::text, '-') || ':' "
                "|| coalesce(pnl_usd::text, '-') || ':' || unpriced_usd || ':' "
                "|| coalesce(r_sum::text, '-') || ':' || rugs "
                "|| ':' || (rule_set_id = md5('wallet:' || :wallet)::uuid)::text "
                "FROM meme_lab_scoreboard_v1 WHERE kind = 'real_observed'",
                {"wallet": _W27},
            )
        )
        assert board == [
            "wallet:W27_6nAh:1:real_observed:-:active:2026-10-05:2:1:1:2.5000000000:-:1:"
            "0.8333000000:0:true"
        ]
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0027)))


def test_0027_refuses_a_downgrade_that_would_lose_an_observed_trade(upgraded: str) -> None:
    """§17.7: a real fill observed on the chain is evidence — count, name, stop.
    Staged at **0027** first (``0028`` sits on top), then put back at ``head``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_WALLETS_REVISION)
    try:
        asyncio.run(_write(upgraded, [_a_wallet_trade("W27_GUARD")]))
        try:
            with pytest.raises(DBAPIError, match="real fills observed on the chain"):
                command.downgrade(config, "-1")
            assert asyncio.run(_revision(upgraded)) == MEME_WALLETS_REVISION, (
                "the downgrade must not commit"
            )
        finally:
            asyncio.run(_write(upgraded, list(_CLEAN_0027)))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0027_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: the two tables go, the board is ``0022``'s again
    (no reference to the positions), and the upgrade restores all three."""
    config = alembic_config(upgraded)
    uses_positions = (
        "SELECT count(*)::text FROM information_schema.view_table_usage "
        "WHERE view_name = 'meme_lab_scoreboard_v1' AND table_name = 'meme_wallet_positions'"
    )
    command.downgrade(config, MEME_LINES_REVISION)  # through 0028, then 0027
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_LINES_REVISION
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM pg_tables WHERE tablename LIKE 'meme_wallet_%'",
                {},
            )
        ) == ["0"]
        assert asyncio.run(_scalars(upgraded, uses_positions, {})) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM pg_views WHERE viewname = 'meme_lab_scoreboard_v1'",
                {},
            )
        ) == ["1"]
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_scalars(upgraded, uses_positions, {})) == ["1"]
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "meme_lab_scoreboard_v1")) == {
        "SELECT"
    }
    command.check(config)


# ---------------------------------------------------------------------------
# 0028_meme_live — the executor's ledger: the proposal's mode, the real orders,
# the real positions and the durable daily latch (T4.14)
# ---------------------------------------------------------------------------

_P28 = "00000000-0000-4000-8000-000000002801"
_O28 = "00000000-0000-4000-8000-000000002802"
_A_LIVE_PROPOSAL = (
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at, "
    "  decision, decided_by, decided_at, mode) VALUES (:id, 'GUARD_MINT', :rule_set, "
    "  'operator', 'approved', now() + interval '2 minutes', '{}'::jsonb, 'user', now(), :mode)"
)
_A_LIVE_ORDER = (
    "INSERT INTO meme_live_orders (id, proposal_id, side, client_order_id, attempt, status, "
    "  reason, tx_signature, signatures, fill) VALUES (:id, :proposal, :side, :key, :attempt, "
    "  :status, :reason, :signature, CAST(:signatures AS jsonb), CAST(:fill AS jsonb))"
)
_A_LIVE_POSITION = (
    "INSERT INTO meme_live_positions (id, proposal_id, entry_order_id, mint, status, entry_at, "
    "  entry, tokens, sol_spent_lamports, initial_risk_sol, params, mark_sol, mark_at, "
    "  mark_source, sell_requested_at, sell_requested_by, exit_at, exit, pnl_sol, r_multiple) "
    "VALUES (:id, :proposal, :order, 'GUARD_MINT', :status, now() - interval '1 minute', "
    "  '{}'::jsonb, :tokens, :spent, :risk, '{}'::jsonb, :mark_sol, :mark_at, :mark_source, "
    "  :sell_at, :sell_by, :exit_at, CAST(:exit AS jsonb), :pnl, :r)"
)
_CLEAN_0028: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_live_positions WHERE mint = 'GUARD_MINT'", {}),
    (
        "DELETE FROM meme_live_orders WHERE proposal_id IN "
        "(SELECT id FROM meme_proposals WHERE mint = 'GUARD_MINT')",
        {},
    ),
    ("DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT'", {}),
)


def _a_live_order(**overrides: object) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "id": _O28,
        "proposal": _P28,
        "side": "buy",
        "key": f"meme:{_P28}",
        "attempt": 1,
        "status": "admitted",
        "reason": None,
        "signature": None,
        "signatures": "[]",
        "fill": None,
    }
    params.update(overrides)
    return _A_LIVE_ORDER, params


def _a_live_position(**overrides: object) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "id": "00000000-0000-4000-8000-000000002803",
        "proposal": _P28,
        "order": _O28,
        "status": "open",
        "tokens": 1_000_000,
        "spent": 10_000_000,
        "risk": Decimal("0.01"),
        "mark_sol": None,
        "mark_at": None,
        "mark_source": None,
        "sell_at": None,
        "sell_by": None,
        "exit_at": None,
        "exit": None,
        "pnl": None,
        "r": None,
    }
    params.update(overrides)
    return _A_LIVE_POSITION, params


async def _column_privilege_named(
    url: str, role: str, table: str, column: str, privilege: str
) -> bool:
    engine = async_engine(url)
    try:
        async with engine.connect() as connection:
            return bool(
                await connection.scalar(
                    text("SELECT has_column_privilege(:role, :table, :column, :privilege)"),
                    {"role": role, "table": table, "column": column, "privilege": privilege},
                )
            )
    finally:
        await engine.dispose()


def test_0028_adds_the_mode_the_ledger_the_latch_and_the_grants(upgraded: str) -> None:
    """One defaulted column, three tables with their CHECKs, the two idempotency
    keys as the schema's own facts, the seeded ``wallet`` scope, and the API able
    to ask for a sale and to file ``mode`` — and nothing else."""
    live = migration_ddl("meme_live")
    tables = cast("tuple[str, ...]", live.MEME_LIVE_TABLES_0028)
    present = asyncio.run(
        _scalars(upgraded, "SELECT tablename FROM pg_tables WHERE tablename LIKE 'meme_live_%'", {})
    )
    assert (
        set(present)
        == set(tables)
        == {
            "meme_live_orders",
            "meme_live_positions",
            "meme_live_kill_switch",
        }
    )
    for table in tables:
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", table)) == {
            "SELECT",
            "INSERT",
            "UPDATE",
        }
        app = asyncio.run(_table_privileges(upgraded, "hunter_app", table))
        assert "DELETE" not in app and "INSERT" not in app
    for table in cast("tuple[str, ...]", live.MEME_LIVE_APP_READ_ONLY_TABLES):
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", table)) == {"SELECT"}
    for column in cast("tuple[str, ...]", live.MEME_LIVE_SELL_REQUEST_COLUMNS):
        assert asyncio.run(
            _column_privilege_named(upgraded, "hunter_app", "meme_live_positions", column, "UPDATE")
        )
    for column in ("status", "tokens", "exit_at", "mark_sol"):
        assert not asyncio.run(
            _column_privilege_named(upgraded, "hunter_app", "meme_live_positions", column, "UPDATE")
        )
    assert asyncio.run(
        _column_privilege_named(upgraded, "hunter_app", "meme_proposals", "mode", "UPDATE")
    )
    assert not asyncio.run(
        _column_privilege_named(upgraded, "hunter_app", "meme_proposals", "mint", "UPDATE")
    ), "0022 granted the four decision columns; 0028 adds exactly `mode`"
    assert asyncio.run(
        _scalars(upgraded, "SELECT scope || ':' || state FROM meme_live_kill_switch", {})
    ) == ["wallet:ACTIVE"]
    try:
        # The defaulted column: a proposal of yesterday is ``paper`` without saying so.
        asyncio.run(_write(upgraded, [(_A_PROPOSAL, {"id": _P28, "rule_set": _RESEARCH_RULE_SET})]))
        assert asyncio.run(
            _scalars(upgraded, "SELECT mode FROM meme_proposals WHERE id = :id", {"id": _P28})
        ) == ["paper"]
        with pytest.raises(DBAPIError, match="ck_meme_proposals_mode_is_a_known_label"):
            asyncio.run(
                _write(
                    upgraded,
                    [("UPDATE meme_proposals SET mode = 'real' WHERE id = :id", {"id": _P28})],
                )
            )
        refused_orders: list[tuple[dict[str, object], str]] = [
            ({"status": "refused"}, "a_refusal_or_failure_names_its_reason"),
            ({"status": "failed"}, "a_refusal_or_failure_names_its_reason"),
            ({"status": "submitted_unconfirmed"}, "a_sent_order_has_a_signature"),
            ({"status": "confirmed", "signature": "S28"}, "a_confirmed_order_carries_its_fill"),
            ({"status": "landed", "reason": "x"}, "status_is_a_known_label"),
            ({"side": "hold"}, "side_is_a_known_label"),
            ({"attempt": 0}, "attempt_is_positive"),
        ]
        for overrides, constraint in refused_orders:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, [_a_live_order(**overrides)]))
        asyncio.run(
            _write(
                upgraded,
                [
                    _a_live_order(
                        status="confirmed",
                        signature="S28_BUY",
                        signatures='["S28_BUY"]',
                        fill='{"token_amount": 1000000}',
                    )
                ],
            )
        )
        # The two idempotency keys of §9.4: one buy per proposal, one order per signature.
        with pytest.raises(DBAPIError, match="uq_meme_live_orders_one_buy_per_proposal"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        _a_live_order(
                            id="00000000-0000-4000-8000-000000002809", key=f"meme:{_P28}:again"
                        )
                    ],
                )
            )
        with pytest.raises(DBAPIError, match="uq_meme_live_orders_tx_signature"):
            asyncio.run(
                _write(
                    upgraded,
                    [
                        _a_live_order(
                            id="00000000-0000-4000-8000-000000002810",
                            side="sell",
                            key=f"meme:{_P28}:exit:1",
                            status="submitted_unconfirmed",
                            signature="S28_BUY",
                            signatures='["S28_BUY"]',
                        )
                    ],
                )
            )
        refused_positions: list[tuple[dict[str, object], str]] = [
            ({"status": "closed"}, "a_closed_position_says_when"),
            ({"mark_sol": Decimal("0.01")}, "a_mark_says_when_and_whence"),
            ({"sell_at": datetime(2026, 9, 12, tzinfo=UTC)}, "a_sell_request_names_who"),
            ({"spent": 0}, "the_risk_is_what_was_spent"),
            (
                {
                    "status": "closed",
                    "exit_at": datetime(2026, 9, 12, 15, tzinfo=UTC),
                    "exit": "{}",
                    "pnl": Decimal("0.001"),
                },
                "an_exit_carries_its_numbers",
            ),
        ]
        for overrides, constraint in refused_positions:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, [_a_live_position(**overrides)]))
        asyncio.run(_write(upgraded, [_a_live_position()]))
        with pytest.raises(DBAPIError, match="uq_meme_live_positions_proposal_id"):
            asyncio.run(
                _write(upgraded, [_a_live_position(id="00000000-0000-4000-8000-000000002811")])
            )
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0028)))


def test_0028_refuses_a_downgrade_that_would_lose_a_real_order(upgraded: str) -> None:
    """§17.7: a signed order and a live decision are evidence — count, name, stop.
    Staged at **0028** first (``0029`` sits on top), then put back at ``head``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_LIVE_REVISION)
    try:
        asyncio.run(
            _write(
                upgraded,
                [(_A_LIVE_PROPOSAL, {"id": _P28, "rule_set": _RESEARCH_RULE_SET, "mode": "live"})],
            )
        )
        try:
            with pytest.raises(DBAPIError, match="real signatures and real decisions"):
                command.downgrade(config, "-1")
            assert asyncio.run(_revision(upgraded)) == MEME_LIVE_REVISION, (
                "the downgrade must not commit"
            )
            asyncio.run(_write(upgraded, [_a_live_order()]))
            with pytest.raises(DBAPIError, match="1 meme_live_orders rows"):
                command.downgrade(config, "-1")
        finally:
            asyncio.run(_write(upgraded, list(_CLEAN_0028)))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0028_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: the three tables and the column go, ``0027`` is
    what it was; the upgrade restores all and re-seeds the ``wallet`` scope."""
    config = alembic_config(upgraded)
    mode_column = (
        "SELECT count(*)::text FROM information_schema.columns "
        "WHERE table_name = 'meme_proposals' AND column_name = 'mode'"
    )
    command.downgrade(config, MEME_WALLETS_REVISION)  # through 0029, then 0028
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_WALLETS_REVISION
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM pg_tables WHERE tablename LIKE 'meme_live_%'",
                {},
            )
        ) == ["0"]
        assert asyncio.run(_scalars(upgraded, mode_column, {})) == ["0"]
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_scalars(upgraded, mode_column, {})) == ["1"]
    assert asyncio.run(
        _scalars(upgraded, "SELECT scope || ':' || state FROM meme_live_kill_switch", {})
    ) == ["wallet:ACTIVE"]
    command.check(config)


# ---------------------------------------------------------------------------
# 0030_meme_gate_v2 — the honest scoreboard, the 15-second series, the flow gate (T4.16)
# ---------------------------------------------------------------------------

_FLOW_V2_RULE_SET = "01994d00-6c1a-7000-8000-000000000008"
_HYPE_PROBE_2_RULE_SET = "01994d00-6c1a-7000-8000-000000000009"
_HYPE_PROBE_1_RULE_SET = "01994d00-6c1a-7000-8000-000000000004"
_SEEDED_0030 = {"a": _FLOW_V2_RULE_SET, "b": _HYPE_PROBE_2_RULE_SET}
_A_QUALIFIED_BET = (
    "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, mode, status, entry_at, "
    "  entry, initial_risk_sol, params, exit_at, exit, pnl_sol, r_multiple, outcome_quality, "
    "  outcome_quality_reason, outcome_quality_at) VALUES (:id, :proposal, :rule_set, "
    "  'GUARD_MINT', 'paper', :status, now() - interval '2 minutes', '{}'::jsonb, 0.05, "
    "  '{}'::jsonb, CAST(:exit_at AS timestamptz), CAST(:exit AS jsonb), "
    "  CAST(:pnl AS numeric), CAST(:r AS numeric), :quality, :reason, CAST(:at AS timestamptz))"
)
_A_15S_ROW = (
    "INSERT INTO meme_features_15s (as_of, mint, features_version, snapshots_120s, mcap_sol, "
    "  window_reason, progress_reason, holders_reason, tape_reason, creator_net_seller_reason, "
    "  dev_share_reason, snipers_reason) VALUES ('2026-10-05T12:00:00Z', 'GUARD_MINT', "
    "  'meme_features_15s_v1', :snapshots, CAST(:mcap AS numeric), 'no_snapshot', "
    "  'no_snapshot', 'no_holders_reader', 'no_trade_feed', 'no_trade_feed', "
    "  'no_holders_reader', 'no_holders_reader')"
)
_CLEAN_0030: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_features_15s WHERE mint = 'GUARD_MINT'", {}),
)
_SCOREBOARD_COLUMNS = (
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_name = 'meme_lab_scoreboard_v1' AND column_name = 'indeterminate'"
)


def _a_qualified_bet(
    ordinal: int,
    rule_set: str,
    *,
    status: str = "closed",
    quality: str = "measured",
    reason: str | None = None,
    at: datetime | None = None,
    exit_reason: str = "rug_no_snapshot",
) -> list[tuple[str, dict[str, object]]]:
    proposal = f"00000000-0000-4000-8000-0000000006{ordinal:02d}"
    bet = f"00000000-0000-4000-8000-0000000007{ordinal:02d}"
    closed = status == "closed"
    return [
        (_A_PROPOSAL, {"id": proposal, "rule_set": rule_set}),
        (
            _A_QUALIFIED_BET,
            {
                "id": bet,
                "proposal": proposal,
                "rule_set": rule_set,
                "status": status,
                "exit_at": datetime(2026, 10, 5, 12, 5, tzinfo=UTC) if closed else None,
                "exit": json.dumps({"reason": exit_reason}) if closed else None,
                "pnl": Decimal("-0.05") if closed else None,
                "r": Decimal(-1) if closed else None,
                "quality": quality,
                "reason": reason,
                "at": at,
            },
        ),
    ]


def test_0030_adds_outcome_quality_the_15s_series_and_seeds_the_flow_arms(upgraded: str) -> None:
    """Three columns on the bet with their CHECKs, the partitioned series with
    its grants, the scoreboard summing measured closes only, the two arms of
    EXP-M5 with the brief's frozen parameters — and nothing retired."""
    ddl = migration_ddl("meme_gate_v2")
    frozen = cast("tuple[str, ...]", ddl.BET_COLUMNS_0030)
    names = ", ".join(f"'{column}'" for column in frozen)
    present = asyncio.run(
        _scalars(
            upgraded,
            "SELECT column_name FROM information_schema.columns "  # noqa: S608
            f"WHERE table_name = 'meme_paper_bets' AND column_name IN ({names})",
            {},
        )
    )
    assert set(present) == set(frozen)
    assert asyncio.run(_relation_exists(upgraded, "meme_features_15s"))
    for year, month in cast("tuple[tuple[int, int], ...]", ddl.MEME_INITIAL_MONTHS_0030):
        child = partition_name("meme_features_15s", year, month)
        assert asyncio.run(_relation_exists(upgraded, child)), child
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", child)) == set()
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", child)) == set()
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "meme_features_15s")) == {"SELECT"}
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_features_15s")) == {
        "SELECT",
        "INSERT",
    }
    assert asyncio.run(_scalars(upgraded, _SCOREBOARD_COLUMNS, {})) == ["indeterminate"]
    seeds = asyncio.run(
        _scalars(
            upgraded,
            "SELECT name || '/' || version || ':' || kind || ':' || coalesce(exp_ref, '-') || ':' "
            "|| status || ':' || coalesce(params ->> 'clock', '1m') || ':' "
            "|| (params ->> 'gate_key') || ':' || (params ->> 'gate_version') || ':' "
            "|| (params ->> 'size_sol') || ':' || (params ->> 'target_x') || ':' "
            "|| (params ->> 'trailing_pct') || ':' || coalesce(params ->> 'trailing_arm_x', '-') "
            "|| ':' || (params ->> 'max_hold_s') || ':' || (params ->> 'max_loss_pct') || ':' "
            "|| (params ->> 'min_unique_buyers') || ':' || (params ->> 'max_sells_to_buys') "
            "|| ':' || (params ->> 'require_positive_flow') || ':' "
            "|| coalesce(params ->> 'require_holders_rising', '-') || ':' "
            "|| coalesce(params ->> 'require_progress_rising', '-') || ':' "
            "|| (params ->> 'min_progress_pct') || ':' || (params ->> 'max_snipers') || ':' "
            "|| (params ->> 'max_dev_share') || ':' || (params ->> 'dev_share_unknown_allowed') "
            "|| ':' || coalesce(params ->> 'exit_on_line_break', '-') || ':' "
            "|| coalesce(params ->> 'min_hype_score', '-') || ':' "
            "|| coalesce(params ->> 'scale_gate', '-') || ':' || (params ->> 'max_open_positions') "
            "|| ':' || (params ->> 'pedigree_exclusions') "
            "FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY name, version",
            dict(_SEEDED_0030),
        )
    )
    assert seeds == [
        "flow_v2/1:research_only:EXP-M5:active:15s:fluxo_e_holders:1:0.05:3:35:1.5:1800:50:10:0.6"
        ":true:true:true:5:2:0.10:false:true:-:-:5:true",
        "hype_probe_v0/2:research_only:EXP-M5:active:1m:sonda_de_hype:2:0.01:3:40:-:600:50:10:0.6"
        ":true:-:-:0:2:0.10:true:-:0.6:trendline_v0/1:5:true",
    ]
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT status FROM meme_rule_sets WHERE id IN (:a, :b) ORDER BY name",
            {"a": _RESEARCH_RULE_SET, "b": _HYPE_PROBE_1_RULE_SET},
        )
    ) == ["active", "active"], "0030 retires nothing: the audited --deprecate does"
    try:
        # The default: a bet written without the column is measured.
        asyncio.run(_write(upgraded, _a_marked_bet(6, _RESEARCH_RULE_SET)))
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT outcome_quality || ':' || (outcome_quality_reason IS NULL)::text "
                "FROM meme_paper_bets WHERE id = '00000000-0000-4000-8000-000000000506'",
                {},
            )
        ) == ["measured:true"]
        stamp = datetime(2026, 10, 5, 12, 10, tzinfo=UTC)
        asyncio.run(
            _write(
                upgraded,
                _a_qualified_bet(
                    1,
                    _RESEARCH_RULE_SET,
                    quality="indeterminate",
                    reason="no_snapshot_in_window",
                    at=stamp,
                ),
            )
        )
        asyncio.run(_write(upgraded, _a_qualified_bet(2, _RESEARCH_RULE_SET, exit_reason="target")))
        refused: list[tuple[dict[str, object], str]] = [
            ({"quality": "guess"}, "outcome_quality_is_a_known_label"),
            (
                {"status": "open", "quality": "indeterminate", "reason": "x", "at": stamp},
                "an_indeterminate_bet_is_closed",
            ),
            ({"quality": "indeterminate"}, "an_indeterminate_outcome_names_its_reason"),
            (
                {"quality": "indeterminate", "reason": "x"},
                "an_indeterminate_outcome_names_its_reason",
            ),
            ({"reason": "x", "at": stamp}, "an_indeterminate_outcome_names_its_reason"),
        ]
        for overrides, constraint in refused:
            with pytest.raises(DBAPIError, match=constraint):
                asyncio.run(_write(upgraded, _a_qualified_bet(3, _RESEARCH_RULE_SET, **overrides)))  # type: ignore[arg-type]
        # The scoreboard: two closes, one measured (-0,05 SOL, -1 R) and one
        # indeterminate that the sums leave out and the new column counts.
        board = asyncio.run(
            _scalars(
                upgraded,
                "SELECT sum(closed)::text || ':' || sum(indeterminate)::text || ':' "
                "|| sum(pnl_sol)::text || ':' || sum(r_sum)::text || ':' || sum(rugs)::text "
                "|| ':' || sum(wins)::text "
                "FROM meme_lab_scoreboard_v1 WHERE rule_set_id = CAST(:rs AS uuid) "
                "AND day_brt = (now() AT TIME ZONE 'America/Sao_Paulo')::date",
                {"rs": _RESEARCH_RULE_SET},
            )
        )
        assert board == ["2:1:-0.0500000000:-1.0000000000:1:0"]
        # The series: a blind row lands; a market cap without its photo does not.
        asyncio.run(_write(upgraded, [(_A_15S_ROW, {"snapshots": 0, "mcap": None})]))
        with pytest.raises(DBAPIError, match="a_market_cap_names_its_photo"):
            asyncio.run(_write(upgraded, [(_A_15S_ROW, {"snapshots": 1, "mcap": Decimal("30")})]))
        with pytest.raises(DBAPIError, match="counts_are_not_negative"):
            asyncio.run(_write(upgraded, [(_A_15S_ROW, {"snapshots": -1, "mcap": None})]))
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0030)))
        asyncio.run(_write(upgraded, list(_CLEAN_0029)))


def test_0030_refuses_a_downgrade_that_would_lose_an_outcome_or_the_series(
    upgraded: str,
) -> None:
    """§17.7: an indeterminate outcome, a 15-second row and a bet under a
    seeded set are evidence — count, name, stop. Staged at **0030** first
    (``0031`` sits on top), then put back at ``head``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_GATE_V2_REVISION)
    stamp = datetime(2026, 10, 5, 12, 10, tzinfo=UTC)
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            _a_qualified_bet(4, _RESEARCH_RULE_SET, quality="indeterminate", reason="x", at=stamp),
            "reclassified indeterminate",
        ),
        ([(_A_15S_ROW, {"snapshots": 0, "mcap": None})], "15-second series holds rows"),
        (_a_qualified_bet(5, _FLOW_V2_RULE_SET), "reference the seeded flow_v2"),
    ]
    try:
        for statements, message in guarded:
            asyncio.run(_write(upgraded, statements))
            try:
                with pytest.raises(DBAPIError, match=message):
                    command.downgrade(config, "-1")
                assert asyncio.run(_revision(upgraded)) == MEME_GATE_V2_REVISION, (
                    "the downgrade must not commit"
                )
            finally:
                asyncio.run(_write(upgraded, list(_CLEAN_0030)))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0030_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: the columns, the series and the seed go, the
    ``0027`` scoreboard is what it was; the upgrade restores all."""
    config = alembic_config(upgraded)
    columns = (
        "SELECT count(*)::text FROM information_schema.columns "
        "WHERE table_name = 'meme_paper_bets' AND column_name IN "
        "('outcome_quality', 'outcome_quality_reason', 'outcome_quality_at')"
    )
    command.downgrade(config, MEME_MOONSHOT_REVISION)  # through 0031, then 0030
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_MOONSHOT_REVISION
        assert asyncio.run(_scalars(upgraded, columns, {})) == ["0"]
        assert not asyncio.run(_relation_exists(upgraded, "meme_features_15s"))
        assert asyncio.run(_scalars(upgraded, _SCOREBOARD_COLUMNS, {})) == []
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM meme_rule_sets WHERE id IN (:a, :b)",
                dict(_SEEDED_0030),
            )
        ) == ["0"]
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_scalars(upgraded, columns, {})) == ["3"]
    assert asyncio.run(_relation_exists(upgraded, "meme_features_15s"))
    assert asyncio.run(_scalars(upgraded, _SCOREBOARD_COLUMNS, {})) == ["indeterminate"]
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT count(*)::text FROM meme_rule_sets WHERE id IN (:a, :b) AND status = 'active'",
            dict(_SEEDED_0030),
        )
    ) == ["2"]
    command.check(config)


# ---------------------------------------------------------------------------
# 0032_meme_activity — the tape by batch (T4.2g)
# ---------------------------------------------------------------------------

_AN_ACTIVITY_ROW = (
    "INSERT INTO meme_market_activity_1m (end_time, mint, window_name, window_s, received_at, empty, "
    "  num_txs, buys, sells, unique_users, unique_buyers, unique_sellers, volume_usd, "
    "  buy_volume_usd, sell_volume_usd, price_change_pct, sol_usd, sol_usd_observed_at, "
    "  buy_volume_sol, sell_volume_sol) VALUES ('2026-10-05T12:00:00Z', 'GUARD_MINT', :window, "
    "  :window_s, '2026-10-05T12:00:01Z', :empty, :txs, :buys, :sells, :users, :buyers, :sellers, "
    "  :volume, :buy_usd, :sell_usd, :change, CAST(:sol_usd AS numeric), "
    "  CAST(:quote_at AS timestamptz), CAST(:buy_sol AS numeric), CAST(:sell_sol AS numeric))"
)
_A_TAPED_V3_ROW = (
    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage, "
    "  progress_reason, curve_reason, unique_buyers, buy_sell_ratio_reason, top10_share_reason, "
    "  creator_sold_reason, holders_reason, dev_share_reason, snipers_reason, "
    "  buys_1m, sells_1m, net_sol_flow_1m, curve_volume_1m_sol, creator_net_seller_reason, "
    "  tape_source, tape_window_s, tape_as_of) VALUES ('2026-10-05T12:00:00Z', 'GUARD_MINT', "
    "  'meme_features_v3', 1, 'not_polled', 'not_polled', 3, 'no_sells', 'no_holders_reader', "
    "  'no_trade_feed', 'no_holders_reader', 'no_holders_reader', 'no_holders_reader', "
    "  3, 0, 0.1, 0.1, 'no_trade_feed', :source, :window_s, CAST(:as_of AS timestamptz))"
)
_AN_UNTAPED_V3_ROW = (
    "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage, "  # noqa: S608
    f"  {_REASON_COLUMNS}, tape_source, tape_window_s, tape_as_of) VALUES "
    f"('2026-10-05T12:00:00Z', 'GUARD_MINT', 'meme_features_v3', 1, {_REASON_VALUES}, "
    "  :source, :window_s, CAST(:as_of AS timestamptz))"
)
_A_TAPED_15S_ROW = (
    "INSERT INTO meme_features_15s (as_of, mint, features_version, snapshots_120s, "
    "  window_reason, progress_reason, holders_reason, buys_60s, sells_60s, unique_buyers_60s, "
    "  net_sol_flow_60s, curve_volume_60s_sol, creator_net_seller_reason, dev_share_reason, "
    "  snipers_reason, tape_source, tape_window_s, tape_as_of) VALUES ('2026-10-05T12:00:00Z', "
    "  'GUARD_MINT', 'meme_features_15s_v1', 0, 'no_snapshot', 'no_snapshot', "
    "  'no_holders_reader', 2, 1, 2, 0.05, 0.15, 'no_trade_feed', 'no_holders_reader', "
    "  'no_holders_reader', :source, :window_s, CAST(:as_of AS timestamptz))"
)
_CLEAN_0032: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_market_activity_1m WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_features_1m WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_features_15s WHERE mint = 'GUARD_MINT'", {}),
)
_TAPE_SOURCE_COLUMNS = (
    "SELECT count(*)::text FROM information_schema.columns "
    "WHERE table_name = :table AND column_name IN ('tape_source', 'tape_window_s', 'tape_as_of')"
)
_MINUTE_0032 = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
_AS_OF_0032 = datetime(2026, 10, 5, 11, 59, 57, tzinfo=UTC)
_QUOTE_AT_0032 = datetime(2026, 10, 5, 11, 59, 30, tzinfo=UTC)


def _an_activity(**overrides: object) -> tuple[str, dict[str, object]]:
    params: dict[str, object] = {
        "window": "1m",
        "window_s": 60,
        "empty": False,
        "txs": 5,
        "buys": 3,
        "sells": 2,
        "users": 4,
        "buyers": 3,
        "sellers": 2,
        "volume": Decimal("120.5"),
        "buy_usd": Decimal("80.5"),
        "sell_usd": Decimal("40"),
        "change": Decimal("12.5"),
        "sol_usd": Decimal("200"),
        "quote_at": _QUOTE_AT_0032,
        "buy_sol": Decimal("0.4025"),
        "sell_sol": Decimal("0.2"),
    }
    params.update(overrides)
    return _AN_ACTIVITY_ROW, params


def test_0032_adds_the_activity_table_and_names_the_tape_of_both_series(upgraded: str) -> None:
    """The partitioned table with its grants and CHECKs, and the three
    provenance columns on ``meme_features_1m``/``meme_features_15s`` with
    theirs — a source names its window and instant, is a known label, and
    implies a tape."""
    ddl = migration_ddl("meme_activity")
    assert asyncio.run(_relation_exists(upgraded, "meme_market_activity_1m"))
    for year, month in cast("tuple[tuple[int, int], ...]", ddl.MEME_INITIAL_MONTHS_0032):
        child = partition_name("meme_market_activity_1m", year, month)
        assert asyncio.run(_relation_exists(upgraded, child)), child
        assert asyncio.run(_table_privileges(upgraded, "hunter_app", child)) == set()
        assert asyncio.run(_table_privileges(upgraded, "hunter_worker", child)) == set()
    assert asyncio.run(_table_privileges(upgraded, "hunter_app", "meme_market_activity_1m")) == {
        "SELECT"
    }
    assert asyncio.run(_table_privileges(upgraded, "hunter_worker", "meme_market_activity_1m")) == {
        "SELECT",
        "INSERT",
    }
    for table in ("meme_features_1m", "meme_features_15s"):
        assert asyncio.run(_scalars(upgraded, _TAPE_SOURCE_COLUMNS, {"table": table})) == ["3"]
    try:
        asyncio.run(_write(upgraded, [_an_activity()]))
        asyncio.run(
            _write(
                upgraded,
                [
                    _an_activity(
                        window="5m",
                        window_s=300,
                        empty=True,
                        txs=0,
                        buys=0,
                        sells=0,
                        users=0,
                        buyers=0,
                        sellers=0,
                        volume=0,
                        buy_usd=0,
                        sell_usd=0,
                        change=None,
                        sol_usd=None,
                        quote_at=None,
                        buy_sol=None,
                        sell_sol=None,
                    )
                ],
            )
        )
        for refused in (
            _an_activity(window="1h", window_s=3600, quote_at=None),  # a quote names its instant
            _an_activity(window="1h", window_s=3600, buys=-1),
            _an_activity(window="2m", window_s=120),
            _an_activity(window="1h", window_s=3600, empty=True),  # empty means zeros
            _an_activity(window="1h", window_s=3600, sol_usd=Decimal(0)),
        ):
            with pytest.raises(DBAPIError):
                asyncio.run(_write(upgraded, [refused]))
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        _A_TAPED_V3_ROW,
                        {"source": "activity_1m", "window_s": 60, "as_of": _AS_OF_0032},
                    ),
                    (
                        _A_TAPED_15S_ROW,
                        {
                            "source": "swap_api_trades",
                            "window_s": 60,
                            "as_of": _MINUTE_0032,
                        },
                    ),
                ],
            )
        )
        asyncio.run(_write(upgraded, list(_CLEAN_0032)))
        refused_tapes: list[tuple[str, dict[str, object]]] = [
            (
                _A_TAPED_V3_ROW,
                {"source": "activity_5m", "window_s": 300, "as_of": _MINUTE_0032},
            ),
            (_A_TAPED_V3_ROW, {"source": "activity_1m", "window_s": None, "as_of": None}),
            (
                _AN_UNTAPED_V3_ROW,
                {"source": "activity_1m", "window_s": 60, "as_of": _MINUTE_0032},
            ),
            (_A_TAPED_15S_ROW, {"source": "activity_1m", "window_s": 60, "as_of": None}),
            (
                _A_TAPED_15S_ROW,
                {"source": "batch", "window_s": 60, "as_of": _MINUTE_0032},
            ),
        ]
        for statement, params in refused_tapes:
            with pytest.raises(DBAPIError):
                asyncio.run(_write(upgraded, [(statement, params)]))
    finally:
        asyncio.run(_write(upgraded, list(_CLEAN_0032)))


def test_0032_refuses_a_downgrade_that_would_lose_the_activity(upgraded: str) -> None:
    """§17.7: a batch row, or a feature row that names the batch as its tape,
    is evidence — count, name, stop. Staged at **0032** first (``0033`` sits on
    top), then put back at ``head``."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_ACTIVITY_REVISION)
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        ([_an_activity()], "meme_market_activity_1m rows exist"),
        (
            [
                (
                    _A_TAPED_V3_ROW,
                    {"source": "activity_1m", "window_s": 60, "as_of": _AS_OF_0032},
                )
            ],
            "minutes folded from the batch route",
        ),
        (
            [
                (
                    _A_TAPED_15S_ROW,
                    {"source": "activity_1m", "window_s": 60, "as_of": _AS_OF_0032},
                )
            ],
            "instants folded from the batch route",
        ),
    ]
    try:
        for statements, message in guarded:
            asyncio.run(_write(upgraded, statements))
            try:
                with pytest.raises(DBAPIError, match=message):
                    command.downgrade(config, "-1")
                assert asyncio.run(_revision(upgraded)) == MEME_ACTIVITY_REVISION, (
                    "the downgrade must not commit"
                )
            finally:
                asyncio.run(_write(upgraded, list(_CLEAN_0032)))
        # A minute folded from the per-mint tape is not the batch's evidence: it reverses.
        asyncio.run(
            _write(
                upgraded,
                [
                    (
                        _A_TAPED_V3_ROW,
                        {
                            "source": "swap_api_trades",
                            "window_s": 60,
                            "as_of": _MINUTE_0032,
                        },
                    )
                ],
            )
        )
        command.downgrade(config, "-1")
        assert asyncio.run(_revision(upgraded)) == MEME_LAB_TICKS_REVISION
    finally:
        command.upgrade(config, "head")
        asyncio.run(_write(upgraded, list(_CLEAN_0032)))
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    command.check(config)


def test_0032_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: the table and the six columns go; the upgrade restores all."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_LAB_TICKS_REVISION)
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_LAB_TICKS_REVISION
        assert not asyncio.run(_relation_exists(upgraded, "meme_market_activity_1m"))
        for table in ("meme_features_1m", "meme_features_15s"):
            assert asyncio.run(_scalars(upgraded, _TAPE_SOURCE_COLUMNS, {"table": table})) == ["0"]
        assert asyncio.run(_relation_exists(upgraded, "meme_lab_ticks")), "0031 stays"
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_relation_exists(upgraded, "meme_market_activity_1m"))
    for table in ("meme_features_1m", "meme_features_15s"):
        assert asyncio.run(_scalars(upgraded, _TAPE_SOURCE_COLUMNS, {"table": table})) == ["3"]
    command.check(config)


# ---------------------------------------------------------------------------
# 0033_meme_operator_3 — the desk proposes through the E1 gate (T4.19)
# ---------------------------------------------------------------------------

_OPERATOR_3_RULE_SET = "01994d00-6c1a-7000-8000-00000000000a"
"""``operator/2`` is ``_OPERATOR_2_RULE_SET`` of the ``0029`` section (``…0007``)."""
_ACTIVE_OPERATOR_SETS = (
    "SELECT name || '/' || version FROM meme_rule_sets "
    "WHERE kind = 'operator' AND status = 'active' ORDER BY version"
)
_CLEAN_0033: tuple[tuple[str, dict[str, object]], ...] = (
    ("DELETE FROM meme_paper_bets WHERE mint = 'GUARD_MINT'", {}),
    ("DELETE FROM meme_proposals WHERE mint = 'GUARD_MINT'", {}),
)


def test_0033_seeds_operator_3_through_the_flow_gate_and_retires_operator_2(
    upgraded: str,
) -> None:
    """``operator/3`` = ``flow_v2/1``'s params (the E1 gate, the E2 exclusions,
    the 15-second clock, the 3× / 35 % after 1,5× / 30 min / 50 % exits) with
    only the two numbers the brief changes for a buy by hand: ``ttl_s = 180``
    and ``max_open_positions = 2``; ``operator/2`` (EXP-M1's gate) retired."""
    seeds = asyncio.run(
        _scalars(
            upgraded,
            "SELECT name || '/' || version || ':' || kind || ':' || coalesce(exp_ref, '-') || ':' "
            "|| status || ':' || (params ->> 'gate_key') || '/' || (params ->> 'gate_version') "
            "|| ':' || (params ->> 'clock') || ':' || (params ->> 'pedigree_exclusions') || ':' "
            "|| (params ->> 'ttl_s') || ':' || (params ->> 'size_sol') || ':' "
            "|| (params ->> 'max_open_positions') || ':' || (params ->> 'target_x') || ':' "
            "|| (params ->> 'trailing_pct') || ':' || (params ->> 'trailing_arm_x') || ':' "
            "|| (params ->> 'max_hold_s') || ':' || (params ->> 'max_loss_pct') || ':' "
            "|| (params ->> 'exit_on_line_break') || ':' || (params ->> 'max_sol_per_bet') "
            "FROM meme_rule_sets WHERE id = :id",
            {"id": _OPERATOR_3_RULE_SET},
        )
    )
    assert seeds == [
        "operator/3:operator:-:active:fluxo_e_holders/1:15s:true:180:0.05:2:3:35:1.5:1800:50"
        ":true:0.05"
    ]
    same_gate = asyncio.run(
        _scalars(
            upgraded,
            "SELECT ((o.params - 'ttl_s' - 'max_open_positions') "
            "        = (f.params - 'max_open_positions'))::text "
            "FROM meme_rule_sets o, meme_rule_sets f WHERE o.id = :o AND f.id = :f",
            {"o": _OPERATOR_3_RULE_SET, "f": _FLOW_V2_RULE_SET},
        )
    )
    assert same_gate == ["true"], "every other key is flow_v2/1's, byte for byte"
    assert asyncio.run(
        _scalars(
            upgraded,
            "SELECT status || ':' || (retired_at IS NOT NULL)::text FROM meme_rule_sets "
            "WHERE id = :id",
            {"id": _OPERATOR_2_RULE_SET},
        )
    ) == ["retired:true"]
    assert asyncio.run(_scalars(upgraded, _ACTIVE_OPERATOR_SETS, {})) == ["operator/3"], (
        "exactly one active operator set for the desk's manual buys"
    )


def test_0033_refuses_a_downgrade_while_a_proposal_or_a_bet_references_operator_3(
    upgraded: str,
) -> None:
    """§17.7: a proposal the desk saw and a bet it filled under ``operator/3``
    are evidence — count, name, stop. ``0033`` is the head: no staging."""
    config = alembic_config(upgraded)
    proposal = "00000000-0000-4000-8000-000000000a01"
    bet = "00000000-0000-4000-8000-000000000a02"
    guarded: list[tuple[list[tuple[str, dict[str, object]]], str]] = [
        (
            [(_A_PROPOSAL, {"id": proposal, "rule_set": _OPERATOR_3_RULE_SET})],
            "proposals reference the seeded operator/3",
        ),
        (
            [
                (_A_PROPOSAL, {"id": proposal, "rule_set": _RESEARCH_RULE_SET}),
                (
                    _A_BET,
                    {
                        "id": bet,
                        "proposal": proposal,
                        "rule_set": _OPERATOR_3_RULE_SET,
                        "mode": "paper",
                    },
                ),
            ],
            "bets reference the seeded operator/3",
        ),
    ]
    for statements, message in guarded:
        asyncio.run(_write(upgraded, statements))
        try:
            with pytest.raises(DBAPIError, match=message):
                command.downgrade(config, "-1")
            assert asyncio.run(_revision(upgraded)) == HEAD_REVISION, (
                "the downgrade must not commit"
            )
        finally:
            asyncio.run(_write(upgraded, list(_CLEAN_0033)))
    command.check(config)


def test_0033_reverses_on_a_clean_database_and_comes_back(upgraded: str) -> None:
    """The operator's rollback: ``operator/3`` goes, ``operator/2`` comes back
    active, ``0032`` stays; the upgrade restores the hand-over."""
    config = alembic_config(upgraded)
    command.downgrade(config, MEME_ACTIVITY_REVISION)
    try:
        assert asyncio.run(_revision(upgraded)) == MEME_ACTIVITY_REVISION
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT count(*)::text FROM meme_rule_sets WHERE id = :id",
                {"id": _OPERATOR_3_RULE_SET},
            )
        ) == ["0"]
        assert asyncio.run(
            _scalars(
                upgraded,
                "SELECT status || ':' || (retired_at IS NULL)::text FROM meme_rule_sets "
                "WHERE id = :id",
                {"id": _OPERATOR_2_RULE_SET},
            )
        ) == ["active:true"]
        assert asyncio.run(_scalars(upgraded, _ACTIVE_OPERATOR_SETS, {})) == ["operator/2"]
        assert asyncio.run(_relation_exists(upgraded, "meme_market_activity_1m")), "0032 stays"
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_scalars(upgraded, _ACTIVE_OPERATOR_SETS, {})) == ["operator/3"]
    command.check(config)


_AN_EXTRA_OPERATOR_SET = (
    "INSERT INTO meme_rule_sets (id, name, version, kind, params, code_ref, exp_ref, status) "
    "VALUES (:id, 'operator_guard_0033', '1', 'operator', '{}'::jsonb, 'x', NULL, 'active')"
)


def test_0033_refuses_to_upgrade_a_desk_that_already_has_another_active_operator_set(
    upgraded: str,
) -> None:
    """The desk's invariant is asserted after the hand-over: a second active
    ``operator`` set (planted by hand) makes the upgrade stop — refused, not
    repaired — and the failed upgrade commits nothing."""
    config = alembic_config(upgraded)
    extra = "00000000-0000-4000-8000-000000000a09"
    command.downgrade(config, MEME_ACTIVITY_REVISION)
    try:
        asyncio.run(_write(upgraded, [(_AN_EXTRA_OPERATOR_SET, {"id": extra})]))
        try:
            with pytest.raises(DBAPIError, match="2 operator sets are active"):
                command.upgrade(config, "head")
            assert asyncio.run(_revision(upgraded)) == MEME_ACTIVITY_REVISION, (
                "the upgrade must not commit"
            )
            assert asyncio.run(_scalars(upgraded, _ACTIVE_OPERATOR_SETS, {})) == [
                "operator_guard_0033/1",
                "operator/2",
            ], "the refused upgrade left operator/2 active and planted nothing"
        finally:
            asyncio.run(
                _write(upgraded, [("DELETE FROM meme_rule_sets WHERE id = :id", {"id": extra})])
            )
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(_revision(upgraded)) == HEAD_REVISION
    assert asyncio.run(_scalars(upgraded, _ACTIVE_OPERATOR_SETS, {})) == ["operator/3"]
