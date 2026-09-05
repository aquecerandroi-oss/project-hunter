"""Unit tests for the D4/D12 fixes in ``infra/scripts/create_partitions.py``.

Location note: the repo's existing coverage for this script is integration-only,
against a real Postgres, in
``packages/core/tests/integration/test_schema_seed_and_partitions.py`` (loaded
by path — the script is not an installed package, see that file's docstring).
That location is inside ``packages/**``, out of scope for this change, so this
is a *new* location: pure unit tests, no database, exercising
``ensure_partitions`` against a fake connection that records exactly what SQL
text it was asked to execute. If a maintainer with access to
``packages/core/tests/integration`` wants a real-Postgres assertion of the same
two ``SET LOCAL`` statements later, that file is where it belongs; this one
does not depend on it and does not modify it.

Run:
    uv run pytest infra/scripts/tests/test_create_partitions.py -v

Not wired into ``[tool.pytest.ini_options] testpaths`` (``pyproject.toml`` only
lists ``packages``, ``apps``, ``services``, ``tests`` — outside this change's
file scope), so a bare ``uv run pytest`` will not pick this file up on its own;
it must be named explicitly, as above, or ``testpaths`` extended separately.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import asyncpg
import pytest
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.unit

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "create_partitions.py"


def _load_module() -> ModuleType:
    """Load ``create_partitions.py`` by path, exactly as the integration suite does.

    A fresh module object per test (no shared ``sys.modules`` entry reused
    across tests) so ``monkeypatch.setattr`` on one test's module never leaks
    into another's.
    """
    spec = importlib.util.spec_from_file_location("hunter_infra_create_partitions_ut", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResult:
    """Just enough of a cursor result for ``for row in result`` to work."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class FakeTransaction:
    """A no-op async context manager standing in for ``AsyncConnection.begin()``."""

    async def __aenter__(self) -> FakeTransaction:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False  # never swallow — real rollback-on-exception behaves the same way


class FakeConnection:
    """Records every executed statement's text; can be told to fail on one of them.

    ``fail_contains``/``fail_with`` let a test make a specific DDL statement
    raise the exact exception shape ``ensure_partitions`` has to tell apart —
    real Postgres wraps a ``lock_timeout`` hit as
    ``asyncpg.exceptions.LockNotAvailableError`` inside a
    ``sqlalchemy.exc.DBAPIError`` (SQLSTATE 55P03); a different ``orig`` type
    is the control case that must still propagate.
    """

    def __init__(
        self,
        existing: tuple[str, ...] = (),
        fail_contains: str | None = None,
        fail_with: BaseException | None = None,
    ) -> None:
        self.executed: list[str] = []
        self._existing = existing
        self._fail_contains = fail_contains
        self._fail_with = fail_with

    def begin(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, clause: object) -> FakeResult:
        sql = str(clause)
        self.executed.append(sql)
        if self._fail_contains is not None and self._fail_contains in sql:
            assert self._fail_with is not None
            raise self._fail_with
        if sql.strip().startswith("SELECT c.relname"):
            return FakeResult([(name,) for name in self._existing])
        return FakeResult([])


class FakeConnectionCtx:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self._connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class FakeEngine:
    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection
        self.disposed = False

    def connect(self) -> FakeConnectionCtx:
        return FakeConnectionCtx(self._connection)

    async def dispose(self) -> None:
        self.disposed = True


def _patch_engine(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, connection: FakeConnection
) -> FakeEngine:
    engine = FakeEngine(connection)

    def _fake_create_async_engine(*_args: object, **_kwargs: object) -> FakeEngine:
        return engine

    monkeypatch.setattr(module, "create_async_engine", _fake_create_async_engine)
    monkeypatch.setattr(module, "migration_url", lambda: "postgresql+asyncpg://fake/fake")
    return engine


