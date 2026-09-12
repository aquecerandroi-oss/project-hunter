"""What each role may actually do — DATABASE.md §1.2, SECURITY.md §3.

The T04 cross-review proved two holes that ``GRANT ... ON ALL TABLES IN SCHEMA
public`` opens and that no test covered:

1. the append-only rule was enforced by revoking UPDATE/DELETE on the *parent*
   only, so ``DELETE FROM audit_logs_2026_09`` succeeded for ``hunter_app``
   (Postgres does not inherit privileges from a partitioned parent: access
   through the parent is checked on the parent, access to a child on the child);
2. the API role had full DML on every global catalogue, market and analysis
   table — ``UPDATE feature_flags`` from the API was a grant away from nothing.

Both are asserted here against the frozen grant lists in ``ddl/security.py``,
including partition children.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hunter_core.domain.types import uuid7

from .conftest import migration_ddl

pytestmark = pytest.mark.integration

_AS_APP = text("SET LOCAL ROLE hunter_app")
_DENIED = "permission denied"

_WRITE_PRIVILEGES = ("UPDATE", "DELETE")


def _security() -> object:
    return migration_ddl("security")


def _shadow_tables(name: str) -> tuple[str, ...]:
    """A grant-list constant added by a revision after ``0001``.

    ``ddl.tables``' four classes are frozen as of ``0001`` — a revision must
    describe the schema *as of that revision* — so ``0002_shadow_lab`` states
    its own lists in ``ddl/shadow.py`` and this test unions them. Every table
    still has to land in exactly one class.
    """
    return cast(tuple[str, ...], getattr(migration_ddl("shadow"), name))


def _analysis_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0003_analysis``'s lists in ``ddl/analysis.py``.

    It adds a fifth ``hunter_worker`` class — ``SELECT``/``INSERT``/``DELETE``
    and never ``UPDATE`` — because a ``feature_baselines`` revision may be
    created and expired but never changed.
    """
    return cast(tuple[str, ...], getattr(migration_ddl("analysis"), name))


def _paper_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0006_paper_wallet``'s lists in ``ddl/paper.py``.

    It adds two ``hunter_app`` classes on top of ``0001``'s four — an append-only
    pair (the currency anchor and the participation ledger, which are records of
    fact) and a no-delete pair (the exit intentions and the risk state, which are
    mutable but may never be removed) — plus read-only access to the two new
    global archives.
    """
    return cast(tuple[str, ...], getattr(migration_ddl("paper"), name))


def _paper_roles_2_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0008_paper_roles_2``'s list in ``ddl/paper_roles_2.py``.

    It adds no class: ``APP_READ_ONLY_TABLES_0008`` **moves** four tables
    (``orders``, ``fills``, ``positions``, ``trades``) out of ``0001``'s
    ``APP_WRITE_TABLES`` and into read-only, so every test below subtracts it
    from the write class before counting. The partition stays exact, and
    ``test_migrations.py::test_0008_reclassifies_only_tables_0001_had_already_classified``
    is what keeps the move a move.
    """
    return cast(tuple[str, ...], getattr(migration_ddl("paper_roles_2"), name))


def _replay_run_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0013_replay_runs``'s lists in ``ddl/replay_runs.py``.

    It adds no class either: ``replay_runs`` is read-only for ``hunter_app``
    (the scoreboard reads a receipt) and append-only for ``hunter_worker`` (the
    replay engine writes one and may never edit it), which is the shape
    ``fx_observations`` already has — a table in ``PAPER_APP_READ_ONLY_TABLES``
    on one side and ``PAPER_WORKER_APPEND_TABLES`` on the other (§18.9).
    """
    return cast(tuple[str, ...], getattr(migration_ddl("replay_runs"), name))


def _breadth_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0019_market_breadth``'s lists in ``ddl/breadth.py``.

    It adds no class either: ``market_breadth`` is read-only for ``hunter_app``
    and append-only for ``hunter_worker`` — the scanner produces one reading per
    closed minute, the strategy-worker's gate reads it, and neither may edit a
    minute that a decision may already have been gated by. Exactly the
    ``replay_runs`` shape (§18.9, T3.77).
    """
    return cast(tuple[str, ...], getattr(migration_ddl("breadth"), name))


def _dispersion_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0020_market_dispersion``'s lists in ``ddl/dispersion.py``.

    It adds no class either: ``market_dispersion`` is read-only for ``hunter_app``
    and append-only for ``hunter_worker`` — the scanner produces one reading per
    closed minute, the strategy-worker's gate reads it, and neither may edit a
    minute a decision may already have been gated by. Exactly the
    ``market_breadth`` shape (§18.9, §31, T3.90).
    """
    return cast(tuple[str, ...], getattr(migration_ddl("dispersion"), name))


def _meme_lab_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0022_meme_lab``'s lists in ``ddl/meme_lab.py``.

    It adds **three** ``hunter_app`` classes, because the desk writes: read-only
    (``meme_rule_sets``, ``meme_paper_bets``), append (``meme_operator_commands``
    — an order is written once) and *decision* (``meme_proposals`` —
    ``SELECT``/``INSERT`` plus ``UPDATE`` of exactly the four decision columns,
    the ``0007`` column-grant shape). Nobody has ``DELETE`` on any of the four.
    """
    return cast(tuple[str, ...], getattr(migration_ddl("meme_lab"), name))


def _meme_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0021_meme_radar``'s lists in ``ddl/meme_radar.py``.

    It adds no class either. Four of the five tables are the ``market_breadth``
    shape — read-only for ``hunter_app``, append-only for ``hunter_worker`` — and
    the fifth, ``meme_tokens``, is the one place retention cannot drop a partition
    (its key is the mint), so the worker carries ``UPDATE``/``DELETE`` there behind
    a write-once trigger and a declared ``app.meme_retention`` marker (§17.2's
    ``feature_baselines`` precedent).
    """
    return cast(tuple[str, ...], getattr(migration_ddl("meme_radar"), name))


def _lock_tables(name: str) -> tuple[str, ...]:
    """The same, for ``0005_feature_baselines_lock_grant``'s ``ddl/baseline_lock.py``.

    It grants no table class of its own: it hands ``hunter_worker`` the single
    ``UPDATE`` privilege PostgreSQL demands for a row lock, on a table ``0003``
    already classified. See that module for why the archive is not weakened.
    """
    return cast(tuple[str, ...], getattr(migration_ddl("baseline_lock"), name))


def _security_tables(name: str) -> tuple[str, ...]:
    """A frozen grant-list constant from ``ddl.security``, correctly typed.

    ``ddl.security`` is imported at test time via ``sys.path`` surgery (the
    same way Alembic itself reaches it) rather than a static import, so
    pyright sees only ``ModuleType`` and infers ``Unknown`` for any attribute
    on it. Every constant this reaches for is a documented, frozen
    ``tuple[str, ...]`` — see ``infra/migrations/ddl/tables.py`` — so a single
    typed ``cast`` here is enough to make every call site fully typed.
    """
    return cast(tuple[str, ...], getattr(_security(), name))


@pytest_asyncio.fixture
async def app_connection(schema_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose transaction runs as ``hunter_app``.

    ``GRANT hunter_app TO CURRENT_USER`` is the same one-off grant a deployment
    makes so the login role may ``SET ROLE`` into the application role.
    """
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_app TO CURRENT_USER"))
    async with schema_engine.connect() as connection:
        await connection.begin()
        await connection.execute(_AS_APP)
        yield connection
        await connection.rollback()


@pytest_asyncio.fixture
async def worker_connection(schema_engine: AsyncEngine) -> AsyncIterator[AsyncConnection]:
    """A connection whose transaction runs as ``hunter_worker``, rolled back after.

    The pipeline's own role: everything it writes it writes as this, so a
    statement the scanner issues has to be proven here rather than inferred from
    ``has_table_privilege``.
    """
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_worker TO CURRENT_USER"))
    async with schema_engine.connect() as connection:
        await connection.begin()
        await connection.execute(text("SET LOCAL ROLE hunter_worker"))
        yield connection
        await connection.rollback()


async def _market(connection: AsyncConnection) -> uuid.UUID:
    """A throwaway market to hang a baseline on, written as the caller's role."""
    exchange, market = uuid7(), uuid7()
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')"),
        {"id": exchange, "code": f"probe-{uuid.uuid4().hex[:8]}"},
    )
    await connection.execute(
        text(
            "INSERT INTO markets (id, exchange_id, symbol, market_type) "
            "VALUES (:id, :exchange, :symbol, 'perpetual')"
        ),
        {"id": market, "exchange": exchange, "symbol": f"BTC{uuid.uuid4().hex[:6].upper()}"},
    )
    return market


