"""feature_baselines: hunter_worker may take the row lock §17.2 asks it to take

One statement: ``GRANT UPDATE ON feature_baselines TO hunter_worker``.

``0003`` withheld it on purpose — the class in ``ddl/analysis.py`` is
``SELECT``/``INSERT``/``DELETE`` and "no ``UPDATE`` for anyone" — but the
retention protocol of DATABASE.md §17.2 has the baseline writer take
``SELECT ... WHERE id = ANY(...) FOR SHARE`` before referencing a revision, and
the retention job take ``FOR UPDATE`` before deleting one; those two row locks
over the same row are the whole of the mutual exclusion. PostgreSQL requires the
``UPDATE`` privilege to take *any* row lock, so on a correctly migrated database
the writer's first statement failed with *permission denied*. T2.5 reported it
as BUG-1: the scanner probes at startup, logs at ``error`` and degrades to a
plain existence check, which still refuses to write a sample whose baseline
vanished but no longer serialises that write against a concurrent retention
``DELETE``.

**The immutability is the trigger, not the grant.** ``feature_baselines_immutable``
(``BEFORE UPDATE OR DELETE ... FOR EACH ROW``, installed by ``0003``) raises on
every ``UPDATE`` for every role, the table owner included — which is strictly
more than a ``REVOKE`` could ever promise, since no revoke reaches the owner.
This revision therefore does not make a baseline revision editable by anybody;
it hands over the one capability the trigger cannot express, the row lock. The
two-locks-on-one-door claim in §17.2/§17.6 is corrected accordingly: it was one
lock on the door and one on the door frame.

Grant only — no table, column, index, constraint or type changes — so
``alembic check`` sees nothing here either way, and ``downgrade()`` revokes the
single privilege and leaves ``0003``'s class exactly as it was.

**Named ``0005_baseline_lock_grant``, not ``0005_feature_baselines_lock_grant``**
(the name the T2.5 note asks for), because ``alembic_version.version_num`` is
``VARCHAR(32)`` and the longer id is 33 characters: the upgrade reached the
final stamp and failed with *value too long for type character varying(32)*,
after every statement of the revision had run. 32 characters is the budget for
every revision id from here on.

Revision ID: 0005_baseline_lock_grant
Revises: 0004_outbox_pending_index
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.baseline_lock import BASELINE_LOCK_TABLES_0005, grant_row_lock, revoke_row_lock

revision: str = "0005_baseline_lock_grant"
down_revision: str | None = "0004_outbox_pending_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    grant_row_lock(BASELINE_LOCK_TABLES_0005)


def downgrade() -> None:
    revoke_row_lock(BASELINE_LOCK_TABLES_0005)
