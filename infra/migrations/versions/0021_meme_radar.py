"""meme radar: the pump.fun dimension, three monthly series and one read model

Twenty-first revision. **Five tables** (three of them ``RANGE``-partitioned by
month), six indexes, one view, two triggers and grants by subtraction. No enum,
no RLS policy, no column added anywhere else, and nothing touched in ``0020``.

T4.2, on the adapter T4.1 committed (``packages/exchange-adapters/
hunter_exchanges/pumpfun/``) and on ``docs/plans/T4-MEME-RADAR.md`` plus Astra's
corrections (``.claude/state/notes-A4.1b-mayhem.md``). The slice is **monitoring
only**: nothing here can become an order (T4-MEME-RADAR.md §0), no table is
reachable by ``packages/risk-core`` or the execution path, and ``hunter_app`` has
``SELECT`` and nothing else on all five.

**Global, RLS-free** (DATABASE.md §1.1), like ``markets``, ``market_regimes``,
``market_breadth`` and ``market_dispersion``: an on-chain token belongs to the
chain, not to an organization. No ``organization_id``, therefore no policy — and
the absence is **asserted**, not assumed, because "needs no policy" and "somebody
forgot the policy" are indistinguishable from outside (§25.5's rule).

**Three partitioned parents, with the arithmetic written down** (§1.3's threshold
is 1 M rows/year): ``meme_curve_snapshots`` is capped by the free REST budget at
60 rows/minute ≈ 31 M/year, ``meme_features_1m`` is one row per tracked mint per
closed minute ≈ 63 M/year at the default cap of 120, and ``meme_trades`` will take
per-transaction events. ``meme_features_1m`` being partitioned is a **declared
deviation from the brief**, which left it unpartitioned: at 63 M rows/year it would
be the largest unpartitioned table in the schema and its retention would be a
``DELETE`` of tens of millions of rows rather than a ``DROP`` (``ddl/meme_radar.py``).

**Retention is 90 days and identical for graduated and non-graduated mints**
(``MEME_RETENTION_DAYS``, T4-MEME-RADAR.md §8 decision 2: selecting on success
after the fact deletes the controls and poisons every later comparison). The three
partitioned parents are pruned by ``infra/scripts/prune_partitions.py`` dropping
whole months — which is why neither role has ``DELETE`` on them — and
``meme_tokens``, whose key is the mint and which therefore cannot be partitioned
by month, is pruned row-wise by the worker behind a declared marker
(``ddl/meme_radar_guards.py``).

**The trade table is created with no producer, on purpose.** The PumpPortal trade
channel is paid (0,01 SOL / 10 000 events) and the on-chain decoder is T4.2b; the
table exists now so the schema is whole and so the four feature columns that
depend on it can be ``NULL`` **with a reason** instead of silently zero — Astra's
MUST-FIX 1. Its primary key is ``(block_time, signature, event_index)``, which is
MUST-FIX 2: keyed on ``(signature, ts)`` alone, two trades inside one transaction
would be one row and the second would vanish into ``ON CONFLICT DO NOTHING``.

**No upgrade guard, and that is an assertion** (§19.5, §20.5, §21.4, §24.6, §25.6,
§30.5): the revision creates tables that did not exist, so there is no stored row
it can make unrepresentable. **The downgrade refuses** while any of the five holds
a row, counting them and naming the ``COPY`` (§17.7) — on every database of today
each counts zero, so the round trip runs without exporting anything.

**Nothing here depends on session state**: five ``CREATE TABLE``, six
``CREATE INDEX``, one ``CREATE VIEW``, twelve partitions, two triggers and the
grants. No session prepared statement, no ``LISTEN``/``NOTIFY``, no session
advisory lock — the only GUC involved, ``app.meme_retention``, is written with
``SET LOCAL`` and read with ``NULLIF(current_setting(..., true), '')``, exactly as
``app.current_org`` (§15.4). ``CREATE TABLE`` takes no lock on a relation that does
not yet exist and the grants lock only the catalogue (``0005``'s measurement,
§15.6): this revision **opens no maintenance window**.

**Named ``0021_meme_radar`` (16 characters)** — ``alembic_version.version_num`` is
``VARCHAR(32)`` (§17.6). Described in ``docs/DATABASE.md`` §33 (§32 belongs to
``0020_market_dispersion``, in flight in T3.90) and in
``.claude/state/notes-T4.2.md`` §contrato, which froze the read model for T4.3
before this file was written.

Revision ID: 0021_meme_radar
Revises: 0020_market_dispersion
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_radar import (
    create_meme_partitions,
    create_meme_tables,
    drop_meme_tables,
    grant_meme_privileges,
)
from ddl.meme_radar_guards import (
    create_meme_token_guards,
    drop_meme_token_guards,
    refuse_a_downgrade_that_would_lose_meme_rows,
)

revision: str = "0021_meme_radar"
down_revision: str | None = "0020_market_dispersion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_tables()
    create_meme_partitions()
    create_meme_token_guards()
    grant_meme_privileges()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_meme_rows()
    drop_meme_token_guards()
    drop_meme_tables()
