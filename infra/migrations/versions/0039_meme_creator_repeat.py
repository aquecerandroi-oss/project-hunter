"""meme creator repeat: flow_v2/5 and operator/5 refuse a creator with a prior dump (T4.24)

Revision ID: 0039_meme_creator_repeat
Revises: 0038_meme_creator_watch_live

Measured in the VPS database (176 apostas de papel, 15/09/2026): of the 89
bets whose creator had a prior coin in our own database, the 31 where that
creator had **already sold** on an earlier coin
(``meme_features_1m.creator_sold``, the chain watch's
``creator_sold_seen_at`` or one of our own bets exiting ``creator_dump``)
paid R mean −0,168 against −0,140 elsewhere, 26 of 85 ``creator_dump`` exits
and only 4 winners (13 % against 19 %). This revision seeds the second arm —
``flow_v2/5`` (research, EXP-M6, prediction ``descartar``) and ``operator/5``
(the desk) — both ``flow_v2/2``/``operator/4``'s params plus
``pedigree_repeat_dumper: true``, retiring ``operator/4``. ``flow_v2/1`` and
``flow_v2/2`` stay active for the comparison. Everything is in
``ddl/meme_creator_repeat.py``; the downgrade refuses while a proposal or a
bet references either seeded set (§17.7) and revives ``operator/4``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_creator_repeat import (
    refuse_a_downgrade_that_would_orphan_a_repeat_dumper_row,
    seed_creator_repeat,
    unseed_creator_repeat,
)

revision: str = "0039_meme_creator_repeat"
down_revision: str | None = "0038_meme_creator_watch_live"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_creator_repeat()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_repeat_dumper_row()
    unseed_creator_repeat()
