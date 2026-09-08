"""``0012_replication`` — the replication cohort, ``promising_at`` and a sibling's lineage.

T3.19 (``docs/plans/REPLICATION.md``) shipped the protocol and declared two
pendencies in ``.claude/state/notes-T3.19.md`` (CONCERNS 1 and 2). Both were the
same kind of gap: something the protocol *depends on* lived in prose instead of
in the schema.

1. **The arm label was not a cohort.** ``shadow_episodes.cohort`` accepted only
   ``prospective`` and ``replay:<uuid>``, so a sibling's signals were emitted as
   ``prospective`` — the one cohort the execution bridge admits (T3.15e). The
   three barriers that keep a sibling away from the wallet held (``purpose =
   research_only``, no ``agents`` row, the cohort filter), but the cheapest of
   them, the one that refuses **by name before any wallet query**, was refusing
   a label nothing could ever write. This revision widens the CHECK to
   ``replication:<parent_version_id>:<k>``, ``k`` in 1..99.
2. **``promising_at`` lived in the ``changelog``** of the siblings and in a
   ``system_events`` row that retention deletes after 30 days — while block 1 of
   the protocol needs at least 15 days *of distinct decision days* measured from
   it. A marker whose durable copy is a substring of a free-text column is not a
   marker. It becomes a column, with ``promising_by`` naming the verdict that
   wrote it.

And one thing neither pendency named, found writing this: a sibling's lineage
(*whose* sibling, *which* arm) was also only a sentence in ``changelog``,
recovered by regex (``replication_stats.ARM_RE``). Two columns and a UNIQUE make
it a fact: ``replication_parent_id`` and ``replication_index``.

**Every list here is frozen as of this revision**, the same rule
``ddl/shadow.py``, ``ddl/analysis.py``, ``ddl/paper*.py`` and
``ddl/strategy_purpose.py`` state for their own: a later edit here must never
change what ``0012`` installs. The two patterns below are therefore *copies*,
not imports of ``hunter_core.domain.enums.SHADOW_COHORT_PATTERN`` — the
database's contract must not silently follow a later edit to a Python constant
(``ddl/paper_geometry.py``'s module docstring), and
``test_migrations.py::test_0012_and_the_domain_constant_agree_on_the_cohort_grammar``
is what keeps the copy honest.

**No grant, and that is an assertion, not an omission.** ``0010`` revoked
``hunter_worker``'s table-level ``INSERT``/``UPDATE`` on ``strategy_versions``
and re-granted twelve columns; ``0011`` revoked ``INSERT`` outright and
``UPDATE`` on seven of them. What is left for the worker is a table-level
``SELECT`` plus ``UPDATE`` on five named columns — so a column *added* here is
readable by both roles (the table grant covers it) and writable by neither
application role, without a single statement. That is the same shape ``purpose``
has, arrived at by subtraction instead of by revocation, and it is proven as the
role rather than declared: ``test_schema_privileges.py::
test_the_worker_cannot_write_any_of_the_replication_columns``. Writing a
no-op ``REVOKE`` here to *look* like a guarantee is exactly the mistake
DATABASE.md §15.6 records about ``ALTER DEFAULT PRIVILEGES ... REVOKE ALL``.

Described in ``docs/DATABASE.md`` §24.
"""

from __future__ import annotations

from alembic import op

COHORT_CHECK = "ck_shadow_episodes_cohort_format"

_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

COHORT_PATTERN_0002 = f"^(prospective|replay:{_UUID})$"
"""What ``0002_shadow_lab`` wrote, byte for byte — the target of the downgrade."""

COHORT_PATTERN_0012 = f"^(prospective|replay:{_UUID}|replication:{_UUID}:[1-9][0-9]?)$"
"""``0002``'s two branches **unchanged**, plus the replication arm.

``[1-9][0-9]?`` is 1..99 written as a shape rather than as a digit count, so
``:0`` and ``:01`` are refused: a second spelling of arm 1 would be a second
population under a name the report already uses.
"""

REPLICATION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("promising_at", "timestamptz"),
    ("promising_by", "text"),
    ("replication_parent_id", "uuid"),
    ("replication_index", "smallint"),
)
"""The four columns ``0012`` adds to ``strategy_versions``, in creation order.

All nullable, none with a default: a version written before this revision
genuinely has no promising marker and genuinely is not a sibling, and a default
would claim otherwise. There is therefore **no upgrade guard** — the same
assertion ``0009`` (§21.4) and ``0010`` (§22.1) make: nothing already stored
becomes unrepresentable.
"""

