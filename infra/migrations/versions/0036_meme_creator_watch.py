"""meme creator watch: the creator's sale seen on the chain, on the paper bet (T4.2h)

Revision ID: 0036_meme_creator_watch
Revises: 0035_meme_organic_e3

``creator_dump`` was the exit of 22 of the 35 measured paper closes of
12/09/2026, on average 14 minutes after the entry — the tape reports the sale
late. The worker now reads the creator's token accounts every 15 s for the
mints it holds and stamps the first decrease on the open bets
(``creator_sold_seen_at``, ``creator_sold_fraction``); a creator with no token
account is ``creator_balance_reason = creator_ata_missing``. Everything is in
``ddl/meme_creator_watch.py``; the downgrade refuses while a bet carries a
seen sale.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_creator_watch import (
    add_creator_watch_columns,
    drop_creator_watch_columns,
    refuse_a_downgrade_that_would_lose_a_creator_sale,
)

revision: str = "0036_meme_creator_watch"
down_revision: str | None = "0035_meme_organic_e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_creator_watch_columns()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_a_creator_sale()
    drop_creator_watch_columns()
