"""meme gate arm: absorb_semdump_v0/1, absorb_v0/2 without the creator_dump exit (H-031b)

Revision ID: 0069_meme_absorb_semdump_arm
Revises: 0068_meme_wallet_exceptions

EXP-M27 (``obsidian/05-EXPERIMENTS/EXP-M27-gemeo-sem-creator-dump.md``), the
Defensor's route (2) over H-031, approved by Everton on 07/10/2026: does the
largest buyer's concentration predict a loss once the ``creator_dump`` exit no
longer absorbs it? This revision seeds ``absorb_semdump_v0/1`` (``…0022``),
``research_only``, ``absorb_v0/2``'s live params plus
``"exit_on_creator_dump": false``, copied in the same statement the guards
check. **One arm, no schema change, nothing retired, the desk untouched.** The
upgrade refuses when ``absorb_v0/2`` is missing, not active, not on the ``15s``
clock or already without the exit, and when a stranger sits under the frozen
name; the downgrade refuses while a proposal, a bet, a param-history row, a
sampled refusal or an opportunity record references the twin (§17.7).
Everything is in ``ddl/meme_absorb_semdump_arm.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_absorb_semdump_arm import (
    refuse_a_downgrade_that_would_orphan_a_twin_row,
    seed_absorb_semdump,
    unseed_absorb_semdump,
)

revision: str = "0069_meme_absorb_semdump_arm"
down_revision: str | None = "0068_meme_wallet_exceptions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_absorb_semdump()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_twin_row()
    unseed_absorb_semdump()
