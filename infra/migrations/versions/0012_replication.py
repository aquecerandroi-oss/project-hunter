"""the replication cohort, promising_at and a sibling's lineage exist in the schema

Twelfth revision. Closes the two pendencies T3.19 declared in
``.claude/state/notes-T3.19.md`` (CONCERNS 1 and 2), plus one it did not name:

(a) **the cohort.** ``ck_shadow_episodes_cohort_format`` accepted ``prospective``
    and ``replay:<uuid>`` and nothing else, so a replication sibling emitted its
    signals as ``prospective`` — the one cohort the execution bridge admits
    (T3.15e). The bridge has been ready for the label since then, naming "a
    replication sibling's cohort" in its own refusal; what was missing was the
    schema. The CHECK now also accepts ``replication:<parent_version_id>:<k>``,
    ``k`` in 1..99, with the other two branches byte-identical.

(b) **``promising_at`` + ``promising_by``.** The instant a version was first
    called ``validada`` decided where block 1 of the protocol starts counting,
    and it lived in the siblings' ``changelog`` and in a ``system_events`` row
    that retention deletes at 30 days — for a block that needs 15 distinct
    decision *days* after it. Now a column, written only by the owner
    connection, with ``promising_by`` naming the verdict that wrote it.

(c) **the lineage.** ``replication_parent_id`` and ``replication_index``, with
    ``CHECK (parent IS NULL) = (index IS NULL)``, ``1 <= index <= 99``,
    ``parent IS DISTINCT FROM id``, and ``UNIQUE (parent, index)``. Whose
    sibling and which arm stop being a regex over free text.

**No grant.** ``0010`` and ``0011`` between them left ``hunter_worker`` with a
table-level ``SELECT`` and ``UPDATE`` on five named columns, so a column added
here is readable by both roles and writable by neither — the shape ``purpose``
has, reached by subtraction. Proven as the role in
``test_schema_privileges.py``, not declared here (``ddl/replication.py``'s
docstring says why a no-op ``REVOKE`` would be worse than nothing).

**No upgrade guard, and that is an assertion.** Four nullable columns with no
default, one CHECK that only speaks about non-null values, one widened CHECK
that accepts a strict superset of what it accepted before. Nothing already
stored becomes unrepresentable — the same assertion ``0009`` (§21.4) and
``0010`` (§22.1) make.

**The downgrade refuses** on three counts (§17.7: reversing is allowed, losing
evidence is not): any ``promising_at``, any ``replication_parent_id``, any
``shadow_episodes`` row on a replication cohort.

**Named ``0012_replication`` (17 characters)** — ``alembic_version.version_num``
is ``VARCHAR(32)`` (§17.6). Described in ``docs/DATABASE.md`` §24.

Revision ID: 0012_replication
Revises: 0011_strategy_activation_owner
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.replication import (
    add_replication_columns,
    drop_replication_columns,
    narrow_the_cohort_check,
    refuse_a_downgrade_that_would_lose_a_replication,
    replace_strategy_version_freeze,
    restore_purpose_freeze,
    widen_the_cohort_check,
)

revision: str = "0012_replication"
down_revision: str | None = "0011_strategy_activation_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    widen_the_cohort_check()
    add_replication_columns()
    replace_strategy_version_freeze()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``.

    ``restore_purpose_freeze`` runs *before* the columns are dropped: ``0012``'s
    trigger body names them and ``0010``'s does not, so reverting the body first
    is what keeps the drop from leaving a function pointing at columns that no
    longer exist (the same ordering ``0009``'s downgrade needed, §21.2).
    """
    refuse_a_downgrade_that_would_lose_a_replication()
    restore_purpose_freeze()
    drop_replication_columns()
    narrow_the_cohort_check()