def test_each_group_transaction_opens_with_both_set_local_guards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D4 + D12: every per-parent transaction runs ``lock_timeout`` then ``TimeZone`` first.

    Reconstructs the exact statement sequence ``ensure_partitions`` must send:
    the existence census, then per group (in order) the two guards followed by
    that group's own DDL — proving both presence, order (guards before any
    DDL) and that they are per-transaction (once per group), not once for the
    whole run.
    """
    module = _load_module()
    groups = module.planned_groups(0)
    connection = FakeConnection()
    _patch_engine(monkeypatch, module, connection)
    asyncio.run(module.ensure_partitions(groups))

    expected: list[str] = [str(module._EXISTING_PARTITIONS)]
    for _parent, statements in groups:
        expected.append(module._LOCK_TIMEOUT_SQL)
        expected.append(module._SESSION_UTC_SQL)
        expected.extend(sql for _name, sql in statements)

    assert connection.executed == expected


def test_monthly_bounds_carry_an_explicit_utc_offset() -> None:
    """D12 belt-and-braces: ``_explicit_utc_bounds`` makes the bound literal unambiguous.

    ``_partitions.py`` (frozen) emits a bare date; the script must not depend
    solely on ``SET LOCAL TimeZone`` to make that safe.
    """
    module = _load_module()
    groups = module.planned_groups(0)
    monthly_ddl = [
        sql
        for _parent, statements in groups
        for _name, sql in statements
        if sql.startswith("CREATE TABLE IF NOT EXISTS") and "FOR VALUES FROM" in sql
    ]
    assert monthly_ddl, "no monthly RANGE partition statement found to check"
    for sql in monthly_ddl:
        assert "+00" in sql, f"bound literal is not explicit UTC: {sql}"
        assert " 00:00:00+00" in sql


def test_list_partition_statements_are_untouched_by_the_bound_rewrite() -> None:
    """The LIST level's ``FOR VALUES IN ('1m')`` is not a date; the rewrite must not touch it."""
    module = _load_module()
    groups = module.planned_groups(0)
    list_ddl = [
        sql for _parent, statements in groups for _name, sql in statements if "FOR VALUES IN" in sql
    ]
    assert list_ddl, "no LIST partition statement found to check"
    for sql in list_ddl:
        assert "+00" not in sql


def test_lock_timeout_on_one_group_is_skipped_not_raised_and_others_still_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D4: a lock_timeout hit on one parent's DDL is logged and skipped, not fatal.

    The failing group contributes nothing to ``created``; ``on_skip`` is told
    which parent was skipped; every other group still completes normally.
    """
    module = _load_module()
    groups = module.planned_groups(0)
    assert len(groups) > 1, "need at least two groups to prove the others are unaffected"
    failing_parent, failing_statements = groups[0]
    _failing_name, failing_sql = failing_statements[0]

    lock_error = DBAPIError(
        failing_sql, {}, asyncpg.exceptions.LockNotAvailableError("lock timeout")
    )
    connection = FakeConnection(fail_contains=failing_sql, fail_with=lock_error)
    _patch_engine(monkeypatch, module, connection)
    skipped: list[str] = []
    created = asyncio.run(module.ensure_partitions(groups, on_skip=skipped.append))

    assert skipped == [failing_parent]
    failing_names = {name for name, _sql in failing_statements}
    assert not (failing_names & set(created)), "the skipped group must not report anything created"
    other_names = {
        name
        for parent, statements in groups
        if parent != failing_parent
        for name, _sql in statements
    }
    assert other_names <= set(created), "the other groups must still be created"


def test_a_non_lock_timeout_error_still_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Control case: only ``lock_timeout`` (55P03) is treated as skippable; anything else raises."""
    module = _load_module()
    groups = module.planned_groups(0)
    _failing_name, failing_sql = groups[0][1][0]

    other_error = DBAPIError(
        failing_sql, {}, asyncpg.exceptions.UndefinedTableError("relation does not exist")
    )
    connection = FakeConnection(fail_contains=failing_sql, fail_with=other_error)
    _patch_engine(monkeypatch, module, connection)

    with pytest.raises(DBAPIError):
        asyncio.run(module.ensure_partitions(groups))
