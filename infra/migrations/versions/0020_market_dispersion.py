"""market_dispersion: BTC x alts, one row per closed minute

Twentieth revision. One table, no column added anywhere else, no trigger, no
enum, no partition, no RLS.

T3.90 / H-P18. The plantão runs of 2026-09-10 and 2026-09-11
(``obsidian/00-INBOX/Hipoteses-do-plantao.md``) measured the same shape twice: the
median 24 h return of the sixteen markets of the shadow universe at **-4,80 %**
and **-3,85 %** while the **BTC** sat at **-1,50 %** and **-1,30 %**. The
hypothesis that this *discordância*, read before a decision, separates expectancy
can only reach a decision through the eligibility policy (``0017``, T3.52/T3.59),
and a gate needs a **value at the instant the bar closed**.

Computing that value inside the gate was the alternative and it was refused for
``0019``'s reason: the replay would fold *today's* ``candles_1m`` while the live
decision folded *that* minute's, and the two populations the whole Shadow Lab
exists to compare would stop being comparable.

Reusing ``market_breadth`` was the *other* alternative, asked first by the brief
and refused after reading that table's constraints: ``value`` is checked into
``[0, 1]`` (a dispersion is signed — negative **is** the hypothesis),
``falling <= covered`` ties two counts this series does not have, and
``window_minutes`` is in its unique key. Widening it meant dropping CHECKs that
protect every row already there. A sibling table with the same conventions keeps
both series as strict as each can afford (``ddl/dispersion.py``).

**Global, RLS-free**, like ``market_breadth``, ``market_regimes``,
``market_betas`` and ``replay_runs`` (DATABASE.md §1.1): the universe belongs to
the exchange.

**Not partitioned, and the count is written down**: 525 600 rows/year per venue
per version, against the 1 M/year threshold. The lookup index is keyed so that
partitioning by ``end_time`` later changes no query (though it would rebuild the
table — the PK is ``id`` alone, §15.2).

**Grants**: ``SELECT`` for ``hunter_app``, ``SELECT``/``INSERT`` for
``hunter_worker``, and nothing else for either — the ``market_breadth`` shape. No
immutability trigger is needed because no ``UPDATE`` on this table is ever legal.

**No upgrade guard, and that is an assertion**: the revision creates a table that
did not exist, so there is no stored row it can make unrepresentable. **The
downgrade refuses** while any reading exists (§17.7): the series is not
recomputable after the fact, because ``markets.is_monitored`` is overwritten in
place and the universe a historical minute was measured against is gone with the
rows.

**Nothing here depends on session state**: one ``CREATE TABLE`` and two
``GRANT``s — no ``CREATE INDEX`` of its own, because the unique key's index is the
only one this table carries. ``CREATE TABLE`` takes no lock on a relation that
does not yet exist and the ``GRANT``s lock only the catalogue (``0005``'s
measurement, §15.6): this revision opens no maintenance window.

**Named ``0020_market_dispersion`` (23 characters)** —
``alembic_version.version_num`` is ``VARCHAR(32)`` (§17.6). Described in
``docs/PIPELINE.md`` §4b item 16; the ``docs/DATABASE.md`` §32 that should describe
it is **owed** (the debt ``0019`` declared for §31, declared again here).

Revision ID: 0020_market_dispersion
Revises: 0019_market_breadth
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.dispersion import (
    create_dispersion_table,
    drop_dispersion_table,
    grant_dispersion_privileges,
    refuse_a_downgrade_that_would_lose_a_reading,
)

revision: str = "0020_market_dispersion"
down_revision: str | None = "0019_market_breadth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_dispersion_table()
    grant_dispersion_privileges()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_reading()
    drop_dispersion_table()
