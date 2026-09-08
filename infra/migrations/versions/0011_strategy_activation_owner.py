"""strategy_versions: hunter_worker can no longer activate, deprecate or delete a row

Eleventh revision. Closes the gap security review T3.15 MEDIUM 4 and
database-architect review A4 both found from opposite sides: ``0010`` protects
``purpose`` (the wallet label) once a version is activated, but the freeze
trigger only fires on an already-activated row (``WHEN (OLD.activated_at IS
NOT NULL)``). Before that, the table-level ``UPDATE``/``DELETE``
``0001_initial_schema`` gave ``hunter_worker`` still let it activate a
``draft`` row derived by ``activate_strategy_version.py --paper-line`` (with no
audit line, no ``--changelog`` and no decision behind it) or delete it
outright. Every production query against this table as ``hunter_worker`` is a
``SELECT`` (``catalogue.py``, ``replay/load.py``, ``metrics.py``,
``bridge_repo.py``); the only writers run on the owner connection
(``DATABASE_URL_MIGRATIONS``): ``infra/scripts/activate_strategy_version.py``,
``infra/scripts/seed.py`` and ``paper_line.py``.

Revokes, for ``hunter_worker``: ``UPDATE`` on ``status``, ``activated_at``,
``deprecated_at``, ``code_ref``, ``parameters_schema``, ``default_parameters``,
``params_format``; ``DELETE`` on the whole table; ``INSERT`` outright (nothing
inserts as this role). What survives is ``UPDATE`` on ``id``, ``strategy_id``,
``version``, ``changelog``, ``created_at`` — the five columns of ``0010``'s
twelve-column grant this revision does not touch, none of them written by
production code either, kept because narrowing them is not a finding either
review made.

Grants only — no ``ACCESS EXCLUSIVE``, no table rewrite, no downgrade guard:
reversing this revision loses no data, it only regrants what ``0001``/``0010``
already gave. Described in ``docs/DATABASE.md`` section 23.

**Named ``0011_strategy_activation_owner`` (30 characters)** —
``alembic_version.version_num`` is ``VARCHAR(32)`` (section 17.6).

Revision ID: 0011_strategy_activation_owner
Revises: 0010_strategy_purpose
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.strategy_activation_owner import restore_worker_activation, revoke_worker_activation

revision: str = "0011_strategy_activation_owner"
down_revision: str | None = "0010_strategy_purpose"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    revoke_worker_activation()


def downgrade() -> None:
    restore_worker_activation()
