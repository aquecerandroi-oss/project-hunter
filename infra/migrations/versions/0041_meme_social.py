"""meme social: the identity pump.fun already carries, and the event that may pump it (T4.26)

Revision ID: 0041_meme_social
Revises: 0040_meme_tokens_creator_index

Eleven columns on ``meme_tokens`` (``twitter``, ``telegram``, ``website``,
``description``, ``twitter_kind``, ``twitter_post_id``, ``twitter_post_at``,
``twitter_reuse_count``, ``twitter_reuse_observed_at``, ``social_observed_at``,
``social_source``) — nine written once, two mutable — plus ``meme_events``
(the "may pump" announcement, mint optional at birth), ``meme_proposals.
event_id`` and the seeded ``event_v0/1`` (research, EXP-M8). Everything is in
``ddl/meme_social.py``, ``ddl/meme_social_checks.py`` and ``ddl/meme_events.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_events import (
    create_meme_events_table,
    drop_meme_events_table,
    grant_meme_events_privileges,
    refuse_a_downgrade_that_would_lose_an_event,
    refuse_a_downgrade_that_would_orphan_an_event_v0_row,
    seed_event_v0,
    unseed_event_v0,
)
from ddl.meme_social import (
    add_social_checks,
    add_social_columns,
    create_meme_token_guards_0041,
    create_social_view,
    drop_social_checks,
    drop_social_columns,
    refuse_a_downgrade_that_would_lose_a_social_read,
    restore_meme_token_guards_0024,
    restore_radar_view_0024,
)

revision: str = "0041_meme_social"
down_revision: str | None = "0040_meme_tokens_creator_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_social_columns()
    add_social_checks()
    create_meme_token_guards_0041()
    create_social_view()
    create_meme_events_table()
    grant_meme_events_privileges()
    seed_event_v0()


def downgrade() -> None:
    """Refuse first, in both directions, then unwind in reverse."""
    refuse_a_downgrade_that_would_orphan_an_event_v0_row()
    unseed_event_v0()
    refuse_a_downgrade_that_would_lose_an_event()
    drop_meme_events_table()
    refuse_a_downgrade_that_would_lose_a_social_read()
    restore_radar_view_0024()
    restore_meme_token_guards_0024()
    drop_social_checks()
    drop_social_columns()
