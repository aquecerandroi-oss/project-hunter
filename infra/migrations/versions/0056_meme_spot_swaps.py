"""meme spot swaps: mint pair columns on meme_treasury_swaps (T4.73)

Fifty-sixth revision. Everton, 19/09/2026 10:2x BRT: use Binance as the
signal source and buy on Solana through the wallet, via Jupiter — generalized
to any mint pair, not only the USDC->SOL treasury top-up (``0051``). This
revision plants the minimal, additive column pair
(``ddl/meme_spot_swaps.py``) so ``infra/scripts/meme_spot_swap.py`` can name
which mints a row's numbers were of, reusing ``meme_treasury_swaps`` (whose
CHECK constraints never named a currency by value, only by column label) end
to end instead of a second audit table.

**Upgrade guard: none** — two new nullable columns, nothing else touched;
every existing row (and every future USDC->SOL treasury row) keeps them
``NULL``. **The downgrade refuses** while any row carries a mint pair
(``ddl/meme_spot_swaps.py``, §17.7): a spot swap row without it is a pair of
audited numbers with no record of what moved.

Revision ID: 0056_meme_spot_swaps
Revises: 0055_meme_operator6_desk
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_spot_swaps import (
    add_spot_swap_mint_columns,
    drop_spot_swap_mint_columns,
    refuse_a_downgrade_that_would_lose_a_spot_swap_mint_pair,
)

revision: str = "0056_meme_spot_swaps"
down_revision: str | None = "0055_meme_operator6_desk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_spot_swap_mint_columns()


def downgrade() -> None:
    """Refuse first, then drop."""
    refuse_a_downgrade_that_would_lose_a_spot_swap_mint_pair()
    drop_spot_swap_mint_columns()