async def _baseline(connection: AsyncConnection, market: uuid.UUID) -> uuid.UUID:
    window_end = datetime(2026, 9, 5, 11, 59, tzinfo=UTC)
    result = await connection.execute(
        text(
            "INSERT INTO feature_baselines "
            "(id, market_id, feature, feature_version, algo_version, hour_of_day, "
            " window_start, window_end, available_at, median, mad, sample_size, "
            " expected_size, distinct_days, coverage, source, sampling, input_fingerprint) "
            "VALUES (:id, :market, 'volume_relative', 1, 'mad_v1', 11, :window_start, "
            " :window_end, :available_at, :median, :mad, 400, 420, 7, :coverage, 'live', "
            " 'per_minute', :fingerprint) RETURNING id"
        ),
        {
            "id": uuid7(),
            "market": market,
            "window_start": window_end - timedelta(days=7),
            "window_end": window_end,
            "available_at": window_end + timedelta(minutes=2),
            "median": Decimal("1.0000000000"),
            "mad": Decimal("0.2500000000"),
            "coverage": Decimal("0.952381"),
            "fingerprint": uuid.uuid4().hex,
        },
    )
    return result.scalar_one()


async def _partitions_of(connection: AsyncConnection, parent: str) -> list[str]:
    """Every descendant partition of ``parent``, at any nesting depth."""
    result = await connection.execute(
        text(
            "WITH RECURSIVE tree AS ("
            "  SELECT c.oid FROM pg_class c WHERE c.relname = :parent"
            "  UNION ALL"
            "  SELECT i.inhrelid FROM pg_inherits i JOIN tree t ON i.inhparent = t.oid"
            ") SELECT c.relname FROM tree JOIN pg_class c ON c.oid = tree.oid "
            "WHERE c.relispartition ORDER BY c.relname"
        ),
        {"parent": parent},
    )
    return [row[0] for row in result]


async def test_append_only_tables_deny_update_and_delete_to_the_app_role(
    schema_engine: AsyncEngine,
) -> None:
    """Every append-only table *and every partition of one* is INSERT/SELECT only."""
    append_only = _security_tables("APPEND_ONLY_TABLES")

    async with schema_engine.connect() as connection:
        targets: list[str] = []
        for table in append_only:
            targets.append(table)
            targets.extend(await _partitions_of(connection, table))

        offenders: list[str] = []
        for target in targets:
            for privilege in _WRITE_PRIVILEGES:
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_app', :t, :p)"),
                    {"t": target, "p": privilege},
                )
                if granted:
                    offenders.append(f"{target}:{privilege}")

    assert len(targets) > len(append_only), "no partition children were checked"
    assert offenders == [], f"hunter_app can still write append-only relations: {offenders}"


async def test_the_app_role_can_still_insert_and_read_append_only_parents(
    schema_engine: AsyncEngine,
) -> None:
    append_only = _security_tables("APPEND_ONLY_TABLES")
    async with schema_engine.connect() as connection:
        for table in append_only:
            for privilege in ("SELECT", "INSERT"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_app', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                assert granted, f"hunter_app lost {privilege} on {table}"


async def test_deleting_from_an_audit_log_partition_is_denied(
    app_connection: AsyncConnection,
) -> None:
    """The reviewer's probe, verbatim: the child must refuse, not the parent only."""
    with pytest.raises(ProgrammingError, match=_DENIED):
        await app_connection.execute(text("DELETE FROM audit_logs_2026_09"))


async def test_updating_a_global_table_is_denied_to_the_app_role(
    app_connection: AsyncConnection,
) -> None:
    """Global catalogue rows are written by ``hunter_worker`` and by migrations."""
    with pytest.raises(ProgrammingError, match=_DENIED):
        await app_connection.execute(text("UPDATE feature_flags SET enabled = true"))


async def test_read_only_tables_grant_the_app_role_nothing_but_select(
    schema_engine: AsyncEngine,
) -> None:
    read_only = (
        *_security_tables("APP_READ_ONLY_TABLES"),
        *_shadow_tables("SHADOW_APP_READ_ONLY_TABLES"),
        *_analysis_tables("ANALYSIS_APP_READ_ONLY_TABLES"),
        *_paper_tables("PAPER_APP_READ_ONLY_TABLES"),
        # 0008: execution stops being the API's to write (§20.1). The four
        # arrive here rather than in ``ddl/tables.py`` because that list is
        # frozen as of ``0001`` and has to keep describing what ``0001`` did.
        *_paper_roles_2_tables("APP_READ_ONLY_TABLES_0008"),
    )
    assert read_only, "the read-only grant list is empty"

    async with schema_engine.connect() as connection:
        offenders: list[str] = []
        for table in read_only:
            selectable = await connection.scalar(
                text("SELECT has_table_privilege('hunter_app', :t, 'SELECT')"), {"t": table}
            )
            assert selectable, f"hunter_app cannot read {table}"
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_app', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                if granted:
                    offenders.append(f"{table}:{privilege}")
    assert offenders == [], f"hunter_app can write read-only tables: {offenders}"


async def test_no_partition_child_carries_a_grant_for_either_role(
    schema_engine: AsyncEngine,
) -> None:
    """Access goes through the parent; a child must be reachable no other way."""
    async with schema_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relispartition"
            )
        )
        children = [row[0] for row in result]
        assert children, "the schema has no partitions to check"

        offenders: list[str] = []
        for child in children:
            for role in ("hunter_app", "hunter_worker"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    granted = await connection.scalar(
                        text("SELECT has_table_privilege(:r, :t, :p)"),
                        {"r": role, "t": child, "p": privilege},
                    )
                    if granted:
                        offenders.append(f"{role}:{child}:{privilege}")
    assert offenders == [], f"partition children carry direct grants: {offenders[:10]}"


async def test_the_grant_lists_cover_every_table_exactly_once(
    schema_engine: AsyncEngine,
) -> None:
    """The frozen lists and the database describe the same set of tables."""
    # 0008 **moves** four tables from the write class to read-only; the lists are
    # frozen per revision, so the move is expressed here as a subtraction rather
    # than by editing ``0001``'s tuple. Without it the four would be counted
    # twice and this test would read a reclassification as a bug.
    reclassified = set(_paper_roles_2_tables("APP_READ_ONLY_TABLES_0008"))
    write = tuple(
        table for table in _security_tables("APP_WRITE_TABLES") if table not in reclassified
    )
    no_delete = _security_tables("APP_NO_DELETE_TABLES")
    read_only = _security_tables("APP_READ_ONLY_TABLES")
    append_only = _security_tables("APPEND_ONLY_TABLES")

    shadow_read_only = _shadow_tables("SHADOW_APP_READ_ONLY_TABLES")
    analysis_read_only = _analysis_tables("ANALYSIS_APP_READ_ONLY_TABLES")
    paper_read_only = _paper_tables("PAPER_APP_READ_ONLY_TABLES")
    paper_append = _paper_tables("PAPER_APPEND_TABLES")
    paper_no_delete = _paper_tables("PAPER_NO_DELETE_TABLES")
    # T3.1b: ``portfolio_risk_state`` left ``PAPER_NO_DELETE_TABLES`` for a class
    # of its own — the API gets SELECT/INSERT and ``UPDATE (updated_at)``, which
    # is exactly enough to take the wallet lock and not enough to write a value.
    paper_lock_only = _paper_tables("PAPER_LOCK_ONLY_TABLES")
    execution_read_only = _paper_roles_2_tables("APP_READ_ONLY_TABLES_0008")
    replay_read_only = _replay_run_tables("REPLAY_APP_READ_ONLY_TABLES")
    breadth_read_only = _breadth_tables("BREADTH_APP_READ_ONLY_TABLES")
    dispersion_read_only = _dispersion_tables("DISPERSION_APP_READ_ONLY_TABLES")
    meme_read_only = _meme_tables("MEME_APP_READ_ONLY_TABLES")
    meme_lab_read_only = _meme_lab_tables("MEME_LAB_APP_READ_ONLY_TABLES")
    meme_lab_append = _meme_lab_tables("MEME_LAB_APP_APPEND_TABLES")
    meme_lab_decision = _meme_lab_tables("MEME_LAB_APP_DECISION_TABLES")

    classified = (
        list(write)
        + list(no_delete)
        + list(read_only)
        + list(append_only)
        + list(shadow_read_only)
        + list(analysis_read_only)
        + list(paper_read_only)
        + list(paper_append)
        + list(paper_no_delete)
        + list(paper_lock_only)
        + list(execution_read_only)
        + list(replay_read_only)
        + list(breadth_read_only)
        + list(dispersion_read_only)
        + list(meme_read_only)
        + list(meme_lab_read_only)
        + list(meme_lab_append)
        + list(meme_lab_decision)
    )
    assert len(classified) == len(set(classified)), "a table is in two grant classes"

    async with schema_engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') "
                "AND NOT c.relispartition AND c.relname <> 'alembic_version'"
            )
        )
        actual = {row[0] for row in result}
    assert set(classified) == actual


