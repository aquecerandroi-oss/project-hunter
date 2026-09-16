"""meme tokens creator index: the pedigree counts stop scanning the table (T4.24b hotfix)

Revision ID: 0040_meme_tokens_creator_index
Revises: 0039_meme_creator_repeat

The prior-coin counts of ``0039``'s repeat-dumper exclusion scanned ``meme_tokens``
per judged mint and killed the Lab loop on the statement timeout (deploy
``8293c2b``, 15/09/2026 19:1x BRT). This adds ``(creator, created_at)`` (partial,
non-null); the loop also bounds the counts to 7 days and reads them in a
savepoint with its own 8 s timeout. Everything is in
``ddl/meme_tokens_creator_index.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_tokens_creator_index import add_creator_index, drop_creator_index

revision: str = "0040_meme_tokens_creator_index"
down_revision: str | None = "0039_meme_creator_repeat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_creator_index()


def downgrade() -> None:
    drop_creator_index()
