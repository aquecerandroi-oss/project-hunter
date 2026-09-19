"""spot desk: the Binance -> Solana market map, the real orders and positions of spot/1

Fifty-seventh revision. **Three tables** (``spot_desk_markets``,
``spot_orders``, ``spot_positions``), nine indexes, one ``ALTER`` closing the
orders <-> positions cycle, a **50-row seed** (R63 §2a minus ``SOLUSDT`` and
``ENAUSDT``, ``ddl/spot_desk_seed.py``) and grants by subtraction. No enum,
no view, no partition, no RLS policy; nothing touched in ``0022``–``0056``.

T4.74-1, on Everton's decision of 19/09/2026 10:2x BRT ("quero ir no
dinheiro real e testar no real mesmo"): the ``spot/1`` desk — a
``mean_reversion`` signal of the Lab (Binance candles) executed on Solana by
the robot's wallet through Jupiter, as a lane inside ``services/meme-executor``
(``docs/design/spot1-lab-solana.md``). This revision is the map the lane
reads and the ledger it writes; nothing here turns money on
(``SPOT1_ENABLED`` is born ``false``).

**Upgrade guard: none, and that is an assertion** — the tables are new and
the seed is ``ON CONFLICT DO NOTHING``. **The downgrade refuses** while
``spot_orders`` holds a row with ``tx_signature`` (``ddl/spot_desk.py``,
§17.7): a real Jupiter transaction would lose its only ledger.

**Lock and pooler.** ``CREATE TABLE``/``CREATE INDEX`` on tables that did not
exist, one ``ALTER`` on an empty table, ``GRANT``s on the catalogue, 50
inserts. Nothing depends on session state. **Named ``0057_spot_desk`` (14
characters)** — ``VARCHAR(32)`` (§17.6). Described in ``docs/DATABASE.md``
§63.

Revision ID: 0057_spot_desk
Revises: 0056_meme_spot_swaps
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.spot_desk import (
    create_spot_desk_tables,
    drop_spot_desk_tables,
    grant_spot_desk_privileges,
    refuse_a_downgrade_that_would_lose_a_signed_spot_order,
    seed_spot_desk_markets,
)

revision: str = "0057_spot_desk"
down_revision: str | None = "0056_meme_spot_swaps"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_spot_desk_tables()
    grant_spot_desk_privileges()
    seed_spot_desk_markets()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_a_signed_spot_order()
    drop_spot_desk_tables()