async def test_the_app_role_cannot_delete_an_organization_or_a_user(
    schema_engine: AsyncEngine,
) -> None:
    """Identity rows are created and edited by the API, never removed by it.

    ``organizations`` and ``users`` are the one grant class between "full DML"
    and "read only": ``SELECT``/``INSERT``/``UPDATE``. A ``DELETE`` on an
    organization cascades through every portfolio, order, position and fill the
    tenant owns, so it is not a privilege a request handler — or a bug in one —
    should be able to reach. Removal is an operator/``hunter_worker`` operation.
    """
    no_delete = _security_tables("APP_NO_DELETE_TABLES")
    assert set(no_delete) == {"organizations", "users"}

    async with schema_engine.connect() as connection:
        for table in no_delete:
            for privilege in ("SELECT", "INSERT", "UPDATE"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_app', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                assert granted, f"hunter_app lost {privilege} on {table}"
            deletable = await connection.scalar(
                text("SELECT has_table_privilege('hunter_app', :t, 'DELETE')"), {"t": table}
            )
            assert not deletable, f"hunter_app can still DELETE {table}"


async def test_deleting_an_organization_is_denied_to_the_app_role(
    app_connection: AsyncConnection,
) -> None:
    """The reviewer's probe: the grant must refuse before RLS is even consulted."""
    with pytest.raises(ProgrammingError, match=_DENIED):
        await app_connection.execute(text("DELETE FROM organizations"))


async def test_the_worker_role_owns_the_organization_lifecycle(
    schema_engine: AsyncEngine,
) -> None:
    """Someone has to be able to remove a tenant; it is the operator side.

    ``hunter_worker`` has ``BYPASSRLS``, so it is the role a retention or
    account-closure job runs as. It gets ``DELETE`` and nothing else on these two
    tables — it never creates or edits a person or an organization, which stays
    the API's job.
    """
    lifecycle = _security_tables("WORKER_DELETE_TABLES")
    assert set(lifecycle) == {"organizations", "users"}

    async with schema_engine.connect() as connection:
        for table in lifecycle:
            deletable = await connection.scalar(
                text("SELECT has_table_privilege('hunter_worker', :t, 'DELETE')"), {"t": table}
            )
            assert deletable, f"hunter_worker cannot DELETE {table}"
            for privilege in ("INSERT", "UPDATE"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_worker', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                assert not granted, f"hunter_worker can {privilege} {table}"


async def test_the_worker_holds_update_on_a_baseline_only_to_lock_the_row(
    schema_engine: AsyncEngine,
) -> None:
    """``feature_baselines`` is the one table whose ``UPDATE`` grant is a lock.

    ``0003`` withheld ``UPDATE`` and called it the second of "two independent
    locks on the same door". It was not: PostgreSQL demands the ``UPDATE``
    privilege for *any* row lock (``ACL_SELECT_FOR_UPDATE`` is ``ACL_UPDATE``),
    so withholding it did not protect the archive — the
    ``feature_baselines_immutable`` trigger already refuses every ``UPDATE`` for
    every role, the owner included, which no ``REVOKE`` can do — it only made
    the ``FOR SHARE`` of DATABASE.md §17.2 impossible, which is BUG-1 of T2.5.
    ``0005`` grants it. What the archive is worth is asserted where it now
    lives: ``test_schema_analysis.py``, as the worker role, against the trigger.
    """
    append_tables = _analysis_tables("ANALYSIS_WORKER_APPEND_TABLES")
    assert set(append_tables) == {"feature_baselines"}
    locked = _lock_tables("BASELINE_LOCK_TABLES_0005")
    assert set(locked) <= set(append_tables), "0005 grants outside 0003's class"

    async with schema_engine.connect() as connection:
        for table in append_tables:
            expected: set[str] = {"SELECT", "INSERT", "DELETE"}
            if table in locked:
                expected.add("UPDATE")
            held: set[str] = set()
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_worker', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                if granted:
                    held.add(privilege)
            assert held == expected, (table, held)


async def test_the_worker_can_actually_take_for_share_on_a_baseline_row(
    worker_connection: AsyncConnection,
) -> None:
    """Run as the role, not asked of ``has_table_privilege`` — this is BUG-1.

    The scanner's probe (``hunter_scanner_worker.writers.probe_baseline_lock``)
    is this statement, and against ``0003`` it failed with *permission denied*,
    aborting the transaction it ran in. Asking the catalogue whether ``UPDATE``
    is granted would not have caught it before the grant existed and would not
    prove it now: what §17.2 needs is that this exact statement runs, on a real
    row, as ``hunter_worker``.
    """
    market = await _market(worker_connection)
    baseline_id = await _baseline(worker_connection, market)

    locked = await worker_connection.scalar(
        text("SELECT id FROM feature_baselines WHERE id = ANY(:ids) FOR SHARE"),
        {"ids": [str(baseline_id)]},
    )
    assert locked == baseline_id

    empty = await worker_connection.execute(
        text("SELECT id FROM feature_baselines WHERE id = ANY(:ids) FOR SHARE"), {"ids": []}
    )
    assert empty.fetchall() == [], "the startup probe must run without raising"


async def test_the_app_role_cannot_write_a_baseline_or_the_outbox(
    schema_engine: AsyncEngine,
) -> None:
    """Everything the M2 pipeline writes is written by a worker. The API reads a
    baseline to explain a score and reads the outbox to report queue depth; a
    request handler that could write either could rewrite the past or publish an
    event nobody produced."""
    read_only = _analysis_tables("ANALYSIS_APP_READ_ONLY_TABLES")
    async with schema_engine.connect() as connection:
        for table in read_only:
            selectable = await connection.scalar(
                text("SELECT has_table_privilege('hunter_app', :t, 'SELECT')"), {"t": table}
            )
            assert selectable, f"hunter_app cannot read {table}"
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                granted = await connection.scalar(
                    text("SELECT has_table_privilege('hunter_app', :t, :p)"),
                    {"t": table, "p": privilege},
                )
                assert not granted, f"hunter_app can {privilege} {table}"


async def test_the_worker_can_actually_insert_into_the_outbox_sequence_and_all(
    schema_engine: AsyncEngine,
) -> None:
    """Inserted as the role, not asked of ``has_table_privilege``.

    ``outbox_events.id`` is ``BIGSERIAL``, and a table grant alone passes every
    privilege check and then fails the ``INSERT`` with "permission denied for
    sequence" — the trap ``shadow_outbox`` paid for in ``0002``. Only a real
    write proves the sequence grant went out with the table grant.
    """
    async with schema_engine.begin() as connection:
        await connection.execute(text("GRANT hunter_worker TO CURRENT_USER"))
    async with schema_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(text("SET LOCAL ROLE hunter_worker"))
            written = await connection.scalar(
                text(
                    "INSERT INTO outbox_events (event_id, stream) "
                    "VALUES (gen_random_uuid(), 'opportunities.updated') RETURNING id"
                )
            )
            assert written is not None
        finally:
            await transaction.rollback()


async def test_the_app_role_reads_the_equity_curve_and_never_writes_it(
    app_connection: AsyncConnection,
) -> None:
    """``0007_paper_roles``: the curve is evidence, and the API only reads it.

    ``hunter_core.risk.curve`` reads this table twice — to anchor the trading day
    and to prove a recovery before a resume — and ``portfolio_risk_state_guard``
    measures every rising peak against ``max(equity)`` in it (§18.7). RLS keeps
    one tenant out of another's curve; it does nothing about a request handler
    writing a number into its *own* tenant's curve, which is exactly how a
    recovery that never happened becomes the evidence for an unlatch (security
    review of ``0006``, finding 5). Asserted as the role, not asked of the
    catalogue.
    """
    await app_connection.execute(text("SELECT count(*) FROM portfolio_equity_snapshots"))
    for statement in (
        "INSERT INTO portfolio_equity_snapshots (organization_id, portfolio_id, resolution, ts, "
        "cash, equity, exposure_notional, unrealized_pnl, realized_pnl_cum, peak_equity) "
        "VALUES (gen_random_uuid(), gen_random_uuid(), '1m', now(), 0, 0, 0, 0, 0, 0)",
        "UPDATE portfolio_equity_snapshots SET equity = 20000 WHERE false",
        "DELETE FROM portfolio_equity_snapshots WHERE false",
    ):
        with pytest.raises(ProgrammingError, match=_DENIED):
            await app_connection.execute(text(statement))
        await app_connection.rollback()
        await app_connection.begin()
        await app_connection.execute(_AS_APP)


async def test_the_app_role_files_a_proposal_and_never_decides_one(
    app_connection: AsyncConnection,
) -> None:
    """``SELECT``/``INSERT`` stay; ``UPDATE``/``DELETE`` go (§19.2).

    Deciding is admission's job and admission runs as the engine — the ``fifo_v1``
    counter lives in ``portfolio_risk_state``, which the API may not write. With
    ``UPDATE`` a handler could turn a rejected proposal into an approved one, or
    widen a reservation after the decision that sized it.
    """
    await app_connection.execute(text("SELECT count(*) FROM trade_proposals"))
    for statement in (
        "UPDATE trade_proposals SET status = 'approved' WHERE false",
        "DELETE FROM trade_proposals WHERE false",
    ):
        with pytest.raises(ProgrammingError, match=_DENIED):
            await app_connection.execute(text(statement))
        await app_connection.rollback()
        await app_connection.begin()
        await app_connection.execute(_AS_APP)


async def test_the_engine_moves_the_kill_switch_column_and_nothing_else(
    worker_connection: AsyncConnection,
) -> None:
    """The engine's grant on ``portfolios``/``organizations`` is a column, not a table.

    It writes the latch the workers read (with its reason and ``updated_at``) so
    one evaluation of the kill switch fits in one transaction (T3.6, finding 1),
    and it locks the organization row on the way in (``FOR SHARE``, which
    PostgreSQL charges ``ACL_UPDATE`` for — T3.12, blocking A). It may not rename
    a wallet, archive it, flip ``is_arena``, or block an organization: those are
    the API's, and the last one is an OWNER's.
    """
    await worker_connection.execute(
        text("UPDATE portfolios SET kill_switch_state = 'ACTIVE' WHERE false")
    )
    await worker_connection.execute(text("SELECT id FROM organizations WHERE false FOR SHARE"))
    for statement in (
        "UPDATE portfolios SET name = 'renamed' WHERE false",
        "UPDATE portfolios SET is_arena = true WHERE false",
        "UPDATE organizations SET kill_switch_state = 'EMERGENCY' WHERE false",
    ):
        with pytest.raises(ProgrammingError, match=_DENIED):
            await worker_connection.execute(text(statement))
        await worker_connection.rollback()
        await worker_connection.begin()
        await worker_connection.execute(text("SET LOCAL ROLE hunter_worker"))


async def test_the_app_role_reads_execution_and_writes_none_of_it(
    app_connection: AsyncConnection,
) -> None:
    """``0008_paper_roles_2``, D1: the API lists execution and forges nothing.

    The four statements below are the security review's, verbatim in intent:
    each one was **accepted** against ``0007``, as this role, inside the correct
    organization, where RLS says yes. That is the point — RLS keeps one tenant
    out of another's rows and says nothing about a request handler (or an
    injection into one) rewriting its own tenant's execution history.

    It matters more than it looks, because ``portfolio_equity_snapshots`` is
    *derived* from these four: with ``0007`` alone, closing the curve to the API
    only moved the forgery one table down — fabricate the fill and the engine
    computes, signs and stores the forged point itself, as the role everything
    downstream trusts.

    Proved as the role, not asked of ``has_table_privilege``: the catalogue is
    checked by ``test_migrations.py``; what a request handler can actually run
    is checked here.
    """
    for table in _paper_roles_2_tables("APP_READ_ONLY_TABLES_0008"):
        await app_connection.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608

    for statement in (
        # a fabricated fill — the source the curve is derived from
        "INSERT INTO fills (id, order_id, organization_id, portfolio_id, ts, qty, price, "
        "fee, liquidity, execution_key) VALUES (gen_random_uuid(), gen_random_uuid(), "
        "gen_random_uuid(), gen_random_uuid(), now(), 1, 1, 0, 'taker', 'forged')",
        "UPDATE positions SET qty = qty * 1000 WHERE false",
        "DELETE FROM trades WHERE false",
        "UPDATE orders SET status = 'filled' WHERE false",
        "INSERT INTO positions (id, organization_id, portfolio_id, market_id, direction, "
        "qty, avg_entry_price, notional) VALUES (gen_random_uuid(), gen_random_uuid(), "
        "gen_random_uuid(), gen_random_uuid(), 'long', 1, 1, 1)",
    ):
        with pytest.raises(ProgrammingError, match=_DENIED):
            await app_connection.execute(text(statement))
        await app_connection.rollback()
        await app_connection.begin()
        await app_connection.execute(_AS_APP)


async def test_the_engine_still_writes_every_execution_table(
    worker_connection: AsyncConnection,
) -> None:
    """D1 narrows the API and nothing else: execution is the engine's, whole.

    The failure this guards against is over-correction — a ``REVOKE`` written on
    the wrong side leaves T3.5 with no role able to record a fill, which is the
    wall ``0007`` hit on ``portfolios`` (§19.2, item 1b) and the reason that one
    was measured rather than assumed.
    """
    for table in _paper_roles_2_tables("APP_READ_ONLY_TABLES_0008"):
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            granted = await worker_connection.scalar(
                text("SELECT has_table_privilege('hunter_worker', :t, :p)"),
                {"t": table, "p": privilege},
            )
            assert granted, f"the engine lost {privilege} on {table}"
    # and it runs, not merely reports: an UPDATE that matches nothing still goes
    # through the privilege check the API now fails.
    await worker_connection.execute(text("UPDATE positions SET qty = qty WHERE false"))
    await worker_connection.execute(text("DELETE FROM trades WHERE false"))


# --------------------------------------------------------------------------
# 0010_strategy_purpose: the wallet label, written by nobody but the
# activation/migration connection — DATABASE.md section 22
# --------------------------------------------------------------------------


async def test_both_roles_read_purpose(schema_engine: AsyncEngine) -> None:
    async with schema_engine.connect() as connection:
        for role in ("hunter_app", "hunter_worker"):
            readable = await connection.scalar(
                text("SELECT has_column_privilege(:r, 'strategy_versions', 'purpose', 'SELECT')"),
                {"r": role},
            )
            assert readable, f"{role} lost SELECT on strategy_versions.purpose"


async def _set_as_worker(connection: AsyncConnection) -> None:
    """Re-enter the role after a rollback poisons the transaction and drops
    ``SET LOCAL``'s scope with it."""
    await connection.begin()
    await connection.execute(text("SET LOCAL ROLE hunter_worker"))


async def test_the_worker_cannot_name_purpose_in_an_insert(
    worker_connection: AsyncConnection,
) -> None:
    """Measured, not assumed: a column-level ``REVOKE`` alone cannot narrow the
    table-level ``INSERT``/``UPDATE`` ``0001`` already gave ``hunter_worker`` —
    Postgres checks a column access as the *union* of the table and column ACL.
    ``0010`` takes the table-level grant back and re-grants every column but
    ``purpose``, so this proves it as the role, not through
    ``has_column_privilege`` alone (which the module docstring's own probe
    against a real Postgres already found insufficient to trust blindly).
    """
    strategy_id, version_id = uuid7(), uuid7()
    await worker_connection.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)"),
        {"id": strategy_id, "key": f"purpose-priv-{uuid.uuid4().hex[:8]}"},
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, version, purpose) "
                "VALUES (:id, :strategy, 'v1', 'paper')"
            ),
            {"id": version_id, "strategy": strategy_id},
        )
    await worker_connection.rollback()


