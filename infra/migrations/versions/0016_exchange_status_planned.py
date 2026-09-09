"""exchange_status gains 'planned': a venue nobody collects is not a broken feed

Sixteenth revision. **One enum label.** No table, no column, no index, no
constraint, no trigger, no policy, no partition, no ``GRANT``.

It answers ``.claude/state/brief-T3.44c-exchange-status-planned.md``, which
T3.44b wrote instead of editing a migration. The symptom was in the topbar:
``exchanges`` holds ``binance`` and ``bybit``, ``bybit`` has never had a
collector deployed, and ``build_market_status`` renders **one row per
``exchanges`` entry** on purpose (an exchange the worker never touched must
appear rather than vanish). So the aggregate read ``2 exchanges ·
UNAVAILABLE`` — the worst-of reduction taking the state of a feed that was
never supposed to exist — while ``binance`` was connected the whole time.

**Why a third label and not a second column.** The brief left the choice open
and named the alternative (``has_collector boolean``, or a separate
``onboarding_status``). ``exchange_status`` already *is* the venue's lifecycle
for us, and ``planned`` is a point on it, not a second axis: catalogued but not
collected → collected → switched off. A boolean would be a deployment fact
sitting next to a lifecycle column, two things to keep in agreement with no
constraint able to say how, and every reader would have to learn that
``status = 'active' AND NOT has_collector`` means what one label means. And
``inactive`` is not it: nobody switched Bybit off. DATABASE.md §1 names adding
a value through a migration as *the* mechanism for exactly this; §28 records
the deviation from §15.1, which froze the type at ``active|inactive``.

**Position: ``BEFORE 'active'``** (``ddl/enums.py``,
``EXCHANGE_PLANNED_ADDED_VALUES``). ``enumsortorder`` is part of the contract
(§17.1) and ``hunter_core.domain.enums.ExchangeStatus`` declares ``PLANNED``
first to match: a venue is planned before it is collected.

**Inside the migration's transaction, and that is not an oversight.** The brief
asked for the ``ADD VALUE`` outside a transaction block "as Postgres requires".
Postgres 12+ requires no such thing — what it forbids is *using* the new label
in the same transaction, in a DEFAULT, an index predicate or any other DDL
(§17.1, §18.1). This revision adds the label and writes none of it:
``exchanges.status`` keeps the ``'active'`` default ``0001`` gave it, and
``planned`` first reaches a row through ``infra/scripts/seed.py``, after the
commit. Going through ``autocommit_block()`` would buy nothing and cost the
revision its atomicity, which is what ``0004`` pays only because
``CONCURRENTLY`` leaves it no choice (§17.5).

**The downgrade rebuilds the type, and refuses first.** There is no ``ALTER
TYPE ... DROP VALUE``; ``ddl/exchange_planned.py`` renames the type, recreates
it from the labels ``0001`` froze, retypes ``exchanges.status`` around its
default and drops the original — the recipe ``0003`` established. Before any of
that, a guard counts the exchanges still marked ``planned`` and **refuses**,
naming them: both surviving labels lie about such a venue (``active`` puts it
straight back into the aggregate this revision exists to fix, ``inactive``
claims somebody switched it off), and "the migration reverted without error"
would be the only report of that rewrite. On a database that never marked one —
every database before the next seed run — the guard counts zero and the
downgrade proceeds.

**No upgrade guard, and the absence is an assertion** (§19.5, §20.5, §21.4,
§24.6): the label is added, nothing already stored becomes unrepresentable,
every existing row keeps the label it has. **No grant and no RLS change**:
``exchanges`` is a global reference table (§1.1) — no ``organization_id``, no
policy, ``SELECT`` for ``hunter_app`` and write for ``hunter_worker`` since
``0001``, and a label is not a column, so no ACL is involved at all.

**Lock.** ``ALTER TYPE ... ADD VALUE`` takes ``ACCESS EXCLUSIVE`` on the *type*
in ``pg_type``, never on ``exchanges``: readers and writers of the table are not
blocked, and this opens no maintenance window (unlike ``0010``/``0012``, which
do validating ``ALTER TABLE``). The downgrade is the one that does take
``ACCESS EXCLUSIVE`` on ``exchanges``, for a table with two rows.

**Nothing here depends on session state:** one ``ALTER TYPE``. No session
prepared statement, no ``LISTEN``/``NOTIFY``, no session advisory lock — the
revision is transparent to the transaction pooler.

**Named ``0016_exchange_status_planned`` (28 characters)** —
``alembic_version.version_num`` is ``VARCHAR(32)`` (§17.6). Described in
``docs/DATABASE.md`` §28.

Revision ID: 0016_exchange_status_planned
Revises: 0015_runtime_login_role
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.enums import EXCHANGE_PLANNED_ADDED_VALUES, add_enum_values
from ddl.exchange_planned import (
    refuse_rows_using_the_planned_label,
    restore_exchange_status_without_planned,
)

revision: str = "0016_exchange_status_planned"
down_revision: str | None = "0015_runtime_login_role"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_enum_values(EXCHANGE_PLANNED_ADDED_VALUES)


def downgrade() -> None:
    refuse_rows_using_the_planned_label()
    restore_exchange_status_without_planned()
