"""``0011_strategy_activation_owner`` — closing the lifecycle hole ``0010`` left.

Security review T3.15 MEDIUM 4 and database-architect review A4
(``.claude/state/review-T3.15-security.md``, ``.claude/state/review-T3.15-db.md``):
``0010`` protected the *label* (``purpose``) from ``hunter_worker``, but the
freeze trigger only fires ``WHEN (OLD.activated_at IS NOT NULL)``. A ``draft``
row — exactly the shape ``activate_strategy_version.py --paper-line`` derives,
waiting for the seven conditions of D10 — has ``activated_at IS NULL``, so the
table-level ``UPDATE``/``DELETE`` ``0001`` gave ``hunter_worker`` still let it
**activate** that row (``UPDATE ... SET status = 'active', activated_at =
now()``) or **delete** it outright, with no line in ``system_events``, no
``--changelog`` and no decision behind it. Both reviews measured the same fact
from the other side: no production query run as ``hunter_worker`` does
anything but ``SELECT`` against ``strategy_versions``
(``catalogue.py``, ``replay/load.py``, ``metrics.py``, ``bridge_repo.py`` — all
reads). The only writers are the owner connection
(``DATABASE_URL_MIGRATIONS``): ``infra/scripts/activate_strategy_version.py``
and ``infra/scripts/seed.py``, and the strategy-worker's own
``paper_line.py``, which the db review confirmed also runs on the owner
connection, not as ``hunter_worker``.

**What this revision revokes.** Exactly the columns a lifecycle write needs and
nothing declared safe by omission: ``status``/``activated_at``/``deprecated_at``
(the activate/deprecate cycle) and ``code_ref``/``parameters_schema``/
``default_parameters``/``params_format`` (the version's identity — the same
four the freeze trigger already protects *after* activation; this closes the
gap *before* it). ``DELETE`` is revoked outright — there is no partial DELETE.
``INSERT`` is revoked outright too: the db review found nothing that inserts as
``hunter_worker`` (``seed.py`` and ``paper_line.py`` both use the owner
connection), so keeping it would be a privilege granted on the theory that
something might one day use it, which is exactly what ``0001``'s original
table-level grant already was.

**What survives.** ``UPDATE`` on ``id``, ``strategy_id``, ``version``,
``changelog``, ``created_at`` — the five columns of
``ddl.strategy_purpose.WORKER_COLUMNS_EXCEPT_PURPOSE`` this revision does not
touch. None of them is written by production code as ``hunter_worker`` either,
but narrowing them is not a finding either review made, and a revocation earns
the same evidence bar a grant does
(``test_the_worker_cannot_update_purpose_but_keeps_every_other_column`` already
proves ``changelog`` survives a narrowing pass — this revision must not break
that proof).

No guard on downgrade: unlike ``0010``'s column drop, reversing this revision
loses no data — it only regrants what ``0001``/``0010`` already gave, so the
downgrade is the plain mirror of the upgrade.

Named ``0011_strategy_activation_owner`` (30 characters, well under the 32
the previous revision's docstring miscounted its own name against, see
``docs/DATABASE.md`` §22 and §23).
"""

from __future__ import annotations

from alembic import op

from ddl.strategy_purpose import WORKER_COLUMNS_EXCEPT_PURPOSE
from hunter_core.db.models import WORKER_ROLE

REVOKED_LIFECYCLE_COLUMNS: tuple[str, ...] = (
    "status",
    "activated_at",
    "deprecated_at",
    "code_ref",
    "parameters_schema",
    "default_parameters",
    "params_format",
)
"""The activate/deprecate cycle and the version's identity — everything the
freeze trigger already protects *after* the first activation, now also out of
``hunter_worker``'s reach *before* it."""

REMAINING_WORKER_UPDATE_COLUMNS: tuple[str, ...] = tuple(
    column for column in WORKER_COLUMNS_EXCEPT_PURPOSE if column not in REVOKED_LIFECYCLE_COLUMNS
)
"""``id``, ``strategy_id``, ``version``, ``changelog``, ``created_at`` — what is
left of ``0010``'s twelve-column grant once :data:`REVOKED_LIFECYCLE_COLUMNS`
is taken out. Computed, not retyped, so the two lists can never silently drift
apart."""


def revoke_worker_activation() -> None:
    """``hunter_worker`` keeps ``SELECT``; every write that could activate,
    deprecate or delete a version is gone."""
    revoked = ", ".join(REVOKED_LIFECYCLE_COLUMNS)
    inserted = ", ".join(WORKER_COLUMNS_EXCEPT_PURPOSE)
    op.execute(f"REVOKE UPDATE ({revoked}) ON strategy_versions FROM {WORKER_ROLE}")
    op.execute(f"REVOKE INSERT ({inserted}) ON strategy_versions FROM {WORKER_ROLE}")
    op.execute(f"REVOKE DELETE ON strategy_versions FROM {WORKER_ROLE}")


def restore_worker_activation() -> None:
    """Downgrade: put back exactly what ``0010`` had granted."""
    inserted = ", ".join(WORKER_COLUMNS_EXCEPT_PURPOSE)
    revoked = ", ".join(REVOKED_LIFECYCLE_COLUMNS)
    op.execute(f"GRANT DELETE ON strategy_versions TO {WORKER_ROLE}")
    op.execute(f"GRANT INSERT ({inserted}) ON strategy_versions TO {WORKER_ROLE}")
    op.execute(f"GRANT UPDATE ({revoked}) ON strategy_versions TO {WORKER_ROLE}")
