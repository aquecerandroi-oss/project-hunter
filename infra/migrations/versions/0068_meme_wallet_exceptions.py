"""meme wallet exceptions: Everton's audited per-mint exception to check 17

Revision ID: 0068_meme_wallet_exceptions
Revises: 0067_meme_token_state_history

F1 of the wallet-holdings review (decision 2026-09-28,
``obsidian/06-DECISIONS/2026-09-28-excecao-auditada-token-golpe.md``;
``docs/DATABASE.md`` §71; ``docs/RISK_ENGINE_MEME.md`` §3.2): **one new table**,
``meme_wallet_holding_exceptions``, global and RLS-free like ``meme_live_*``,
``SELECT`` to both roles, written only by the owner's audited CLI, revocation
only (triggers), everything in ``ddl/meme_wallet_exceptions.py``. No column on an
existing table, no view, no enum, no RLS policy, no partition, no seed.

Upgrade guard: none, and that is an assertion — the table is new and nothing
reads it until the executor that knows it is deployed (an older executor simply
ignores it: its check 17 stays as strict as it was). The downgrade refuses
while **any** row exists, revoked ones included (§17.7). **Named
``0068_meme_wallet_exceptions`` (27 characters)** — ``VARCHAR(32)`` (§17.6).
The held EXP-M26 seed was renumbered ``0069`` on top of this one.

Create Date: 2026-09-28
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_wallet_exceptions import (
    create_meme_wallet_exceptions,
    drop_meme_wallet_exceptions,
    grant_meme_wallet_exceptions_privileges,
    refuse_a_downgrade_that_would_lose_an_exception,
)

revision: str = "0068_meme_wallet_exceptions"
down_revision: str | None = "0067_meme_token_state_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_wallet_exceptions()
    grant_meme_wallet_exceptions_privileges()


def downgrade() -> None:
    """Refuse first, then unwind."""
    refuse_a_downgrade_that_would_lose_an_exception()
    drop_meme_wallet_exceptions()