LINEAGE_CHECK = "ck_strategy_versions_replication_lineage"
PROMISING_CHECK = "ck_strategy_versions_promising_is_attributed"
ARM_UNIQUE = "uq_strategy_versions_replication_arm"
PARENT_FK = "fk_strategy_versions_replication_parent"

_LINEAGE_CHECK_SQL = (
    "(replication_parent_id IS NULL) = (replication_index IS NULL) "
    "AND (replication_index IS NULL OR replication_index BETWEEN 1 AND 99) "
    "AND replication_parent_id IS DISTINCT FROM id"
)
"""Three clauses, and each closes a different way of half-writing a lineage.

- the biconditional: an arm without a parent names an experiment nobody can
  find again, and a parent without an arm cannot be told from its siblings;
- the range: the same 1..99 the cohort grammar accepts, so a row can never
  carry a lineage that has no representable cohort;
- ``IS DISTINCT FROM id``: a version is not its own sibling (the precedent is
  ``portfolio_exit_intents``' ``id <> superseded_by_id``, §18.4). ``IS DISTINCT
  FROM`` rather than ``<>`` because ``<>`` is ``NULL`` for a ``NULL`` parent,
  and a CHECK that evaluates to ``NULL`` is satisfied — the ``coalesce`` trap
  ``0009`` measured (§21.1), one operator earlier.
"""

_PROMISING_CHECK_SQL = (
    "(promising_at IS NULL) = (promising_by IS NULL) "
    "AND (promising_by IS NULL OR char_length(promising_by) BETWEEN 1 AND 64)"
)
"""A marker nobody can attribute is a date, not evidence; and a ``NOT NULL``
alone would accept the empty string, which attributes nothing — the argument
``0002`` makes about ``no_entry_reason`` (§16.2)."""

_FROZEN_COLUMNS_0012: tuple[str, ...] = (
    "strategy_id",
    "version",
    "code_ref",
    "parameters_schema",
    "default_parameters",
    "params_format",
    "activated_at",
    "purpose",
    "replication_parent_id",
    "replication_index",
)
"""``ddl.strategy_purpose._FROZEN_COLUMNS_0010`` plus the two lineage columns —
copied, not imported (see the module docstring).

**``promising_at`` and ``promising_by`` are deliberately absent.** The freeze
trigger fires ``WHEN (OLD.activated_at IS NOT NULL)``, and the promising marker
is written *after* activation by definition: a version has to run for thirty days
before a scoreboard can call it validada. Freezing it would make the column
unwritable on every row that could ever earn one. What protects it instead is
that only the owner connection may write it at all, and that
:func:`hunter_strategy_worker.replication.mark_promising` never moves an
existing timestamp.

The lineage columns go the other way: a sibling is inserted with them, in the
same statement that sets ``activated_at``, so the trigger never sees that write
— and re-pointing a sibling at a different parent afterwards would silently
re-attribute an experiment whose signals are already on record.
"""

FREEZE_FUNCTION = "shadow_freeze_strategy_version"
UPDATE_TRIGGER = "strategy_versions_freeze_update"
DELETE_TRIGGER = "strategy_versions_freeze_delete"


def _freeze_function_sql() -> str:
    """``ddl.strategy_purpose._freeze_function_sql`` with this revision's list.

    Copied rather than parameterised for the reason in the module docstring: the
    body ``0012`` installs must not change when a later revision edits ``0010``.
    """
    checks = "\n".join(
        f"        IF NEW.{column} IS DISTINCT FROM OLD.{column} THEN "
        f"changed := changed || '{column}'::text; END IF;"
        for column in _FROZEN_COLUMNS_0012
    )
    return f"""
CREATE FUNCTION {FREEZE_FUNCTION}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    DECLARE changed text[] := ARRAY[]::text[];
    BEGIN
        IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION USING
                MESSAGE = 'strategy_versions ' || OLD.id
                    || ' is frozen after activation: an activated version cannot be deleted',
                HINT = 'deprecate it instead; shadow signals point at this row';
        END IF;
{checks}
        IF cardinality(changed) > 0 THEN
            RAISE EXCEPTION USING
                MESSAGE = 'strategy_versions ' || OLD.id
                    || ' is frozen after activation: ' || array_to_string(changed, ', ')
                    || ' cannot change',
                HINT = 'create a new strategy_version; status, changelog, promising_at and '
                    || 'deprecated_at stay mutable';
        END IF;
        RETURN NEW;
    END;
$$
"""


