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
