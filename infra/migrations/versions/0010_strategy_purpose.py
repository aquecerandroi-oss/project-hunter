"""strategy_versions.purpose: the wallet a signal may reach, named on the version

Tenth revision. T3.15/D10 — the label the producer crava'd
(``PURPOSE_RESEARCH_ONLY``) and the label the two consumers demand (``live``)
have exactly one gap between them, and it was never a row value: it was a
missing column. ``strategy_versions.purpose text NOT NULL DEFAULT
'research_only'`` closes it, with a CHECK naming the three admissible labels
(``research_only`` | ``paper`` | ``live``) and the same freeze-on-first-activation
trigger ``0002_shadow_lab`` built for ``code_ref`` — widened, not duplicated
(``ddl.strategy_purpose`` replaces the trigger's body the same way
``0009_paper_geometry`` replaced ``0007``'s request-guard body).

Described in DATABASE.md section 22.

**There is no upgrade guard, and that is an assertion**: every existing row is,
and has only ever been, ``research_only`` (D10's own finding — the label
``paper`` "does not exist in the code" as of this task), so the default
backfills what is already honestly true. No `0002`/`0003`/`0006`-style invariant
is created over data that already violates it.

**The downgrade refuses** (section 17.7's boundary) when a row carries a purpose
other than ``research_only`` — dropping the column would erase the one thing
that told a paper-wallet coorte apart from shadow evidence, and that is not
recoverable from anything that remains. Nothing is ever activated by this
migration; it only makes the label representable.

**Named ``0010_strategy_purpose`` (20 characters)** - ``alembic_version.version_num``
is ``VARCHAR(32)`` (section 17.6).

Revision ID: 0010_strategy_purpose
Revises: 0009_paper_geometry
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.strategy_purpose import (
    add_purpose_column,
    drop_purpose_column,
    refuse_a_downgrade_that_would_lose_a_purpose,
    replace_strategy_version_freeze,
    restore_purpose_write,
    restore_shadow_freeze,
    revoke_purpose_write,
)

revision: str = "0010_strategy_purpose"
down_revision: str | None = "0009_paper_geometry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_purpose_column()
    replace_strategy_version_freeze()
    revoke_purpose_write()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_purpose()
    restore_purpose_write()
    restore_shadow_freeze()
    drop_purpose_column()
