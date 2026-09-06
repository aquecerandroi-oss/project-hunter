"""What the daily partition job intends to create — DATABASE.md §1.3.

Split out of ``create_partitions.py`` when T2.5f pushed that file past the
350-line budget (``infra/scripts/check_file_size.py``): the *plan* (which months,
for which parent, with which DDL) lives here, the *execution* (engine,
one transaction per parent, lock-timeout handling, exit codes) stays there.
Nothing here touches the database.

Three horizons, one job:

- the **current** month, always;
- ``months_ahead`` **future** months (default 3, §1.3) — so no insert ever
  arrives before its partition;
- ``months_behind`` **past** months (default 2, T2.5f) — so a backfill of
  history has somewhere to land. This is the half that did not exist: a request
  for seven days made on the 6th names minutes in the previous month, no
  partition accepted them, and the market-worker's consumer refused 3 300 of
  8 547 minutes with ``market_backfill_refused reason=no_partition``.

A backward month is planned **only while retention would still keep it**
(:func:`partition_retention.month_is_retained`, evaluated at the same instant —
see its docstring for the UTC-midnight boundary). Creating a month the pruner
drops the same night is not conservative, it is a nightly fight over the same
partition, each side taking ``ACCESS EXCLUSIVE`` on the parent for nothing —
and the month would be gone again before any backfill could use it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from partition_retention import month_is_retained, retention_days

from hunter_core.db.models import (
    create_list_partition_sql,
    create_partition_sql,
    harden_partition_sql,
    list_partition_name,
    list_partitioned_tables,
    monthly_partition_parents,
    months_before,
    months_from,
    partition_name,
    tenant_tables,
)

if TYPE_CHECKING:
    from hunter_core.settings import Settings

DEFAULT_MONTHS_AHEAD = 3
"""DATABASE.md §1.3: partitions exist three months before they are needed."""

DEFAULT_MONTHS_BEHIND = 2
"""Two, because the widest history anyone asks for is 30 days plus a margin.

The backfill windows in flight are seven days (baseline bootstrap) and thirty
(replay / β), and **one month behind is not always enough for thirty days**:
2027-03-01 minus 30 days is 2027-01-30, because February is short. Two months
cover 30 days in every month of the calendar — at least 59 days of past when the
job runs on the 1st, about 92 when it runs at the end — plus margin for a
request whose window ends a few days in the past (a gap detected late, a replay
of an older stretch, a day the job did not run). It is not larger because a
backward month is only useful while retention keeps it, and three months back is
already outside ``candles_1m``'s 90 days.
"""

_DATE_ONLY_BOUND = re.compile(r"'(\d{4}-\d{2}-\d{2})'")

Statement = tuple[str, str]
"""``(relation the statement concerns, SQL)``."""

Group = tuple[str, list[Statement]]
"""``(partitioned parent, its statements)`` — the unit of one transaction."""


def _explicit_utc_bounds(sql: str) -> str:
    """Rewrite ``_partitions.py``'s bare date bounds to carry an explicit ``+00``.

    ``create_partition_sql`` emits ``FOR VALUES FROM ('2026-09-01') TO
    ('2026-10-01')`` — a date literal, not a timestamp, so Postgres attaches
    midnight in the *session* ``TimeZone`` to it (D12). Turning it into
    ``'2026-09-01 00:00:00+00'`` here makes the statement's own text
    unambiguous regardless of any session setting, without editing the frozen
    ``_partitions.py``. A no-op on statements with no date-only literal (the
    LIST level's ``FOR VALUES IN ('1m')`` never matches this pattern).
    """
    return _DATE_ONLY_BOUND.sub(lambda m: f"'{m.group(1)} 00:00:00+00'", sql)


def _harden(child: str, root: str, tenants: frozenset[str]) -> list[Statement]:
    return [
        (child, sql)
        for sql in harden_partition_sql(
            child, tenant=root in tenants, audit_scope=root == "audit_logs"
        )
    ]


def planned_months(
    owner: str,
    months_ahead: int,
    months_behind: int,
    now: datetime,
    policy: dict[str, int | None],
) -> list[tuple[int, int]]:
    """The months this run wants for ``owner``, oldest first.

    Past months are filtered by :func:`~partition_retention.month_is_retained`;
    the current month and everything ahead are never filtered — retention has no
    opinion about a month that has not ended.
    """
    behind = [
        (year, month)
        for year, month in months_before(now, months_behind)
        if month_is_retained(owner, year, month, now, policy)
    ]
    return behind + months_from(now, months_ahead + 1)


def planned_groups(
    months_ahead: int,
    now: datetime | None = None,
    months_behind: int = DEFAULT_MONTHS_BEHIND,
    settings: Settings | None = None,
) -> list[Group]:
    """Everything needed from ``months_behind`` back to ``months_ahead`` forward, per parent.

    Grouped by the *top-level* partitioned table, which is the relation whose
    lock every statement in the group contends for: the ``candles_1m`` level and
    every ``candles_1m_YYYY_MM`` under it all belong to ``candles``. Within a
    group the order still matters — the LIST level is created before the months
    that hang off it — and the flattened order is unchanged from before, with the
    backward months simply leading each owner's run of months.

    ``months_behind`` is keyword-or-third-positional so the two existing callers
    that pass ``(months_ahead, now)`` positionally keep working unchanged.
    """
    start = now or datetime.now(UTC)
    tenants = frozenset(tenant_tables())
    policy = retention_days(settings)
    groups: dict[str, list[Statement]] = {}

    for parent, (_column, labels, sub_key) in list_partitioned_tables().items():
        statements = groups.setdefault(parent, [])
        for label in labels:
            intermediate = list_partition_name(parent, label)
            statements.append((intermediate, create_list_partition_sql(parent, label, sub_key)))
            statements += _harden(intermediate, parent, tenants)

    for owner, root in monthly_partition_parents().items():
        statements = groups.setdefault(root, [])
        for year, month in planned_months(owner, months_ahead, months_behind, start, policy):
            child = partition_name(owner, year, month)
            sql = _explicit_utc_bounds(create_partition_sql(owner, year, month))
            statements.append((child, sql))
            statements += _harden(child, root, tenants)

    return list(groups.items())


def planned_statements(
    months_ahead: int,
    now: datetime | None = None,
    months_behind: int = DEFAULT_MONTHS_BEHIND,
    settings: Settings | None = None,
) -> list[Statement]:
    """:func:`planned_groups` flattened — what ``--dry-run`` prints."""
    return [
        statement
        for _parent, statements in planned_groups(months_ahead, now, months_behind, settings)
        for statement in statements
    ]
