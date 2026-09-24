"""meme tokens symbol index: the ticker-clone count stops walking 24 h of tokens

Revision ID: 0064_meme_tokens_symbol_index
Revises: 0063_meme_pullback_entry_arm

``symbol_dup_24h`` in ``lab_repo_fast._PEDIGREE`` had no index on ``symbol``
and was 10.3 s of a 14.0 s pedigree read of 329 mints on the VPS (24/09/2026),
past the savepoint's 8 s timeout. This adds ``(symbol, created_at)`` (partial,
non-null), built ``CONCURRENTLY`` — the upgrade is not atomic, rerunning it is
the recovery; the downgrade is a plain drop inside the run's transaction.
Everything is in ``ddl/meme_tokens_symbol_index.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_tokens_symbol_index import add_symbol_index, drop_symbol_index

revision: str = "0064_meme_tokens_symbol_index"
down_revision: str | None = "0063_meme_pullback_entry_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_symbol_index()


def downgrade() -> None:
    drop_symbol_index()
