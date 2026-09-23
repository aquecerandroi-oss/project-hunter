"""spot desk: the six markets R71 measured and the map was missing

Revision ID: 0061_spot_desk_r71
Revises: 0060_meme_refused_probe_arm

R71 (23/09/2026, Everton's 16:5x BRT decision "aumente o maximo que der, sem
afrouxar criterio"). **No schema change**: six ``INSERT``s into
``spot_desk_markets``, ``ON CONFLICT (binance_symbol) DO NOTHING``, everything
in ``ddl/spot_desk_r71.py``.

Half of the desk's signals were falling in markets the map does not cover. Of
the **68** Binance symbols where the Lab's ``mean_reversion`` family fired in
the last 14 days and which are absent from ``spot_desk_markets``, exactly
**six** have a Solana token that survives R63's filter (price parity with the
Binance mark inside +-3 %, a Jupiter route, round trip under 1 %): ``NEARUSDT``,
``XRPUSDT``, ``BIRBUSDT``, ``SLXUSDT``, ``BTCUSDT`` and ``ORCAUSDT``. The
biggest hole stays open on purpose: ``DASHUSDT`` (121 signals in 14 days, 94 in
7) has **no validated representation on Solana** — its homonyms are unverified
memecoins 100 % away from the Binance price.

``enabled`` is ``0057``'s rule verbatim (``tier <> 'C' AND round trip <=
0,4 %``), so three are born on (``NEARUSDT``, ``BTCUSDT``, ``ORCAUSDT``);
``SLXUSDT`` is off by the rule (tier C) and ``XRPUSDT``/``BIRBUSDT`` are held
back by name for a risk the rule never looked at (freeze authority; holder
concentration) — a restriction, never a loosening, reversible by the operator's
audited script.

**The downgrade refuses** while a ``spot_orders`` or a ``spot_positions`` row
names one of the six (§17.7), and otherwise removes exactly those six —
``0057``'s fifty are never named. **Named ``0061_spot_desk_r71`` (18
characters)** — ``VARCHAR(32)`` (§17.6).

Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.spot_desk_r71 import (
    refuse_a_downgrade_that_would_orphan_a_spot_row,
    seed_spot_desk_markets_r71,
    unseed_spot_desk_markets_r71,
)

revision: str = "0061_spot_desk_r71"
down_revision: str | None = "0060_meme_refused_probe_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    seed_spot_desk_markets_r71()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_orphan_a_spot_row()
    unseed_spot_desk_markets_r71()