def widen_the_cohort_check() -> None:
    """Accept ``replication:<parent>:<k>``; keep the other two branches identical.

    Dropped and recreated rather than rewritten in place — Postgres has no
    ``ALTER CONSTRAINT`` for a CHECK's expression — and the recreate is
    validating, so a row that somehow already carried an unrepresentable cohort
    would stop the upgrade instead of surviving under a constraint that lies.
    ``shadow_episodes`` is one row per (version, market, cohort): a few thousand
    rows, not a hot path, so the ``ACCESS EXCLUSIVE`` this takes is of the same
    order as ``0010``'s (§15.6).
    """
    op.execute(f"ALTER TABLE shadow_episodes DROP CONSTRAINT {COHORT_CHECK}")
    op.execute(
        f"ALTER TABLE shadow_episodes ADD CONSTRAINT {COHORT_CHECK} "
        f"CHECK (cohort ~ '{COHORT_PATTERN_0012}')"
    )


def narrow_the_cohort_check() -> None:
    """Downgrade: back to exactly the CHECK ``0002_shadow_lab`` describes."""
    op.execute(f"ALTER TABLE shadow_episodes DROP CONSTRAINT {COHORT_CHECK}")
    op.execute(
        f"ALTER TABLE shadow_episodes ADD CONSTRAINT {COHORT_CHECK} "
        f"CHECK (cohort ~ '{COHORT_PATTERN_0002}')"
    )


def add_replication_columns() -> None:
    """The four columns, their two CHECKs, the arm's UNIQUE and the self FK."""
    for name, sql_type in REPLICATION_COLUMNS:
        op.execute(f"ALTER TABLE strategy_versions ADD COLUMN {name} {sql_type}")
    op.execute(
        f"ALTER TABLE strategy_versions ADD CONSTRAINT {LINEAGE_CHECK} CHECK ({_LINEAGE_CHECK_SQL})"
    )
    op.execute(
        f"ALTER TABLE strategy_versions ADD CONSTRAINT {PROMISING_CHECK} "
        f"CHECK ({_PROMISING_CHECK_SQL})"
    )
    op.execute(
        f"ALTER TABLE strategy_versions ADD CONSTRAINT {ARM_UNIQUE} "
        "UNIQUE (replication_parent_id, replication_index)"
    )
    # ``NO ACTION`` (the default), never ``RESTRICT``: NO ACTION is checked at
    # the end of the statement, so ``DELETE FROM strategies`` still cascades a
    # whole family away in one command, while deleting a lone parent that would
    # orphan its siblings is refused. Same choice, same reason, as
    # ``participation_consumptions`` (§18.5). No index is created for it: the
    # UNIQUE above is keyed on ``replication_parent_id`` first and is exactly
    # the index §1 requires of every foreign key.
    op.execute(
        f"ALTER TABLE strategy_versions ADD CONSTRAINT {PARENT_FK} "
        "FOREIGN KEY (replication_parent_id) REFERENCES strategy_versions (id)"
    )


def drop_replication_columns() -> None:
    """Downgrade, in the exact reverse order of :func:`add_replication_columns`."""
    for constraint in (PARENT_FK, ARM_UNIQUE, PROMISING_CHECK, LINEAGE_CHECK):
        op.execute(f"ALTER TABLE strategy_versions DROP CONSTRAINT IF EXISTS {constraint}")
    for name, _sql_type in reversed(REPLICATION_COLUMNS):
        op.execute(f"ALTER TABLE strategy_versions DROP COLUMN {name}")


