"""Unit tests for ``infra/scripts/create_partitions.py``: the D4/D12 fixes and
the T2.5f backward horizon (``--months-behind``).

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
    uv run pytest infra/scripts/tests -q

``testpaths`` in ``pyproject.toml`` has since been extended with ``infra``, so a
bare ``uv run pytest`` collects this file too (the note here used to say the
opposite). The real-Postgres half of T2.5f lives next door in
``test_create_partitions_integration.py``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

import asyncpg
import pytest
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = SCRIPTS_DIR / "create_partitions.py"


def _load_module() -> ModuleType:
    """Load ``create_partitions.py`` by path, exactly as the integration suite does.

    A fresh module object per test (no shared ``sys.modules`` entry reused
    across tests) so ``monkeypatch.setattr`` on one test's module never leaks
    into another's.

    ``infra/scripts`` goes on ``sys.path`` first, the same surgery
    ``packages/core/tests/integration/conftest.py::_load_script`` does: since
    T2.5f the script imports its plan from the sibling ``partition_plan``
    module, which running it as ``python infra/scripts/create_partitions.py``
    resolves for free and loading it by path does not.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
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


# --- T2.5f: months behind ----------------------------------------------------
#
# The job only ever looked forward, so a seven-day backfill request made early
# in a month named minutes no partition accepted and the market-worker's
# consumer refused them with ``no_partition`` (notes-T2.5 §31). These tests fix
# the new half of the policy: how far back the job provisions, and the one
# condition under which it declines to.


def _months_of(groups: list[Any], owner: str) -> list[tuple[int, int]]:
    """The ``(year, month)`` pairs planned for one monthly owner, in plan order."""
    prefix = f"{owner}_"
    months: list[tuple[int, int]] = []
    for _parent, statements in groups:
        for name, sql in statements:
            if not sql.startswith("CREATE TABLE IF NOT EXISTS") or "FOR VALUES FROM" not in sql:
                continue
            if not name.startswith(prefix):
                continue
            year, month = name[len(prefix) :].split("_")
            months.append((int(year), int(month)))
    return months


def test_the_default_horizon_reaches_two_months_back() -> None:
    """The fix itself: without asking, the job now provisions the recent past.

    Two, because the widest window anyone asks for is 30 days (replay/β) and
    one month back is its strict minimum, with no room for a request whose
    window ends a few days in the past.
    """
    module = _load_module()
    now = datetime(2026, 9, 6, tzinfo=UTC)

    months = _months_of(module.planned_groups(3, now), "candles_1m")

    assert module.DEFAULT_MONTHS_BEHIND == 2
    assert months[:3] == [(2026, 7), (2026, 8), (2026, 9)]
    assert months[-1] == (2026, 12), "the forward horizon must be untouched"


def test_months_behind_zero_plans_exactly_what_the_job_planned_before() -> None:
    """Regression fence: the new parameter is additive, not a rewrite.

    With ``--months-behind 0`` the plan is the current month and the ones
    ahead — statement for statement, the behaviour every existing test of this
    script was written against.
    """
    module = _load_module()
    now = datetime(2026, 9, 6, tzinfo=UTC)

    groups = module.planned_groups(3, now, 0)

    assert _months_of(groups, "candles_1m") == [(2026, 9), (2026, 10), (2026, 11), (2026, 12)]
    assert _months_of(groups, "audit_logs") == [(2026, 9), (2026, 10), (2026, 11), (2026, 12)]


def test_a_backward_month_retention_already_expired_is_not_planned() -> None:
    """The guard, per owner: never create what the pruner drops the same night.

    On 2026-09-06 the 30-day retention of ``market_snapshots`` still covers
    August (its upper bound, 2026-09-01, is after the 2026-08-07 cutoff) but no
    longer July, while ``candles_1m``'s 90 days covers both. One global "keep
    two months back" would either starve candles or make the short-retention
    parents churn: created at 04:07, dropped by ``prune_partitions.py`` at
    04:12, every night, each taking ``ACCESS EXCLUSIVE`` on the parent for
    nothing.
    """
    module = _load_module()
    now = datetime(2026, 9, 6, tzinfo=UTC)

    groups = module.planned_groups(0, now)

    assert _months_of(groups, "candles_1m")[:2] == [(2026, 7), (2026, 8)]
    assert _months_of(groups, "market_snapshots") == [(2026, 8), (2026, 9)]
    assert _months_of(groups, "liquidations") == [(2026, 8), (2026, 9)]
    # audit_logs is kept forever, so nothing is ever filtered out of its past
    assert _months_of(groups, "audit_logs") == [(2026, 7), (2026, 8), (2026, 9)]


