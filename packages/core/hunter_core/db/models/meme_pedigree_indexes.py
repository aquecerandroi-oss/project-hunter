"""``meme_tokens``'s two pedigree indexes — split out of ``meme.py`` for the
350-line budget, the cut ``meme_social_checks.py`` took. Spread into
``MemeToken.__table_args__``; the revisions own the DDL (``0040``, ``0064``).

Both serve ``lab_repo_fast._PEDIGREE``'s correlated counts, and both were
added after the count had killed or starved the Lab loop on a measured plan:
``(creator, created_at)`` on 15/09/2026 (each count scanned ~105 k rows, 373
restarts), ``(symbol, created_at)`` on 24/09/2026 (``symbol_dup_24h`` walked
the whole 24 h of ``ix_meme_tokens_created_at``: 10.3 s of a 14.0 s read of
329 mints, past the 8 s timeout).
"""

from __future__ import annotations

from sqlalchemy import Index, text

PEDIGREE_INDEXES: tuple[Index, ...] = (
    Index(
        "ix_meme_tokens_creator_created_at",
        "creator",
        "created_at",
        postgresql_where=text("creator IS NOT NULL AND created_at IS NOT NULL"),
    ),
    Index(
        "ix_meme_tokens_symbol_created_at",
        "symbol",
        "created_at",
        postgresql_where=text("symbol IS NOT NULL AND created_at IS NOT NULL"),
    ),
)
