"""meme live: the proposal's mode, the real orders, the real positions, the daily latch

Twenty-eighth revision. **One column** on ``meme_proposals`` (``mode``, CHECK
``paper``/``live``, default ``paper``, one partial index), **three tables**
(``meme_live_orders``, ``meme_live_positions``, ``meme_live_kill_switch``),
six indexes, one seed row (``scope = 'wallet'``, ``ACTIVE``) and grants by
subtraction. No view, no enum, no RLS policy; nothing touched in
``0022``–``0027`` beyond the column and the one column grant.

T4.14, on Everton's directive of 12/09/2026 12:3x BRT ("bora tentar logo com
dinheiro real; ele faz a operação, não consegue?"): the service that connects
an approval on the desk to a signed transaction on the pump.fun curve
(``services/meme-executor``), inert until ``ENABLE_MEME_LIVE_TRADING`` and the
§12 gates — this revision is the ledger it writes and the desk reads.

**Upgrade guard: none, and that is an assertion** — the column is defaulted so
every proposal of today is ``paper``; the tables are new; the seed is
``ON CONFLICT DO NOTHING``. **The downgrade refuses** while ``meme_live_orders``
holds a row or a proposal says ``mode = 'live'`` (``ddl/meme_live.py``).

**Lock and pooler.** ``ADD COLUMN`` with a constant default is catalogue-only
on Postgres 16; ``CREATE TABLE``/``CREATE INDEX`` on empty tables. Nothing
depends on session state. **Named ``0028_meme_live`` (14 characters)** —
``VARCHAR(32)`` (§17.6). Described in ``docs/DATABASE.md`` §40.

Revision ID: 0028_meme_live
Revises: 0027_meme_wallets
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_live import (
    add_proposal_mode,
    create_meme_live_tables,
    drop_meme_live_tables,
    drop_proposal_mode,
    grant_meme_live_privileges,
    refuse_a_downgrade_that_would_lose_a_real_order,
    seed_kill_switch_scope,
)

revision: str = "0028_meme_live"
down_revision: str | None = "0027_meme_wallets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_proposal_mode()
    create_meme_live_tables()
    grant_meme_live_privileges()
    seed_kill_switch_scope()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_real_order()
    drop_meme_live_tables()
    drop_proposal_mode()