def test_a_parent_whose_whole_window_has_passed_gets_no_past_at_all() -> None:
    """14-day retention (``feature_snapshots``) late in a month: no backward month.

    On 2026-09-20 the cutoff is 2026-09-06, past August's upper bound — every
    row August could still hold is already expired. Planning it would create a
    partition with nothing legal to put in it.
    """
    module = _load_module()
    now = datetime(2026, 9, 20, tzinfo=UTC)

    assert _months_of(module.planned_groups(0, now), "feature_snapshots") == [(2026, 9)]


def test_the_plan_never_contains_a_month_the_pruner_would_drop() -> None:
    """The invariant, read from the *other* job's own function, all year round.

    ``partition_retention.is_expired`` is what ``prune_partitions.py`` plans
    with; asserting against it is what makes "the two daily jobs cannot fight"
    a property rather than a comment. Checked on every 5th day of a year so a
    month boundary, a February and a year rollover are all included.
    """
    module = _load_module()
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import partition_retention

    policy = partition_retention.retention_days()
    day = datetime(2026, 9, 1, tzinfo=UTC)
    for _ in range(73):
        day += timedelta(days=5)
        for owner, keep_days in policy.items():
            for year, month in _months_of(module.planned_groups(3, day), owner):
                child = f"{owner}_{year:04d}_{month:02d}"
                assert not partition_retention.is_expired(child, keep_days, day), (
                    f"{child} would be planned on {day.date()} and dropped by prune the same day"
                )


def test_ninety_day_retention_covers_the_two_months_behind_every_day_of_a_year() -> None:
    """``candles_1m`` is the parent the backfill actually writes to.

    DATABASE.md §1.3 requires the retention window to be at least
    ``months-behind + 1`` months for a parent that receives history: 90 days is
    ≥ 3 calendar months in the worst case, so the guard above never trims
    ``candles_1m``'s past — proven for every 5th day of a year rather than for
    the one date this was written on.
    """
    module = _load_module()
    day = datetime(2026, 9, 1, tzinfo=UTC)
    for _ in range(73):
        day += timedelta(days=5)
        months = _months_of(module.planned_groups(0, day), "candles_1m")
        assert len(months) == 3, f"candles_1m lost a backward month on {day.date()}: {months}"


def test_thirty_days_back_from_the_first_of_march_needs_the_second_month() -> None:
    """Why the default is 2 and not 1 — the case Astra's review of this diff produced.

    2027-03-01 minus 30 days is 2027-01-30: a 30-day replay window opened on the
    first of March reaches **January**, not February, because February is short.
    With one month behind, that request would be refused for its oldest two
    days, which is the same ``no_partition`` this task exists to remove.
    """
    module = _load_module()
    now = datetime(2027, 3, 1, tzinfo=UTC)

    assert (now - timedelta(days=30)).month == 1
    assert _months_of(module.planned_groups(0, now), "candles_1m")[:2] == [(2027, 1), (2027, 2)]


def test_expiry_flips_at_a_utc_midnight_and_the_plan_moves_with_it() -> None:
    """The boundary the invariant is stated at: same instant, same answer.

    ``feature_snapshots`` keeps 14 days, so August's upper bound (2026-09-01)
    falls out of the window between 2026-09-14 23:59 and 2026-09-15 00:00 UTC.
    A run planned just before that midnight and pruned just after can therefore
    create a month the next prune drops — once, self-healing (the next plan no
    longer contains it), and never at the cost of a retained row. Written down
    as a test so the "the two jobs cannot fight" claim keeps its "at the same
    instant" qualifier.
    """
    module = _load_module()

    before = datetime(2026, 9, 14, 23, 59, tzinfo=UTC)
    after = datetime(2026, 9, 15, 0, 1, tzinfo=UTC)

    assert _months_of(module.planned_groups(0, before), "feature_snapshots") == [
        (2026, 8),
        (2026, 9),
    ]
    assert _months_of(module.planned_groups(0, after), "feature_snapshots") == [(2026, 9)]
