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

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from .conftest import migration_ddl

pytestmark = pytest.mark.integration

_AS_APP = text("SET LOCAL ROLE hunter_app")
_DENIED = "permission denied"

_WRITE_PRIVILEGES = ("UPDATE", "DELETE")


def _security() -> object:
    return migration_ddl("security")


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
    append_only: tuple[str, ...] = _security().APPEND_ONLY_TABLES  # type: ignore[attr-defined]

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
    append_only: tuple[str, ...] = _security().APPEND_ONLY_TABLES  # type: ignore[attr-defined]
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
    read_only: tuple[str, ...] = _security().APP_READ_ONLY_TABLES  # type: ignore[attr-defined]
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
    security = _security()
    write: tuple[str, ...] = security.APP_WRITE_TABLES  # type: ignore[attr-defined]
    no_delete: tuple[str, ...] = security.APP_NO_DELETE_TABLES  # type: ignore[attr-defined]
    read_only: tuple[str, ...] = security.APP_READ_ONLY_TABLES  # type: ignore[attr-defined]
    append_only: tuple[str, ...] = security.APPEND_ONLY_TABLES  # type: ignore[attr-defined]

    classified = list(write) + list(no_delete) + list(read_only) + list(append_only)
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
    no_delete: tuple[str, ...] = _security().APP_NO_DELETE_TABLES  # type: ignore[attr-defined]
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
    lifecycle: tuple[str, ...] = _security().WORKER_DELETE_TABLES  # type: ignore[attr-defined]
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
