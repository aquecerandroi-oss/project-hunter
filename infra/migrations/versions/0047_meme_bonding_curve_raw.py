"""``0047_meme_bonding_curve_raw`` — Mayhem's shared sol-vault stops
overwriting the curve PDA at ingest; the raw value it replaces is kept for
audit (T4.39).

R36 (16/09/2026, ``.claude/state/notes-R36-pda-mayhem.md``) found 13 615 of
112 108 seven-day ``meme_tokens`` rows storing the Mayhem program's shared
``["sol-vault"]`` PDA (``BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s``) in
``bonding_curve`` instead of the coin's own bonding-curve PDA — 100% of them
``mayhem_enabled``. The PumpPortal ``create`` frame carries the vault in
``bondingCurveKey`` for these coins (``hunter_exchanges.pumpfun.normalize``);
the executor never reads the column (``ChainReader.curve`` always derives),
but the radar's ``reconcile_once`` did, read a 0-byte System-owned account,
and burned top-K RPC budget failing closed for every one of them
(``docs/PUMPFUN.md`` §9).

One nullable column, no backfill here — a migration is not the place for a
one-time, reviewable rewrite of 13 615 rows; ``infra/scripts/
meme_repair_bonding_curve.py`` does that, audited, dry-run by default,
against the running database. The write-once trigger is extended to cover
the new column: it is evidence exactly like ``bonding_curve`` itself.

Upgrade guard: none — the column is new, every existing row starts at
``NULL``. The downgrade refuses while any row carries a raw value (§17.7):
PumpPortal's free channel has no replay, so the first sighting of a frame's
mismatch is not re-observable once the column is dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_bonding_curve_raw import (
    add_bonding_curve_raw_column,
    create_meme_token_guards_0047,
    drop_bonding_curve_raw_column,
    refuse_a_downgrade_that_would_lose_bonding_curve_raw,
    restore_meme_token_guards_0041,
)

revision: str = "0047_meme_bonding_curve_raw"
down_revision: str | None = "0046_meme_rule_set_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    add_bonding_curve_raw_column()
    create_meme_token_guards_0047()


def downgrade() -> None:
    refuse_a_downgrade_that_would_lose_bonding_curve_raw()
    restore_meme_token_guards_0041()
    drop_bonding_curve_raw_column()
