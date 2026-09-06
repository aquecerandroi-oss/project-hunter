"""The row lock the baseline writer needs — DATABASE.md §17.2/§17.6.

``0003`` gave ``hunter_worker`` ``SELECT``/``INSERT``/``DELETE`` on
``feature_baselines`` and **no ``UPDATE`` for anyone**, describing that as "two
independent locks on the same door" next to the ``feature_baselines_immutable``
trigger. One of those two locks was bolted to the wrong door.

The retention protocol of §17.2 is mutual exclusion *per row*: before writing an
envelope the scorer takes ``SELECT ... FROM feature_baselines WHERE id =
ANY(...) FOR SHARE`` and revalidates that the revisions are still there, and the
retention job takes ``FOR UPDATE`` on the candidate before deleting it. The two
row locks on the same row are what serialise "the job proves nobody references
B" against "a scorer with B in cache writes the envelope". PostgreSQL requires
the **``UPDATE`` privilege** to take any row lock (``ACL_SELECT_FOR_UPDATE`` is
``ACL_UPDATE``; a column-level grant does not satisfy it, because a row mark
carries no updated columns), so on a correctly migrated database the writer's
first statement failed with *permission denied* — reported by T2.5 as BUG-1,
which degraded the scanner to a plain existence check and gave up the
serialisation against a concurrent retention ``DELETE``.

So the grant goes in, and **the immutability lives in the trigger, not in the
grant.** That is not a weakening: ``feature_baselines_immutable`` is a
``BEFORE UPDATE OR DELETE ... FOR EACH ROW`` trigger that raises on *every*
``UPDATE``, for every role, the table owner included — a privilege that
``REVOKE`` never reached and that no grant can hand out. What the missing grant
was actually blocking was the lock, i.e. the one part of the protocol the
trigger cannot express.

Frozen per revision like every other grant list (``ddl/tables.py`` as of
``0001``, ``ddl/shadow.py`` as of ``0002``, ``ddl/analysis.py`` as of ``0003``):
``ANALYSIS_WORKER_APPEND_TABLES`` keeps describing the schema ``0003`` built,
and ``BASELINE_LOCK_TABLES_0005`` is this revision's own tuple. A later table
that needs the same treatment brings its own.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import WORKER_ROLE

LOCK_PRIVILEGE = "UPDATE"
"""What PostgreSQL demands for ``FOR SHARE``/``FOR UPDATE``, not what it means.

Named so the revision reads as what it does. The privilege is granted for its
locking effect only; the write it nominally authorises is refused row by row by
``feature_baselines_immutable``.
"""

BASELINE_LOCK_TABLES_0005: tuple[str, ...] = ("feature_baselines",)
"""The tables ``0005`` hands the row lock over. Frozen; it never grows."""

__all__ = [
    "BASELINE_LOCK_TABLES_0005",
    "LOCK_PRIVILEGE",
    "grant_row_lock",
    "revoke_row_lock",
]


def grant_row_lock(tables: tuple[str, ...]) -> None:
    """``GRANT UPDATE`` to ``hunter_worker`` — table level, the only level that works.

    ``GRANT UPDATE (some_column)`` would pass a reading of the docs and fail in
    the executor: a row mark records no updated columns, so the column-level
    path is skipped and the check falls through to a table-level
    ``pg_class_aclcheck``.
    """
    for table in tables:
        op.execute(f"GRANT {LOCK_PRIVILEGE} ON {table} TO {WORKER_ROLE}")


def revoke_row_lock(tables: tuple[str, ...]) -> None:
    """Give back exactly the one privilege, leaving ``0003``'s class intact.

    Not ``REVOKE ALL``: that is ``0003``'s job in its own downgrade, and doing it
    here would leave a database rolled back to ``0004`` without the
    ``SELECT``/``INSERT``/``DELETE`` the worker has had since ``0003``.
    """
    for table in tables:
        op.execute(f"REVOKE {LOCK_PRIVILEGE} ON {table} FROM {WORKER_ROLE}")