async def _insert_strategy_version_as_owner(connection: AsyncConnection, *, key: str) -> uuid.UUID:
    """Create the fixture row with the connecting role's own privilege — the
    container owner, exactly the connection ``activate_strategy_version.py``,
    ``seed.py`` and ``paper_line.py`` actually use (T3.15c: ``0011`` revokes
    ``INSERT`` on ``strategy_versions`` from ``hunter_worker`` outright, so a
    test that needs a row to test *other* privileges against can no longer
    create it as the worker).

    ``RESET ROLE`` returns to the session (owner) role for these two
    statements; the caller is left back in ``hunter_worker`` (the shape
    :func:`_set_as_worker` already re-enters after a rollback). Nothing here
    is committed outside the test's own transaction, which the ``worker_connection``
    fixture rolls back when the test ends.
    """
    strategy_id, version_id = uuid7(), uuid7()
    await connection.execute(text("RESET ROLE"))
    await connection.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)"),
        {"id": strategy_id, "key": key},
    )
    await connection.execute(
        text(
            "INSERT INTO strategy_versions (id, strategy_id, version) VALUES (:id, :strategy, 'v1')"
        ),
        {"id": version_id, "strategy": strategy_id},
    )
    await connection.execute(text("SET LOCAL ROLE hunter_worker"))
    return version_id


