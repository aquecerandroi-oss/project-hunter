"""meme mayhem denominator: the third provenance of the progress denominator

Twenty-fifth revision. **One CHECK widened** on ``meme_tokens``
(``ck_meme_tokens_denominator_source_is_a_known_label`` gains
``mayhem_state``), nothing else: no column, no table, no view, no trigger, no
enum, no RLS policy, nothing touched in ``0022``–``0024``.

T4.2e, on the graduation revision T4.2d committed (``0024_meme_graduation``):
the Mayhem program's per-coin account ``MayhemState`` was read on chain for
five coins and reconciled to the subunit with the coin's vault and SPL supply
(``docs/PUMPFUN-ONCHAIN.md`` §3.5). A Mayhem curve's initial real token reserve
is the ``/global-params`` record's, like every other curve's; what
``0024``'s guard saw as "more tokens than the initial" is the agent's own
billion sold net into the curve. The worker now writes the record's initial
for a Mayhem coin **only after** that reconciliation, and names the provenance
``mayhem_state`` (``services/meme-worker/hunter_meme_worker/mayhem.py``).

**Upgrade guard: none, and that is an assertion** — the new list is a superset
of the old, so no stored row becomes unrepresentable. **The downgrade refuses**
while any row carries a ``mayhem_state`` denominator (``ddl/meme_mayhem.py``).

**Lock and pooler.** ``DROP CONSTRAINT`` and ``ADD CONSTRAINT … NOT VALID`` are
catalogue-only; ``VALIDATE CONSTRAINT`` scans ``meme_tokens`` once (~40 k
rows/day, pruned at 90 days) under ``SHARE UPDATE EXCLUSIVE``, which does not
block the collector's upserts. Nothing depends on session state. **Named
``0025_meme_mayhem_denominator`` (28 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §37.

Revision ID: 0025_meme_mayhem_denominator
Revises: 0024_meme_graduation
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_mayhem import (
    narrow_denominator_source,
    refuse_a_downgrade_that_would_lose_a_mayhem_denominator,
    widen_denominator_source,
)

revision: str = "0025_meme_mayhem_denominator"
down_revision: str | None = "0024_meme_graduation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    widen_denominator_source()


def downgrade() -> None:
    """Refuse first, then restore ``0024``'s list."""
    refuse_a_downgrade_that_would_lose_a_mayhem_denominator()
    narrow_denominator_source()