def replace_strategy_version_freeze() -> None:
    """Widen ``0010``'s freeze trigger to cover the two lineage columns.

    Drop and recreate, never ``CREATE OR REPLACE``, so the function and its two
    triggers stay one object with one history — the shape ``0008`` (§20.3),
    ``0009`` (§21.2) and ``0010`` (§22.2) all used.
    """
    op.execute(f"DROP TRIGGER IF EXISTS {DELETE_TRIGGER} ON strategy_versions")
    op.execute(f"DROP TRIGGER IF EXISTS {UPDATE_TRIGGER} ON strategy_versions")
    op.execute(f"DROP FUNCTION IF EXISTS {FREEZE_FUNCTION}()")
    op.execute(_freeze_function_sql())
    op.execute(
        f"CREATE TRIGGER {UPDATE_TRIGGER} BEFORE UPDATE ON strategy_versions "
        f"FOR EACH ROW WHEN (OLD.activated_at IS NOT NULL) "
        f"EXECUTE FUNCTION {FREEZE_FUNCTION}()"
    )
    op.execute(
        f"CREATE TRIGGER {DELETE_TRIGGER} BEFORE DELETE ON strategy_versions "
        f"FOR EACH ROW WHEN (OLD.activated_at IS NOT NULL) "
        f"EXECUTE FUNCTION {FREEZE_FUNCTION}()"
    )


def restore_purpose_freeze() -> None:
    """Downgrade: call ``0010``'s own creator back.

    Reverting to ``0011`` means having the trigger ``0010`` describes, exactly
    as ``0010``'s downgrade calls ``ddl.shadow``'s (§22.2). It runs **before**
    the columns are dropped, because ``0012``'s body names them and ``0010``'s
    does not.
    """
    from ddl.strategy_purpose import replace_strategy_version_freeze as freeze_0010

    freeze_0010()


def _refuse(sql: str, message: str, hint: str) -> None:
    """Count the offenders and refuse, naming them — §17.7's pattern."""
    safe_message = message.replace("'", "''")
    safe_hint = hint.replace("'", "''")
    op.execute(
        f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
        f"SELECT count(*) INTO offenders FROM ({sql}) AS offending; "
        f"IF offenders > 0 THEN RAISE EXCEPTION USING "
        f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
        f"HINT = '{safe_hint}'; END IF; END $$;"
    )


def refuse_a_downgrade_that_would_lose_a_replication() -> None:
    """§17.7: reversing is allowed, losing evidence is not — three guards.

    Each names a fact that no column left behind can reproduce:

    - a **promising marker** is the instant block 1 of the protocol counts from
      (REPLICATION.md §1.6). It is never recomputed backwards, and the
      ``changelog`` copy only exists on rows that were replicated — a version
      marked promising and not yet replicated would lose it outright;
    - a **lineage** is which arm of whose replication a sibling ran. Dropping
      the columns leaves ten ``research_only`` versions that look like ten
      unrelated experiments, which is precisely the multiple-testing inflation
      the protocol exists to count (REPLICATION.md §2);
    - a **replication cohort** already written to ``shadow_episodes`` would
      violate ``0002``'s narrower CHECK. Postgres would refuse the constraint
      anyway; this refuses first, with the count and the instruction, instead of
      failing halfway through a revision with a constraint-violation error that
      names no way out.

    Nothing is deleted here. Export first, then remove the rows knowing what it
    costs — the same boundary, and the same deliberate lack of a ready-made
    command, as §18.9.
    """
    _refuse(
        "SELECT 1 FROM strategy_versions WHERE promising_at IS NOT NULL",
        "strategy_versions carry a promising_at - the instant the out-of-sample block of "
        "docs/plans/REPLICATION.md counts from, which is never recomputed backwards and is "
        "not derivable from any column that remains",
        "export the affected ids and their promising_at before reversing; a version that was "
        "marked promising and not yet replicated has no other durable copy",
    )
    _refuse(
        "SELECT 1 FROM strategy_versions WHERE replication_parent_id IS NOT NULL",
        "strategy_versions carry a replication parent - dropping the columns turns a "
        "replication family into unrelated research versions, which is exactly the "
        "multiple-testing inflation the protocol exists to count",
        "export the affected ids with their replication_parent_id and replication_index "
        "before reversing; the changelog label is the only copy that survives, and it is "
        "prose",
    )
    _refuse(
        "SELECT 1 FROM shadow_episodes WHERE cohort LIKE 'replication:%'",
        "shadow_episodes carry a replication cohort - 0002's narrower CHECK cannot "
        "represent it, so restoring the constraint would fail on these rows",
        "export the affected episodes and decide what happens to the trackings they hold "
        "before reversing; deleting an episode releases a tracking_hold on a market whose "
        "candles an open outcome still needs",
    )