async def test_the_worker_cannot_insert_a_strategy_version_at_all_since_0011(
    worker_connection: AsyncConnection,
) -> None:
    """``0010`` denied naming ``purpose`` in an ``INSERT``; ``0011`` goes
    further and revokes ``INSERT`` outright, because nothing that runs as
    ``hunter_worker`` ever inserts here — ``seed.py``, ``paper_line.py`` and
    ``activate_strategy_version.py`` all use the owner connection. Omitting
    ``purpose`` (0010's own finding) no longer saves an ``INSERT`` that names
    any other column either."""
    strategy_id = uuid7()
    await worker_connection.execute(
        text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)"),
        {"id": strategy_id, "key": f"purpose-priv-noinsert-{uuid.uuid4().hex[:8]}"},
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, version) "
                "VALUES (:id, :strategy, 'v1')"
            ),
            {"id": uuid7(), "strategy": strategy_id},
        )
    await worker_connection.rollback()


async def test_the_worker_cannot_update_purpose_but_keeps_changelog(
    worker_connection: AsyncConnection,
) -> None:
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"purpose-priv-update-{uuid.uuid4().hex[:8]}"
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text("UPDATE strategy_versions SET purpose = 'paper' WHERE id = :id"),
            {"id": version_id},
        )
    await worker_connection.rollback()
    # The rollback above discarded the row the owner role just inserted, same
    # as it always discarded a worker-inserted one before ``0011`` — a fresh
    # row, again created as the owner, proves the *other* columns' privilege
    # survived the narrowing: ``changelog`` still writes.
    await _set_as_worker(worker_connection)
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"purpose-priv-survives-{uuid.uuid4().hex[:8]}"
    )
    await worker_connection.execute(
        text("UPDATE strategy_versions SET changelog = 'still writable' WHERE id = :id"),
        {"id": version_id},
    )


# --------------------------------------------------------------------------
# 0011_strategy_activation_owner: hunter_worker cannot activate, deprecate or
# delete a version — DATABASE.md section 23
# --------------------------------------------------------------------------


async def test_the_worker_cannot_activate_a_draft(
    worker_connection: AsyncConnection,
) -> None:
    """The gap ``0010`` left open: the freeze trigger only fires on an already-
    activated row, so before ``0011`` the table-level ``UPDATE`` ``0001`` gave
    ``hunter_worker`` still let it flip a ``draft`` row (``activated_at IS
    NULL`` — exactly the shape ``--paper-line`` derives) to ``active`` itself,
    with no line in ``system_events`` and no decision behind it."""
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"activation-priv-{uuid.uuid4().hex[:8]}"
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text(
                "UPDATE strategy_versions SET status = 'active', activated_at = now() "
                "WHERE id = :id"
            ),
            {"id": version_id},
        )
    await worker_connection.rollback()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("code_ref", "'hunter_core.strategies.tampered'"),
        ("parameters_schema", "'{}'::jsonb"),
        ("default_parameters", "'{}'::jsonb"),
        ("params_format", "2"),
        ("deprecated_at", "now()"),
    ],
)
async def test_the_worker_cannot_touch_the_other_activation_columns_either(
    worker_connection: AsyncConnection, column: str, value: str
) -> None:
    """The rest of ``REVOKED_LIFECYCLE_COLUMNS`` (``ddl.strategy_activation_owner``):
    the version's identity and the deprecation cycle, revoked alongside
    ``status``/``activated_at`` for the same reason — nothing that runs as
    ``hunter_worker`` writes any of them."""
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"activation-priv-{column}-{uuid.uuid4().hex[:8]}"
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text(f"UPDATE strategy_versions SET {column} = {value} WHERE id = :id"),  # noqa: S608
            {"id": version_id},
        )
    await worker_connection.rollback()


async def test_the_worker_cannot_delete_a_strategy_version(
    worker_connection: AsyncConnection,
) -> None:
    """The other half of the gap ``0011`` closes: a ``draft`` row's ``DELETE``
    was never guarded by the freeze trigger either (``BEFORE DELETE ... WHEN
    (OLD.activated_at IS NOT NULL)``)."""
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"activation-priv-delete-{uuid.uuid4().hex[:8]}"
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text("DELETE FROM strategy_versions WHERE id = :id"), {"id": version_id}
        )
    await worker_connection.rollback()


async def test_the_worker_still_reads_strategy_versions(
    worker_connection: AsyncConnection,
) -> None:
    """``SELECT`` is the one privilege ``0011`` does not touch — every real
    reader (``catalogue.py``, ``replay/load.py``, ``metrics.py``,
    ``bridge_repo.py``) still works."""
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"activation-priv-select-{uuid.uuid4().hex[:8]}"
    )
    status = await worker_connection.scalar(
        text("SELECT status::text FROM strategy_versions WHERE id = :id"), {"id": version_id}
    )
    assert status == "draft"


async def test_the_worker_has_no_table_level_privilege_left_but_select(
    schema_engine: AsyncEngine,
) -> None:
    """The measured end state of §23: ``SELECT`` only, at the table level."""
    async with schema_engine.connect() as connection:
        held: set[str] = set()
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            granted = await connection.scalar(
                text("SELECT has_table_privilege('hunter_worker', 'strategy_versions', :p)"),
                {"p": privilege},
            )
            if granted:
                held.add(privilege)
    assert held == {"SELECT"}, held


def test_0011_revoked_and_remaining_columns_partition_0010s_grant() -> None:
    """The two lists in ``ddl.strategy_activation_owner`` never drift apart:
    every column ``0010`` granted ``hunter_worker`` is in exactly one of
    "revoked by 0011" or "still writable"."""
    owner_ddl = migration_ddl("strategy_activation_owner")
    purpose_ddl = migration_ddl("strategy_purpose")
    revoked = set(owner_ddl.REVOKED_LIFECYCLE_COLUMNS)
    remaining = set(owner_ddl.REMAINING_WORKER_UPDATE_COLUMNS)
    granted_by_0010 = set(purpose_ddl.WORKER_COLUMNS_EXCEPT_PURPOSE)
    assert revoked | remaining == granted_by_0010
    assert revoked & remaining == set()


# --------------------------------------------------------------------------
# 0012_replication: the promising marker and a sibling's lineage, written by
# nobody but the owner connection — DATABASE.md section 24
# --------------------------------------------------------------------------

_REPLICATION_COLUMNS = (
    "promising_at",
    "promising_by",
    "replication_parent_id",
    "replication_index",
)


async def test_both_roles_read_the_replication_columns(schema_engine: AsyncEngine) -> None:
    """``0012`` adds no ``GRANT``: the table-level ``SELECT`` both roles have had
    since ``0001`` covers a column added later, by construction."""
    async with schema_engine.connect() as connection:
        for role in ("hunter_app", "hunter_worker"):
            for column in _REPLICATION_COLUMNS:
                readable = await connection.scalar(
                    text("SELECT has_column_privilege(:r, 'strategy_versions', :c, 'SELECT')"),
                    {"r": role, "c": column},
                )
                assert readable, f"{role} cannot read strategy_versions.{column}"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("promising_at", "now()"),
        ("promising_by", "'scoreboard:validada'"),
        ("replication_parent_id", "id"),
        ("replication_index", "1"),
        # 0017_eligibility_policy rides along: same closure, one revision later.
        ("eligibility_policy", "'{}'::jsonb"),
    ],
)
async def test_the_worker_cannot_write_any_of_the_replication_columns(
    worker_connection: AsyncConnection, column: str, value: str
) -> None:
    """The assertion ``0012`` makes instead of a ``REVOKE`` — measured as the role.

    ``0010`` took back ``hunter_worker``'s table-level ``INSERT``/``UPDATE`` on
    ``strategy_versions`` and re-granted twelve named columns; ``0011`` revoked
    ``INSERT`` outright and ``UPDATE`` on seven of them. A column added *after*
    both is therefore reachable by neither: there is no table-level write left
    for it to inherit and no column grant naming it. Writing a no-op ``REVOKE``
    in ``0012`` would have looked like the guarantee this test actually is
    (§15.6's ``ALTER DEFAULT PRIVILEGES`` lesson).

    The promising marker is written by
    ``hunter_strategy_worker.replication.mark_promising`` on the owner
    connection, exactly like ``purpose`` (§22.3, §23.2).
    """
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"replication-priv-{column}-{uuid.uuid4().hex[:8]}"
    )
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(
            text(f"UPDATE strategy_versions SET {column} = {value} WHERE id = :id"),  # noqa: S608
            {"id": version_id},
        )
    await worker_connection.rollback()


