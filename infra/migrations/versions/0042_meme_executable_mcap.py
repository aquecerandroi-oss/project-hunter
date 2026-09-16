"""meme executable mcap: the Mayhem agent's virtual SOL is not price (T4.27)

Revision ID: 0042_meme_executable_mcap
Revises: 0041_meme_social

Measured in the VPS database (3 days to 16/09/2026): all 95 peaks of
``mcap_sol`` above 500 SOL were Mayhem coins — the agent inflates the
curve's *virtual* SOL without paying real SOL in (KAT: 23,9 → 1 977 SOL in
60 s, 5 holders). This adds ``mcap_executable_sol`` beside the theoretical
market cap on ``meme_features_1m`` and ``meme_features_15s`` — ``mcap_sol``
capped at the photo's ``real_sol_reserves`` for a Mayhem coin, equal to it
otherwise — with one CHECK per series and a ``COMMENT`` on the theoretical
column. Everything is in ``ddl/meme_executable_mcap.py``; the downgrade
refuses while a row carries the cap (§17.7).

Sits on ``0041_meme_social`` (T4.26), written in parallel: when this file was
committed that revision was still being authored, and the chain was declared
here rather than guessed at.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_executable_mcap import (
    add_executable_mcap_columns,
    drop_executable_mcap_columns,
    refuse_a_downgrade_that_would_unlabel_a_mayhem_peak,
)

revision: str = "0042_meme_executable_mcap"
down_revision: str | None = "0041_meme_social"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_executable_mcap_columns()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_unlabel_a_mayhem_peak()
    drop_executable_mcap_columns()
