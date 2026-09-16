"""``0040_meme_tokens_creator_index`` — the index the pedigree counts needed (T4.24b).

``lab_repo_fast._PEDIGREE`` counts, per judged mint, the creator's prior coins
(``meme_tokens o WHERE o.creator = t.creator AND o.created_at <= t.created_at``).
``meme_tokens`` had indexes on ``created_at`` and ``first_seen_at`` only: every
count was a sequential scan of ~105 k rows, ~130 times per 15-second tick, and the
Lab loop died on the statement timeout right after deploy ``8293c2b`` (11 restarts
in 6 minutes). ``(creator, created_at)`` makes each count an index range.
"""

from __future__ import annotations

from alembic import op

INDEX = "ix_meme_tokens_creator_created_at"


def add_creator_index() -> None:
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX} ON meme_tokens (creator, created_at) "
        "WHERE creator IS NOT NULL AND created_at IS NOT NULL"
    )


def drop_creator_index() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