async def test_the_owner_connection_writes_the_promising_marker(
    schema_engine: AsyncEngine,
) -> None:
    """The other side of the revocation: the connection
    ``infra/scripts/replicate_strategy_version.py`` actually uses can write it.

    A revocation written against the wrong role would leave the protocol with
    nobody able to record that a version became promising — the wall ``0007``
    hit on ``portfolios`` (§19.2, item 1b), one table over.
    """
    strategy_id, version_id = uuid7(), uuid7()
    async with schema_engine.connect() as connection:
        await connection.begin()
        await connection.execute(
            text("INSERT INTO strategies (id, key, name) VALUES (:id, :key, :key)"),
            {"id": strategy_id, "key": f"replication-owner-{uuid.uuid4().hex[:8]}"},
        )
        await connection.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, version, status, activated_at) "
                "VALUES (:id, :strategy, 'v1', 'active', now())"
            ),
            {"id": version_id, "strategy": strategy_id},
        )
        await connection.execute(
            text(
                "UPDATE strategy_versions SET promising_at = now(), "
                "promising_by = 'scoreboard:validada' WHERE id = :id"
            ),
            {"id": version_id},
        )
        stored = await connection.scalar(
            text("SELECT promising_by FROM strategy_versions WHERE id = :id"), {"id": version_id}
        )
        assert stored == "scoreboard:validada"
        await connection.rollback()


# --------------------------------------------------------------------------
# 0013_replay_runs: the worker appends a receipt and can never edit it, the
# API only reads it — DATABASE.md section 25.4
# --------------------------------------------------------------------------

_RECEIPT_INSERT = (
    "INSERT INTO replay_runs (id, run_id, cohort, strategy_version_id, window_from, window_to, "
    "markets, started_at, finished_at, bars_evaluated, signals, outcomes_resolved, "
    "outcomes_open, seconds, decision_lag_s, workers) "
    "VALUES (:id, :run, :cohort, :version, :start, :end, "
    "CAST(:markets AS text[]), now(), now(), 12, 1, 1, 0, CAST('5.000' AS numeric), 2, 1)"
)


def _receipt_params(version_id: uuid.UUID) -> dict[str, object]:
    run_id = uuid7()
    return {
        "id": uuid7(),
        "run": run_id,
        "cohort": f"replay:{run_id}",
        "version": version_id,
        "start": datetime(2026, 8, 8, tzinfo=UTC),
        "end": datetime(2026, 8, 11, tzinfo=UTC),
        "markets": ["binance:BTCUSDT"],
    }


async def test_the_worker_appends_a_replay_receipt_and_can_never_edit_it(
    worker_connection: AsyncConnection,
) -> None:
    """Measured as the role, not asked of the catalogue.

    The replay engine is the only writer of ``replay_runs``
    (``hunter_strategy_worker.replay.ledger``), and a receipt its own writer may
    edit is not a receipt — the argument ``audit_logs``,
    ``kill_switch_transitions`` and ``risk_events`` have carried since ``0001``
    (§1.2). It is also what decided the shape of the table: the alternative the
    brief weighed (one row per run, accumulated by ``UPDATE``) would have needed
    exactly the privilege this test proves is absent.
    """
    version_id = await _insert_strategy_version_as_owner(
        worker_connection, key=f"replay-priv-{uuid.uuid4().hex[:8]}"
    )
    await worker_connection.execute(text(_RECEIPT_INSERT), _receipt_params(version_id))
    assert await worker_connection.scalar(text("SELECT count(*) FROM replay_runs")) == 1

    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(text("UPDATE replay_runs SET bars_evaluated = 99"))
    await worker_connection.rollback()
    await _set_as_worker(worker_connection)
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(text("DELETE FROM replay_runs"))
    await worker_connection.rollback()


async def test_the_app_role_reads_a_replay_receipt_and_writes_none_of_it(
    app_connection: AsyncConnection,
) -> None:
    """The scoreboard reads; it never writes. The same shape ``fx_observations``
    and ``market_betas`` have (§18.9), for the reason the equity curve got in
    ``0007``: a number a request handler can write is not evidence.
    """
    assert await app_connection.scalar(text("SELECT count(*) FROM replay_runs")) is not None
    with pytest.raises(ProgrammingError, match=_DENIED):
        await app_connection.execute(text(_RECEIPT_INSERT), _receipt_params(uuid7()))
    await app_connection.rollback()


async def test_replay_runs_is_global_and_carries_no_tenant_column(
    schema_engine: AsyncEngine,
) -> None:
    """Research is global (§1.1), so there is no ``organization_id`` and no RLS
    policy to isolate — the statement ``0002`` and ``0003`` already make about
    ``shadow_episodes`` and ``feature_baselines``.

    Asserted rather than assumed, because "no policy is needed" and "a policy
    nobody wrote" look identical from outside: a tenant column appearing here
    later would mean the table needs RLS, and this is what would notice.
    """
    async with schema_engine.connect() as connection:
        tenant_column = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'replay_runs' AND column_name = 'organization_id'"
            )
        )
        row = (
            await connection.execute(
                text(
                    "SELECT c.relrowsecurity, count(p.polname) FROM pg_class c "
                    "LEFT JOIN pg_policy p ON p.polrelid = c.oid "
                    "WHERE c.relname = 'replay_runs' GROUP BY c.relrowsecurity"
                )
            )
        ).one()
    assert tenant_column == 0
    assert row[0] is False
    assert row[1] == 0


# --------------------------------------------------------------------------
# 0019_market_breadth: the scanner appends a reading and can never edit it, the
# API only reads it, and the runtime login reaches neither without SET ROLE —
# DATABASE.md section 31
# --------------------------------------------------------------------------

_READING_INSERT = (
    "INSERT INTO market_breadth (id, exchange_id, end_time, window_minutes, breadth_version, "
    "universe_size, covered, falling, value, coverage, usable, reason, inputs) "
    "VALUES (:id, :exchange, :end_time, 5, 'breadth_v1', 200, 194, 188, "
    "CAST(:value AS numeric), CAST(:coverage AS numeric), true, NULL, '{}'::jsonb)"
)
"""The storm minute of 2026-09-09 22:08Z, which is the row the whole revision
exists to be able to hold (``.claude/state/notes-D-P9.md`` §4)."""


def _reading_params(exchange_id: uuid.UUID, *, minute: int = 8) -> dict[str, object]:
    return {
        "id": uuid7(),
        "exchange": exchange_id,
        "end_time": datetime(2026, 9, 9, 22, minute, tzinfo=UTC),
        "value": Decimal("0.969072"),
        "coverage": Decimal("0.970000"),
    }


async def _exchange(connection: AsyncConnection) -> uuid.UUID:
    """A throwaway venue for the reading to point at, written as the caller."""
    exchange_id = uuid7()
    await connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')"),
        {"id": exchange_id, "code": f"breadth-{uuid.uuid4().hex[:8]}"},
    )
    return exchange_id


async def test_the_worker_appends_a_breadth_reading_and_can_never_edit_it(
    worker_connection: AsyncConnection,
) -> None:
    """Measured as the role, not asked of the catalogue.

    The scanner's producer is the only writer of ``market_breadth``
    (``hunter_scanner_worker.breadth_repo.write_readings``), and this is what
    makes the series immutable: ``0019`` installs no trigger because there is no
    legal ``UPDATE`` for one to police — unlike ``market_betas``, which needed
    one because ``superseded_at`` is a legal edit (§18.6). Withholding
    ``UPDATE``/``DELETE`` from the writer itself is the whole mechanism, so it is
    the thing that has to be proved.

    It is also what decided the shape of the table: a minute recomputed after a
    candle backfill is a new ``breadth_version`` — a different row by the unique
    key — precisely because rewriting the old one is not a privilege anybody
    holds. A reading a live decision was gated by may never change afterwards.
    """
    exchange_id = await _exchange(worker_connection)
    await worker_connection.execute(text(_READING_INSERT), _reading_params(exchange_id))
    assert (
        await worker_connection.scalar(
            text("SELECT count(*) FROM market_breadth WHERE exchange_id = :id"),
            {"id": exchange_id},
        )
        == 1
    )

    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(text("UPDATE market_breadth SET falling = 0"))
    await worker_connection.rollback()
    await _set_as_worker(worker_connection)
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(text("DELETE FROM market_breadth"))
    await worker_connection.rollback()


