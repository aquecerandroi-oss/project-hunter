"""replay_runs: a slice is a window and the markets it visited

Eighteenth revision. **One column, one trigger, one key swapped.** No table, no
enum, no index of its own, no partition, no ``GRANT``, no RLS policy.

It closes concern 1 of ``.claude/state/notes-T3.62.md``: ``uq_replay_runs_slice``
was ``(run_id, window_from, window_to)`` and the writer inserts with
``ON CONFLICT ... DO NOTHING``, so four market slices of the *same* window under
one cohort produced **one** receipt and three silent discards. Measured: 32 runs
of a 16-market family left **8 rows**, and ``replay_runs`` reported ``mkts = 4,
bars = 5760, signals = 11`` for work that was 16 markets, 47 616 bars and 147
decisions. The full receipt survived only in ``system_events`` (deleted at 30
days, DATABASE.md §1.3) and in a JSONL that exists if somebody kept the file —
the two places ``0013`` was written precisely because neither is durable.

``markets_digest text NOT NULL`` is the SHA-256 of the sorted market keys of the
slice, and the key becomes ``(run_id, window_from, window_to, markets_digest)``.

**Not nullable, and no sentinel.** ``markets text[] NOT NULL`` has been on the
table since ``0013``, so every stored row already carries exactly the input the
digest is computed from: the backfill *derives* it in SQL — the ``0002``
boundary (backfill what the existing columns imply, refuse what they merely
suggest). Nothing named ``'legacy'`` exists anywhere, and the CHECK
``markets_digest ~ '^[0-9a-f]{64}$'`` makes such a placeholder unrepresentable.

**No upgrade guard about the key, and that is an assertion.** The new key is a
strict superset of ``0013``'s, so a widening cannot create a collision that the
old key did not already refuse. There *is* one guard, for the single thing the
digest cannot be honest about: a NULL member inside ``markets`` disappears in
the join that builds the digest, so ``{a, NULL}`` and ``{a}`` would hash alike.
It counts, names and refuses (zero on every database today: the only writer
builds each key as ``f"{exchange}:{symbol}"``).

**The downgrade refuses** when any window already holds more than one market
slice: the ``0013`` key is *narrower*, and the only way to satisfy it would be
to delete receipts of replays that really ran. Dropping the column itself loses
nothing and is deliberately not guarded — the digest is derived from ``markets``,
which stays, so re-applying ``0018`` reproduces every value byte for byte.

**Nothing here depends on session state**: one ``ALTER TABLE``, one backfill
``UPDATE``, one trigger and one constraint swap. No session prepared statement,
no ``LISTEN``/``NOTIFY``, no session advisory lock. The constraint swap takes
``ACCESS EXCLUSIVE`` for one index build over a table of tens of rows per day —
the order of magnitude of ``0012``'s window (§24.7), not a new class of risk.

**Named ``0018_replay_runs_slice_markets`` (30 characters)** —
``alembic_version.version_num`` is ``VARCHAR(32)`` (section 17.6), so this is
the longest revision id the project has and it clears the ceiling by two.

Revision ID: 0018_replay_runs_slice_markets
Revises: 0017_eligibility_policy
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.replay_runs_slice_markets import (
    add_digest_column,
    drop_digest_column,
    drop_digest_trigger,
    install_digest_trigger,
    refuse_a_downgrade_that_would_merge_two_slices,
    refuse_an_upgrade_over_an_unnamed_market,
    replace_slice_key,
    restore_slice_key,
)

revision: str = "0018_replay_runs_slice_markets"
down_revision: str | None = "0017_eligibility_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Refuse what cannot be derived, derive the rest, then widen the key."""
    refuse_an_upgrade_over_an_unnamed_market()
    add_digest_column()
    install_digest_trigger()
    replace_slice_key()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_merge_two_slices()
    restore_slice_key()
    drop_digest_trigger()
    drop_digest_column()
