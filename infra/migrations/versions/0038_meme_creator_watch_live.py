"""meme creator watch: the creator's sale seen on the chain, on the real position (T4.2h-b)

Revision ID: 0038_meme_creator_watch_live
Revises: 0037_meme_e1_arms_3_4

``0036`` gave the paper bet three columns for the creator's sale read straight
from the chain every 15 s; the real position (``meme_live_positions``, T4.14)
still learned of the dump from the minute tape, which is the 14-minute delay
that cost 22 of the 35 measured closes of 12/09/2026. This revision gives the
real position **the same three columns, with the same names and the same
CHECKs** (``ddl/meme_creator_watch.py``): one watch loop writes both, one query
measures ``exit_at − creator_sold_seen_at`` on either side, and the executor's
exit loop reads ``creator_sold_seen_at`` on its own 5 s tick.

No grant moves: ``hunter_worker`` already holds ``SELECT, INSERT, UPDATE`` on
the table (``0028``) and ``hunter_app`` keeps its two ``sell_requested_*``
columns and nothing else. The downgrade refuses while a position carries a seen
sale — the latency this task exists to measure is evidence (§17.7).
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_creator_watch import (
    add_creator_watch_live_columns,
    drop_creator_watch_live_columns,
    refuse_a_downgrade_that_would_lose_a_live_creator_sale,
)

revision: str = "0038_meme_creator_watch_live"
down_revision: str | None = "0037_meme_e1_arms_3_4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_creator_watch_live_columns()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_a_live_creator_sale()
    drop_creator_watch_live_columns()