async def test_the_app_role_reads_a_breadth_reading_and_writes_none_of_it(
    app_connection: AsyncConnection,
) -> None:
    """A dashboard may show what the universe was doing; it never produces a
    reading. The ``replay_runs``/``fx_observations`` shape (§18.9): a number a
    request handler can write is not evidence.

    The ``exchange_id`` here points at nothing on purpose — the ``INSERT``
    privilege is checked before the foreign key, so a denial that arrives is a
    denial about the table and not about the row.
    """
    assert await app_connection.scalar(text("SELECT count(*) FROM market_breadth")) is not None
    with pytest.raises(ProgrammingError, match=_DENIED):
        await app_connection.execute(text(_READING_INSERT), _reading_params(uuid7()))
    await app_connection.rollback()


async def test_the_app_role_holds_only_select_on_market_breadth(
    schema_engine: AsyncEngine,
) -> None:
    """``UPDATE`` and ``DELETE`` are absent from the catalogue too, not merely
    unreachable through a statement this file happened to write.

    ``hunter_app`` is the role a bug in a request handler runs as, and "the API
    never issues that statement" is a property of today's code; this is a
    property of the database.
    """
    async with schema_engine.connect() as connection:
        held = {
            privilege
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
            if await connection.scalar(
                text("SELECT has_table_privilege('hunter_app', 'market_breadth', :p)"),
                {"p": privilege},
            )
        }
    assert held == {"SELECT"}


async def test_the_worker_role_holds_only_select_and_insert_on_market_breadth(
    schema_engine: AsyncEngine,
) -> None:
    """Append-only for the producer, asserted as a set so a later revision that
    hands out ``UPDATE`` for "just a backfill" fails here instead of in a
    post-mortem about a number that changed under a decision.
    """
    async with schema_engine.connect() as connection:
        held = {
            privilege
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
            if await connection.scalar(
                text("SELECT has_table_privilege('hunter_worker', 'market_breadth', :p)"),
                {"p": privilege},
            )
        }
    assert held == {"SELECT", "INSERT"}


async def test_the_runtime_login_reaches_market_breadth_only_through_set_role(
    schema_engine: AsyncEngine,
) -> None:
    """``hunter_runtime`` is the login every container actually uses (§27), and
    ``0019`` grants it nothing directly — deliberately, because that is what
    turns a forgotten ``SET LOCAL ROLE`` into a loud failure instead of a silent
    escalation.

    Both halves are asserted: it holds no privilege of its own on the table
    (``has_table_privilege`` honours ``NOINHERIT``, so this is the privilege it
    has *without* ``SET ROLE``), and it is a member of both application roles, so
    ``SET ROLE`` is a door that exists. Only one of the two would be
    indistinguishable from a role that was simply forgotten.
    """
    async with schema_engine.connect() as connection:
        reachable = {
            privilege
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
            if await connection.scalar(
                text("SELECT has_table_privilege('hunter_runtime', 'market_breadth', :p)"),
                {"p": privilege},
            )
        }
        memberships = {
            role: await connection.scalar(
                text("SELECT pg_has_role('hunter_runtime', :role, 'MEMBER')"), {"role": role}
            )
            for role in ("hunter_app", "hunter_worker")
        }
        inherited = {
            role: await connection.scalar(
                text("SELECT pg_has_role('hunter_runtime', :role, 'USAGE')"), {"role": role}
            )
            for role in ("hunter_app", "hunter_worker")
        }
    assert reachable == set(), "hunter_runtime must reach market_breadth only via SET ROLE"
    assert memberships == {"hunter_app": True, "hunter_worker": True}
    assert inherited == {"hunter_app": False, "hunter_worker": False}, "NOINHERIT (0015, §27.1)"


async def test_market_breadth_is_global_and_carries_no_tenant_column(
    schema_engine: AsyncEngine,
) -> None:
    """The universe belongs to the exchange, not to an organization (§1.1), so
    there is no ``organization_id`` and no RLS policy to isolate.

    Asserted rather than assumed, for ``replay_runs``' reason: "no policy is
    needed" and "a policy nobody wrote" look identical from outside. A tenant
    column appearing here later would mean the table needs RLS forced and a
    ``tenant_isolation`` policy, and this is what would notice.
    """
    async with schema_engine.connect() as connection:
        tenant_column = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'market_breadth' AND column_name = 'organization_id'"
            )
        )
        row = (
            await connection.execute(
                text(
                    "SELECT c.relrowsecurity, count(p.polname) FROM pg_class c "
                    "LEFT JOIN pg_policy p ON p.polrelid = c.oid "
                    "WHERE c.relname = 'market_breadth' GROUP BY c.relrowsecurity"
                )
            )
        ).one()
    assert tenant_column == 0
    assert row[0] is False
    assert row[1] == 0


# --------------------------------------------------------------------------
# 0020_market_dispersion: the scanner appends a reading and can never edit it,
# the API only reads it, and the runtime login reaches neither without SET ROLE —
# DATABASE.md section 32 (owed; the conventions are section 31's, T3.90)
# --------------------------------------------------------------------------

_DISPERSION_INSERT = (
    "INSERT INTO market_dispersion (id, exchange_id, end_time, dispersion_version, "
    "horizon_minutes, universe_size, covered, alts_covered, alts_below_btc, btc_r24h, "
    "median_alt_r24h, dispersion, share_below_btc, coverage, usable, reason, inputs) "
    "VALUES (:id, :exchange, :end_time, 'dispersion_24h_v1', 1440, 16, 16, 15, 15, "
    "CAST(:btc AS numeric), CAST(:median AS numeric), CAST(:dispersion AS numeric), "
    "CAST(:share AS numeric), CAST(:coverage AS numeric), true, NULL, '{}'::jsonb)"
)
"""The plantão minute of 2026-09-10: the median alt at -4,80 % against the BTC at
-1,50 %, which is the row the whole revision exists to be able to hold."""


def _dispersion_params(exchange_id: uuid.UUID) -> dict[str, object]:
    return {
        "id": uuid7(),
        "exchange": exchange_id,
        "end_time": datetime(2026, 9, 10, 22, 8, tzinfo=UTC),
        "btc": Decimal("-0.015000"),
        "median": Decimal("-0.048000"),
        "dispersion": Decimal("-0.033000"),
        "share": Decimal("1.000000"),
        "coverage": Decimal("1.000000"),
    }


async def test_the_worker_appends_a_dispersion_reading_and_can_never_edit_it(
    worker_connection: AsyncConnection,
) -> None:
    """Measured as the role, not asked of the catalogue — ``market_breadth``'s proof
    repeated for the second series, because the argument is the same and it has to
    hold for both: ``0020`` installs no immutability trigger precisely because no
    legal ``UPDATE`` exists for one to police, so withholding ``UPDATE``/``DELETE``
    from the writer itself is the whole mechanism.
    """
    exchange_id = uuid7()
    await worker_connection.execute(
        text("INSERT INTO exchanges (id, code, name) VALUES (:id, :code, 'Probe')"),
        {"id": exchange_id, "code": f"dispersion-{uuid.uuid4().hex[:8]}"},
    )
    await worker_connection.execute(text(_DISPERSION_INSERT), _dispersion_params(exchange_id))
    assert (
        await worker_connection.scalar(
            text("SELECT count(*) FROM market_dispersion WHERE exchange_id = :id"),
            {"id": exchange_id},
        )
        == 1
    )

    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(text("UPDATE market_dispersion SET alts_below_btc = 0"))
    await worker_connection.rollback()
    await _set_as_worker(worker_connection)
    with pytest.raises(ProgrammingError, match=_DENIED):
        await worker_connection.execute(text("DELETE FROM market_dispersion"))
    await worker_connection.rollback()


