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
    write = _security_tables("APP_WRITE_TABLES")
    no_delete = _security_tables("APP_NO_DELETE_TABLES")
    read_only = _security_tables("APP_READ_ONLY_TABLES")
    append_only = _security_tables("APPEND_ONLY_TABLES")

    shadow_read_only = _shadow_tables("SHADOW_APP_READ_ONLY_TABLES")
    analysis_read_only = _analysis_tables("ANALYSIS_APP_READ_ONLY_TABLES")

    classified = (
        list(write)
        + list(no_delete)
        + list(read_only)
        + list(append_only)
        + list(shadow_read_only)
        + list(analysis_read_only)
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
