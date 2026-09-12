"""meme wallets: the observed wallet's real trades and positions next to the paper Lab

Twenty-seventh revision. **Two tables** (``meme_wallet_trades``, the ledger of
every fill — or non-fill — of a watched public wallet, and
``meme_wallet_positions``, derived from it by FIFO), **four indexes**, grants by
subtraction, and **one view rewritten**: ``meme_lab_scoreboard_v1`` becomes the
``0022`` board ``UNION ALL`` one row per observed wallet per Brasília day
(``kind = 'real_observed'``). No enum, no RLS policy, nothing touched in
``0022``–``0026`` beyond that view.

T4.12, on Everton's directive of 12/09/2026 — "vou apostar dinheiro real e ter
experiência real, assim você analisa": he trades by hand on the site; this
system **signs nothing** and only reads the public address in
``MEME_WATCH_WALLETS`` from the chain, turning each real buy/sell into a row
the Lab can be judged against (``lab_context``: what every active gate said
about that mint in the minute before the fill).

**Upgrade guard: none, and that is an assertion** — two new tables and a view
whose paper half is byte-identical to ``0022``'s. **The downgrade refuses**
while ``meme_wallet_trades`` holds a row (``ddl/meme_wallets.py``); the
positions are recomputable and not guarded; the view goes back to ``0022``'s.

**Lock and pooler.** ``CREATE TABLE`` and ``CREATE INDEX`` on empty tables;
``DROP VIEW`` + ``CREATE VIEW`` on a view no writer holds. Nothing depends on
session state. **Named ``0027_meme_wallets`` (17 characters)** — ``VARCHAR(32)``
(§17.6). Described in ``docs/DATABASE.md`` §39.

Revision ID: 0027_meme_wallets
Revises: 0026_meme_lines
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_wallets import (
    create_meme_wallet_tables,
    drop_meme_wallet_tables,
    grant_meme_wallet_privileges,
    refuse_a_downgrade_that_would_lose_an_observed_trade,
    replace_scoreboard_with_observed_wallets,
    restore_scoreboard_0022,
)

revision: str = "0027_meme_wallets"
down_revision: str | None = "0026_meme_lines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_wallet_tables()
    grant_meme_wallet_privileges()
    replace_scoreboard_with_observed_wallets()


def downgrade() -> None:
    """Refuse first, then unwind in the exact reverse order of ``upgrade``."""
    refuse_a_downgrade_that_would_lose_an_observed_trade()
    restore_scoreboard_0022()
    drop_meme_wallet_tables()
