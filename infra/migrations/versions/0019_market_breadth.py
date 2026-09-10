"""market_breadth: the amplitude of the universe, one row per closed minute

Nineteenth revision. One table, no column added anywhere else, no trigger, no
enum, no partition, no RLS.

T3.77 / H-P8. ``.claude/state/notes-D-P9.md`` §4 (KB-0083) measured the minute
the ``mean_reversion`` family's worst hour died in: 2026-09-09 22:08Z, **194 of
the 200 monitored perpetuals falling in the same minute** (mean -3,71 %) while
the BTC moved -0,20 %. The hypothesis it produced — that the share of the
universe falling in the minutes before a decision separates expectancy — can only
reach a decision through the eligibility policy (``0017``, T3.52/T3.59), and a
gate needs a **value at the instant the bar closed**.

Computing that value inside the gate was the alternative and it was refused: the
replay would fold *today's* ``candles_1m`` while the live decision folded *that*
minute's, and the two populations the whole Shadow Lab exists to compare would
stop being comparable. A persisted, minute-anchored, immutable series makes "the
replay read what the live bar read" a property of the schema.

**Global, RLS-free**, like ``market_regimes``, ``market_betas`` and
``replay_runs`` (DATABASE.md §1.1): the universe belongs to the exchange.

**Not partitioned, and the count is written down**: 525 600 rows/year for one
venue, 1 051 200 for two, against the 1 M/year threshold the brief sets. The
lookup index is keyed so that partitioning by ``end_time`` later changes no
query.

**Grants**: ``SELECT`` for ``hunter_app``, ``SELECT``/``INSERT`` for
``hunter_worker``, and nothing else for either — the ``replay_runs`` shape. No
immutability trigger is needed because, unlike ``market_betas``, no ``UPDATE`` on
this table is ever legal.

**No upgrade guard, and that is an assertion**: the revision creates a table that
did not exist, so there is no stored row it can make unrepresentable. **The
downgrade refuses** while any reading exists (§17.7): the series is not
recomputable after the fact — ``markets.is_monitored`` is overwritten in place,
so the universe a historical minute was measured against is gone the moment the
rows are.

**Nothing here depends on session state**: one ``CREATE TABLE`` and two
``GRANT``s — no ``CREATE INDEX`` of its own, because the unique key's index is the
only one this table carries (T3.77c). ``CREATE TABLE`` takes no lock on a relation
that does not yet exist and the ``GRANT``s lock only the catalogue (``0005``'s
measurement, §15.6): this revision opens no maintenance window.

**Named ``0019_market_breadth`` (20 characters)** — ``alembic_version.version_num``
is ``VARCHAR(32)`` (§17.6). Described in ``docs/PIPELINE.md`` §4b item 14; the
``docs/DATABASE.md`` §31 that should describe it is **owed**, and said so in
``.claude/state/notes-T3.77.md``.

Revision ID: 0019_market_breadth
Revises: 0018_replay_runs_slice_markets
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.breadth import (
    create_breadth_table,
    drop_breadth_table,
    grant_breadth_privileges,
    refuse_a_downgrade_that_would_lose_a_reading,
)

revision: str = "0019_market_breadth"
down_revision: str | None = "0018_replay_runs_slice_markets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_breadth_table()
    grant_breadth_privileges()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_reading()
    drop_breadth_table()
