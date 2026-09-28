"""meme token state history: completed_at/migrated_at as known at any instant

Revision ID: 0067_meme_token_state_history
Revises: 0066_meme_mature_opportunities

EXP-M26 J (Astra's must-fix 2, ``docs/DATABASE.md`` §70): **one new table**,
``meme_token_state_history``, filled only by two deferred ``CONSTRAINT TRIGGER``s
on ``meme_tokens`` (a row born with ``completed_at``/``migrated_at``, and every
effective change of either), written and stamped at commit through a ``SECURITY
DEFINER`` function — neither role holds ``INSERT`` — everything in
``ddl/meme_token_state_history.py``.
No column on an existing table, no view, no enum, no RLS policy (global, §1.1),
no partition; retention is the token's (``ON DELETE CASCADE``). No backfill: a
value set before this revision has no honest ``recorded_at``, and the reading
says so (``current_row_pre_history``).

Deploy **before** the EXP-M26 seed (``0068``): the history must exist before T0.

Upgrade guard: none, and that is an assertion — the table is new; the two
``CREATE CONSTRAINT TRIGGER`` take ``SHARE ROW EXCLUSIVE`` on ``meme_tokens`` for an
instant (waits for in-flight upserts; ``pg_dump``'s ``ACCESS SHARE`` does not
conflict). The downgrade refuses while a row exists (§17.7). **Named
``0067_meme_token_state_history`` (29 characters)** — ``VARCHAR(32)`` (§17.6).

Create Date: 2026-09-27
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_token_state_history import (
    create_meme_token_state_history,
    drop_meme_token_state_history,
    grant_meme_token_state_history_privileges,
    refuse_a_downgrade_that_would_lose_a_state_change,
)

revision: str = "0067_meme_token_state_history"
down_revision: str | None = "0066_meme_mature_opportunities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_token_state_history()
    grant_meme_token_state_history_privileges()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_a_state_change()
    drop_meme_token_state_history()
