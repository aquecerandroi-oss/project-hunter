"""meme gate v2: the honest scoreboard, the 15-second series, the flow gate

Thirtieth revision. **Three columns** on ``meme_paper_bets`` with three
CHECKs and no backfill, **one table** (``meme_features_15s``, monthly
``RANGE``, four initial months, grants by subtraction), **one view
rewritten** (``meme_lab_scoreboard_v1``, same name and grants) and a **seed
of two rule sets** that retires none. No enum, no RLS policy; nothing touched
in ``0022``–``0029``.

T4.16, on the Lab (``0022``), the lines (``0026``), the wallets (``0027``) and
the moonshot (``0029``): Everton's question of 12/09/2026, 14:0x BRT —
"aparecendo bastante proposta mas estamos perdendo todas; não está analisando
direito? estamos muito lentos?". The measured answer (the study of the 21
bets): five closes were the simulator blinking, not the market
(``outcome_quality``); the gate read closed minutes and bought 99–289 s after
the birth (the 15-second series, ``meme_features_15s``); and it bought coins
with no demand (``flow_v2/1``, EXP-M5; the pedigree exclusions, EXP-M6, are
code, not schema). Pre-registrations:
``obsidian/05-EXPERIMENTS/EXP-M5-fluxo-e-holders.md`` and
``EXP-M6-exclusoes-de-pedigree.md``.

**Upgrade guard: none, and that is an assertion** — a defaulted column, a new
table, a view recreated, ``ON CONFLICT DO NOTHING``. **The downgrade refuses**
while a bet is ``indeterminate``, while the series holds a row, or while the
seeded sets are referenced (``ddl/meme_gate_v2.py``).

**Lock and pooler.** ``ADD COLUMN ... DEFAULT 'measured'`` on PG 16 is
catalogue-only (a non-volatile default is not rewritten); ``ADD CONSTRAINT
CHECK`` scans ``meme_paper_bets`` once (hundreds of rows); ``CREATE TABLE``
on a relation that does not exist takes no lock anyone waits on; ``DROP VIEW``
+ ``CREATE VIEW`` is catalogue-only. Nothing depends on session state.
**Named ``0030_meme_gate_v2`` (16 characters)** — ``VARCHAR(32)`` (§17.6).
Described in ``docs/DATABASE.md`` §43.

**Chain.** ``0031_meme_lab_ticks`` (T4.15, written in parallel) revises
``0029``; the merge that lands both points its ``down_revision`` at this
revision, as its own docstring says, so the chain stays linear.

Revision ID: 0030_meme_gate_v2
Revises: 0029_meme_moonshot
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_v2 import (
    add_outcome_quality,
    create_meme_features_15s,
    drop_meme_features_15s,
    drop_outcome_quality,
    refuse_a_downgrade_that_would_lose_an_outcome_or_the_series,
    replace_scoreboard_with_outcome_quality,
    restore_scoreboard_0027,
    seed_gate_v2_rule_sets,
    unseed_gate_v2_rule_sets,
)

revision: str = "0030_meme_gate_v2"
down_revision: str | None = "0029_meme_moonshot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_outcome_quality()
    create_meme_features_15s()
    replace_scoreboard_with_outcome_quality()
    seed_gate_v2_rule_sets()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_an_outcome_or_the_series()
    unseed_gate_v2_rule_sets()
    restore_scoreboard_0027()
    drop_meme_features_15s()
    drop_outcome_quality()
