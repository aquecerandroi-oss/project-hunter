"""``0048_meme_creator_initial_buy`` — the creator's allocation at the creation
instant, so check 10 can be answered from the chain at decision time (T4.45).

Measured (16/09/2026, ``obsidian/03-TRADING/Meme/Balanco-2026-09-16-mesa-real.md``):
of the day's 58 real orders, **27** were refused ``creator_flow_unknown`` — the
1-minute fold's ``creator_sold`` lands +123 to +441 s after the coin exists while
the entry window is 30–300 s, so the executor asked a question nothing could
answer yet. T4.28g §2.3 refused to derive the answer from the chain for one
concrete reason: *no column held the creator's allocation at creation*, and using
the current ``devHoldingsPercent`` as the base would make a creator who dumped
everything at +20 s read as "holds ≥ base" and **pass** check 10 — the exact dump
the check exists to catch.

This revision stores that base, from the only reading taken at the creation
instant: PumpPortal's ``create`` frame carries ``initialBuy`` (tokens) and
``solAmount`` (SOL), and the frame's own arithmetic proves the unit
(``1 073 000 000 - initialBuy == vTokensInBondingCurve``, to the last digit, on
the live capture). Both columns are written once, like every other fact of the
launch.

**No backfill, and that is a decision, not an omission.** For coins created
before this revision the datum is not recoverable honestly: ``meme_trades``
(swap-api tape) starts covering a mint a median ~100 s after creation — a dev buy
that appears *there* is a later buy, not the creation allocation — and the REST
``/coins/<mint>`` exposes only the **current** ``devHoldingsPercent``, the very
photograph this revision exists to replace. A script that wrote either into these
columns would manufacture exactly the false "creator still holds" that T4.28g
refused. Old coins keep ``NULL`` and keep refusing by name
(``creator_flow_unknown``); the admission only derives a flow when the base is
known and ``> 0``.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_creator_initial_buy import (
    add_creator_initial_buy_columns,
    create_meme_token_guards_0048,
    drop_creator_initial_buy_columns,
    refuse_a_downgrade_that_would_lose_the_creators_initial_buy,
    restore_meme_token_guards_0047,
)

revision: str = "0048_meme_creator_initial_buy"
down_revision: str | None = "0047_meme_bonding_curve_raw"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_creator_initial_buy_columns()
    create_meme_token_guards_0048()


def downgrade() -> None:
    refuse_a_downgrade_that_would_lose_the_creators_initial_buy()
    restore_meme_token_guards_0047()
    drop_creator_initial_buy_columns()
