"""``0064_meme_tokens_symbol_index`` — the index ``symbol_dup_24h`` never had.

``lab_repo_fast._PEDIGREE`` counts, per judged mint, the coins with the same
ticker created in the 24 h before it (``o.symbol = t.symbol AND o.created_at``
in the window). ``meme_tokens`` had no index on ``symbol``: the planner walked
``ix_meme_tokens_created_at`` over the whole 24 h window and filtered on the
ticker. Measured on the VPS on 24/09/2026 (360 283 rows, ``EXPLAIN (ANALYZE,
BUFFERS)``, read-only): **31.4 ms per judged mint, 32 687 rows discarded each,
10.3 s of the 14.0 s** a 329-mint read took, 15.5 M buffers; the savepoint's
own 8 s timeout cut it (``meme_pedigree_read_failed``). ``(symbol,
created_at)``, partial on the two non-null columns like ``0040``'s creator
index (the strict ``=`` proves ``symbol IS NOT NULL``; the query already says
``created_at IS NOT NULL``), makes each count an index range.

**Built ``CONCURRENTLY``, so the upgrade is not atomic** (§17.5, ``0004``'s
recipe): ``meme_tokens`` is the radar's write path (~40 k inserts/day plus the
lifecycle updates), and a plain ``CREATE INDEX`` holds ``SHARE`` for the whole
build, blocking every insert and update of the ingest while it scans the
table. Neither concurrent command may run in a transaction block, so the
upgrade opens an ``autocommit_block`` (the downgrade does not — see
:func:`drop_symbol_index`). A crash mid-build can leave an
``indisvalid = false`` index under the final name, and ``CREATE INDEX IF NOT
EXISTS`` would then keep it; so the upgrade drops the name first — **rerunning
the revision is the recovery**, idempotent over a finished run too.
"""

from __future__ import annotations

from alembic import op

INDEX = "ix_meme_tokens_symbol_created_at"


def add_symbol_index() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
        op.execute(
            f"CREATE INDEX CONCURRENTLY {INDEX} ON meme_tokens (symbol, created_at) "
            "WHERE symbol IS NOT NULL AND created_at IS NOT NULL"
        )


def drop_symbol_index() -> None:
    """A plain, **transactional** drop — not ``CONCURRENTLY``. ``env.py`` runs a
    whole ``alembic downgrade`` in one transaction, and a downgrade that starts
    here and is refused further down (``0059``'s guard) must roll the drop back
    with everything else; a committed concurrent drop left the database at
    ``0064`` with no index behind it. The price is ``ACCESS EXCLUSIVE`` on
    ``meme_tokens`` held until the **whole** downgrade run commits (every
    revision reversed after this one included) — an operator's step, never a
    deploy's."""
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