async def test_the_two_roles_hold_exactly_select_and_select_insert_on_market_dispersion(
    schema_engine: AsyncEngine,
) -> None:
    """Asserted as sets, so a later revision that hands out ``UPDATE`` for "just a
    backfill" fails here instead of in a post-mortem about a number that changed
    under a decision. ``hunter_runtime`` holds nothing of its own (§27.1)."""
    async with schema_engine.connect() as connection:
        held = {
            role: {
                privilege
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE")
                if await connection.scalar(
                    text("SELECT has_table_privilege(:role, 'market_dispersion', :p)"),
                    {"role": role, "p": privilege},
                )
            }
            for role in ("hunter_app", "hunter_worker", "hunter_runtime")
        }
    assert held == {
        "hunter_app": {"SELECT"},
        "hunter_worker": {"SELECT", "INSERT"},
        "hunter_runtime": set(),
    }


async def test_market_dispersion_is_global_and_carries_no_tenant_column(
    schema_engine: AsyncEngine,
) -> None:
    """The universe belongs to the exchange, not to an organization (§1.1), so there
    is no ``organization_id`` and no RLS policy to isolate. Asserted rather than
    assumed, for ``market_breadth``'s reason: "no policy is needed" and "a policy
    nobody wrote" look identical from outside."""
    async with schema_engine.connect() as connection:
        tenant_column = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'market_dispersion' AND column_name = 'organization_id'"
            )
        )
        row = (
            await connection.execute(
                text(
                    "SELECT c.relrowsecurity, count(p.polname) FROM pg_class c "
                    "LEFT JOIN pg_policy p ON p.polrelid = c.oid "
                    "WHERE c.relname = 'market_dispersion' GROUP BY c.relrowsecurity"
                )
            )
        ).one()
    assert tenant_column == 0
    assert row[0] is False
    assert row[1] == 0


async def test_the_worker_appends_a_meme_observation_and_can_never_edit_it(
    worker_connection: AsyncConnection,
) -> None:
    """Proved **as the role**, not asked of the catalogue (§18.7, §25.4's rule).

    Four of the five meme tables are append-only for the engine, and the reason is
    the ``replay_runs`` one: a reading its own writer may rewrite is not evidence.
    There is no legal ``UPDATE`` on a curve observation — a second look at the same
    instant from the same source is the *same* row (the primary key says so), and a
    look at a different instant is a different row.
    """
    await worker_connection.execute(
        text(
            "INSERT INTO meme_curve_snapshots (observed_at, mint, source, "
            "virtual_sol_reserves, virtual_token_reserves, real_sol_reserves, "
            "real_token_reserves, total_supply, complete) VALUES "
            "(now(), 'PROBE_MINT', 'solana_rpc', 30, 1073000000, 0, 793100000, "
            "1000000000, false)"
        )
    )
    for statement in (
        "UPDATE meme_curve_snapshots SET complete = true WHERE mint = 'PROBE_MINT'",
        "DELETE FROM meme_curve_snapshots WHERE mint = 'PROBE_MINT'",
    ):
        await worker_connection.rollback()
        await worker_connection.begin()
        await worker_connection.execute(text("SET LOCAL ROLE hunter_worker"))
        with pytest.raises(ProgrammingError, match=_DENIED):
            await worker_connection.execute(text(statement))


async def test_the_api_role_reads_the_meme_radar_and_writes_none_of_it(
    app_connection: AsyncConnection,
) -> None:
    """The slice is monitoring only (T4-MEME-RADAR.md §0), and that is a privilege
    rather than a promise: every write the API could make is denied by the grant,
    before any trigger or CHECK is consulted."""
    readable = await app_connection.scalar(text("SELECT count(*) FROM meme_radar_features_v1"))
    assert readable is not None, "the API cannot read the read model it is meant to serve"
    for statement in (
        "INSERT INTO meme_tokens (mint, first_seen_source, first_seen_at, last_seen_at) "
        "VALUES ('API_MINT', 'pumpfun_rest', now(), now())",
        "INSERT INTO meme_features_1m (end_time, mint, features_version, coverage) "
        "VALUES (now(), 'API_MINT', 'meme_features_v1', 1)",
        "DELETE FROM meme_ingest_gaps",
    ):
        await app_connection.rollback()
        await app_connection.begin()
        await app_connection.execute(_AS_APP)
        with pytest.raises(ProgrammingError, match=_DENIED):
            await app_connection.execute(text(statement))


async def test_the_meme_tables_are_global_and_carry_no_tenant_column(
    schema_engine: AsyncEngine,
) -> None:
    """``replay_runs``' assertion, five tables over: "needs no policy" and
    "somebody forgot the policy" are indistinguishable from outside, so the
    absence is asserted and a tenant column appearing here later becomes a
    conversation instead of a silent hole."""
    async with schema_engine.connect() as connection:
        tenant_columns = await connection.scalar(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'organization_id' "
                "AND table_name LIKE 'meme%'"
            )
        )
        policies = await connection.scalar(
            text(
                "SELECT count(*) FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid "
                "WHERE c.relname LIKE 'meme%'"
            )
        )
    assert tenant_columns == 0
    assert policies == 0


_A_LAB_PROPOSAL = text(
    "INSERT INTO meme_proposals (id, mint, rule_set_id, origin, status, expires_at) "
    "SELECT gen_random_uuid(), 'PROBE_MINT', id, 'operator', 'proposed', now() + interval '2 min' "
    "FROM meme_rule_sets WHERE name = 'operator' RETURNING id"
)


async def test_the_api_role_decides_a_meme_proposal_and_touches_nothing_else(
    app_connection: AsyncConnection,
) -> None:
    """The desk's two writes, proved as the role (§18.7): a manual proposal and
    its decision are the API's; the quote, the bet and the deletion are not."""
    proposal = await app_connection.scalar(_A_LAB_PROPOSAL)
    await app_connection.execute(
        text(
            "UPDATE meme_proposals SET status = 'approved', decision = '{}'::jsonb, "
            "decided_by = 'user', decided_at = now() WHERE id = :id"
        ),
        {"id": proposal},
    )
    await app_connection.execute(
        text(
            "INSERT INTO meme_operator_commands (id, proposal_id, command, issued_by) "
            "VALUES (gen_random_uuid(), :id, 'cancel', 'user')"
        ),
        {"id": proposal},
    )
    for statement in (
        "UPDATE meme_proposals SET quote = '{}'::jsonb WHERE id = :id",
        "UPDATE meme_proposals SET refusal = 'x' WHERE id = :id",
        "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, entry_at, entry, "
        "  initial_risk_sol, params) SELECT gen_random_uuid(), :id, rule_set_id, mint, now(), "
        "  '{}'::jsonb, 1, '{}'::jsonb FROM meme_proposals WHERE id = :id",
        "DELETE FROM meme_proposals WHERE id = :id",
        "UPDATE meme_operator_commands SET applied_at = now() WHERE proposal_id = :id",
        "INSERT INTO meme_rule_sets (id, name, version, kind, code_ref) "
        "VALUES (gen_random_uuid(), 'x', '1', 'operator', 'x')",
    ):
        await app_connection.rollback()
        await app_connection.begin()
        await app_connection.execute(_AS_APP)
        with pytest.raises(ProgrammingError, match=_DENIED):
            await app_connection.execute(text(statement), {"id": proposal})


async def test_the_worker_writes_the_meme_lab_and_never_deletes_it(
    worker_connection: AsyncConnection,
) -> None:
    """The loop proposes, fills, marks and answers an order; it retires no rule
    set, issues no order and erases no evidence."""
    proposal = await worker_connection.scalar(_A_LAB_PROPOSAL)
    bet = await worker_connection.scalar(
        text(
            "INSERT INTO meme_paper_bets (id, proposal_id, rule_set_id, mint, entry_at, entry, "
            "  initial_risk_sol, params) SELECT gen_random_uuid(), id, rule_set_id, mint, now(), "
            "  '{}'::jsonb, 0.05, '{}'::jsonb FROM meme_proposals WHERE id = :id RETURNING id"
        ),
        {"id": proposal},
    )
    await worker_connection.execute(
        text("UPDATE meme_paper_bets SET mark_sol = 0.04, mark_at = now() WHERE id = :id"),
        {"id": bet},
    )
    for statement in (
        "DELETE FROM meme_paper_bets WHERE id = :bet",
        "DELETE FROM meme_proposals WHERE id = :proposal",
        "UPDATE meme_rule_sets SET status = 'retired', retired_at = now()",
        "INSERT INTO meme_operator_commands (id, bet_id, command, issued_by) "
        "VALUES (gen_random_uuid(), :bet, 'sell_now', 'worker')",
    ):
        await worker_connection.rollback()
        await worker_connection.begin()
        await worker_connection.execute(text("SET LOCAL ROLE hunter_worker"))
        with pytest.raises(ProgrammingError, match=_DENIED):
            await worker_connection.execute(text(statement), {"bet": bet, "proposal": proposal})
