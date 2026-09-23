"""meme decision tapes: what the event lane saw at the instant it decided

Revision ID: 0062_meme_decision_tapes
Revises: 0061_spot_desk_r71

T4.89 (Everton, 23/09/2026 17:5x BRT: "arruma esse erro, o motivo de não ter
visto na hora exata da compra"). R73 found that the event lane's WS tape is
never persisted and ``meme_trades`` is a polling copy ~44 s late, so no study
can rebuild what the desk knew at the decision. **One new table**,
``meme_decision_tapes``, everything in ``ddl/meme_decision_tapes.py``: no
column on an existing table, no view, no enum, no RLS policy, no partition
(retention is row-wise, §64 of ``docs/DATABASE.md``).

**Chain note.** ``0061_spot_desk_r71`` (R71, commit ``017d4b3b``) was the
highest revision in the tree when this was written; this lands on it, keeping
``head`` linear.

Upgrade guard: none, and that is an assertion — the table is new. The
downgrade refuses while a row exists (§17.7). **Named
``0062_meme_decision_tapes`` (24 characters)** — ``VARCHAR(32)`` (§17.6).

Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_decision_tapes import (
    create_meme_decision_tapes,
    drop_meme_decision_tapes,
    grant_meme_decision_tapes_privileges,
    refuse_a_downgrade_that_would_lose_the_decision_tapes,
)

revision: str = "0062_meme_decision_tapes"
down_revision: str | None = "0061_spot_desk_r71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_decision_tapes()
    grant_meme_decision_tapes_privileges()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_the_decision_tapes()
    drop_meme_decision_tapes()
