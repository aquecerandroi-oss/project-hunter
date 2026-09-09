"""``0016_exchange_status_planned``: the guard and the type rebuild.

The *upgrade* half of this revision is one line and lives in
:data:`ddl.enums.EXCHANGE_PLANNED_ADDED_VALUES` — ``ALTER TYPE exchange_status
ADD VALUE 'planned' BEFORE 'active'``. Everything here is the **downgrade**,
which is the expensive direction: Postgres has no ``ALTER TYPE ... DROP VALUE``,
so reversing an ``ADD VALUE`` means rebuilding the type and retyping every
column that uses it, and doing that under a row that still says ``planned``
fails deep inside the rebuild with *invalid input value for enum*.

Frozen per revision, the rule §15.6/§16.5/§17.1 fix for every list in this
package: the labels ``0016`` restores are read from
:data:`ddl.enums.INITIAL_ENUMS`, which ``0001`` owns and no later revision
rewrites, and the columns are named here rather than discovered at migration
time. A later revision that puts ``exchange_status`` on a second column and
does not extend its *own* rebuild will not silently lose it: ``DROP TYPE`` on
the renamed original fails while that column still depends on it, which is a
loud error naming the dependency instead of a quiet retype that missed one.
"""

from __future__ import annotations

from typing import Final

from alembic import op

from ddl.enums import EXCHANGE_PLANNED_ADDED_VALUES, INITIAL_ENUMS

EXCHANGE_STATUS_TYPE: Final[str] = "exchange_status"

EXCHANGE_STATUS_COLUMNS_0016: Final[tuple[tuple[str, str, str | None], ...]] = (
    ("exchanges", "status", "active"),
)
"""``(table, column, server default or None)`` — every column typed
``exchange_status`` when ``0016`` was written.

One entry, and that is the whole point of writing it down: ``exchanges.status``
is the single column of this type in the schema (``0001_initial_schema``
§3), it carries ``server_default 'active'``, and a default is stored already
coerced to the old type — so it has to be dropped and restored around the
retype, exactly as ``ddl/analysis.py::restore_frozen_enum_labels`` does for the
three columns ``0003`` touched.
"""

PLANNED_LABEL: Final[str] = EXCHANGE_PLANNED_ADDED_VALUES[0][1]
"""``'planned'`` — taken from the frozen tuple so the guard and the ``ADD
VALUE`` can never name different labels."""


def refuse_rows_using_the_planned_label() -> None:
    """Refuse the downgrade while any exchange still says ``planned``.

    §17.7: reversing a schema is allowed, losing a fact is not — and here the
    fact is small and irreplaceable. A venue marked ``planned`` is one the
    operator declared *catalogued but not collected*; the two labels that
    survive a downgrade both lie about it (``active`` puts it back into the
    market-status aggregate as a feed that does not exist — the exact bug
    ``0016`` exists to end — and ``inactive`` says somebody switched it off).

    Nothing is deleted here: the offenders are counted and named, with the one
    instruction that is honest — decide which of the two surviving labels each
    venue really is, write it, then downgrade.

    It walks the **same frozen tuple the rebuild walks**, one entry at a time,
    rather than the single column that exists today: a revision that puts
    ``exchange_status`` on a second column and extends
    :data:`EXCHANGE_STATUS_COLUMNS_0016` gets the guard for free, and one that
    extends neither still fails loudly on ``DROP TYPE`` (the module docstring).
    A guard that checked one column while the rebuild retyped several would fail
    *inside* the rebuild with *invalid input value for enum*, which names no way
    out.
    """
    for table, column, _default in EXCHANGE_STATUS_COLUMNS_0016:
        op.execute(
            # S608: table, column and label are constants of this module, never input.
            "DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM {table} "
            f"WHERE {column}::text = '{PLANNED_LABEL}'; "
            "IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' rows in {table} are still "
            "status = ''planned'', a label only 0016_exchange_status_planned defines; "
            "rebuilding the type would have to rewrite them into a label that means "
            "something else', "
            "HINT = 'set each one to active (a collector runs for it) or inactive "
            "(it was switched off) — never let the downgrade choose — then downgrade'; "
            "END IF; END $$;"
        )


def restore_exchange_status_without_planned() -> None:
    """Rebuild ``exchange_status`` with the labels ``0001`` froze.

    Rename, recreate, retype, drop — the recipe ``0003`` established and the
    only one Postgres offers for removing a label. The default is dropped and
    restored around the retype because a stored default is already coerced to
    the type being replaced and would block it.
    """
    previous = f"{EXCHANGE_STATUS_TYPE}__pre0016"
    rendered = ", ".join(f"'{label}'" for label in INITIAL_ENUMS[EXCHANGE_STATUS_TYPE])
    op.execute(f"ALTER TYPE {EXCHANGE_STATUS_TYPE} RENAME TO {previous}")
    op.execute(f"CREATE TYPE {EXCHANGE_STATUS_TYPE} AS ENUM ({rendered})")
    for table, column, default in EXCHANGE_STATUS_COLUMNS_0016:
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {EXCHANGE_STATUS_TYPE} "
            f"USING {column}::text::{EXCHANGE_STATUS_TYPE}"
        )
        if default is not None:
            op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{default}'")
    op.execute(f"DROP TYPE {previous}")
