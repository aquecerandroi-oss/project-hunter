"""meme treasury swaps: the audit trail of every USDC->SOL top-up (T4.54)

Fifty-first revision. **One table**, ``meme_treasury_swaps`` — the record of
every attempt ``hunter_meme_executor.treasury`` ever made to top up the
wallet's SOL from its USDC balance via Jupiter, whether it landed, failed, or
was refused before anything was ever built. Everton's directive of
17/09/2026 ("eu quero deixar atualizado para usar outra moeda"): the bot
wallet held 21,33 USDC beside ~0,67 SOL and pump.fun buys are SOL-only; the
feature is off by default (``MEME_TREASURY_ENABLED``) and every number this
table carries is bounded (``docs/RISK_ENGINE_MEME.md`` new §, T4.54).

**Upgrade guard: none** — one new table, nothing else touched. **The
downgrade refuses** while a row exists (``ddl/meme_treasury_swaps.py``,
§17.7): a treasury swap moved the owner's capital (or refused to), and that
is evidence, not state to discard.

Revision ID: 0051_meme_treasury_swaps
Revises: 0050_meme_gate_ratio10_arm
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_treasury_swaps import (
    create_meme_treasury_swaps_table,
    drop_meme_treasury_swaps_table,
    grant_meme_treasury_swaps_privileges,
    refuse_a_downgrade_that_would_lose_a_treasury_swap,
)

revision: str = "0051_meme_treasury_swaps"
down_revision: str | None = "0050_meme_gate_ratio10_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_treasury_swaps_table()
    grant_meme_treasury_swaps_privileges()


def downgrade() -> None:
    """Refuse first, then drop."""
    refuse_a_downgrade_that_would_lose_a_treasury_swap()
    drop_meme_treasury_swaps_table()
