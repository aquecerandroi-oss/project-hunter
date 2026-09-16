"""meme rule set param history + sampled per-mint gate refusal trail (T4.35)

Revision ID: 0046_meme_rule_set_history
Revises: 0044_meme_gate_e2b_arm

R27 (16/09/2026, ``obsidian/03-TRADING/Meme/Estudo-2026-09-16-a-porta-real-versus-a-replica.md``)
found ``operator/5`` edited four times in 100 minutes with no row keeping the
old value, and the gate's per-mint decision recoverable only by replaying the
whole tick. Two tables, no column on an existing table, no view, no enum, no
RLS policy; nothing touched on ``meme_rule_sets``/``meme_features_15s``
themselves beyond a foreign key each points at ``meme_rule_sets``.

**Chain note (orchestrator, please read before merging).** ``0045`` did not
exist yet when this revision was written, and ``0044_meme_gate_e2b_arm``
(T4.31) was present on disk but **not yet committed** — chosen as
``down_revision`` anyway (rather than the last committed head,
``0043_meme_events_scan_cursor``) because the shared ``services/meme-worker``
test suite resolves Alembic's ``"head"`` once per session
(``services/meme-worker/tests/conftest.py``): branching from ``0043`` instead
would have made ``"head"`` ambiguous for every concurrent agent's test run,
not just this one. **Once ``0044`` (and ``0045``, if it lands first) are
committed, whoever merges this must confirm the chain is still linear** —
bump this file's ``down_revision`` to whatever the real predecessor turns out
to be if a branch appears.

Upgrade guard: none, and that is an assertion — both tables are new. The
downgrade refuses while a row exists in either (§17.7): a param's old value
and a near-miss trail are both evidence nothing else reconstructs.

Described in ``docs/DATABASE.md`` §53.
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.meme_gate_refusals import (
    create_meme_gate_refusals_by_mint,
    drop_meme_gate_refusals_by_mint,
    grant_meme_gate_refusals_by_mint_privileges,
    refuse_a_downgrade_that_would_lose_the_refusal_trail,
)
from ddl.meme_rule_set_history import (
    create_meme_rule_set_param_history,
    drop_meme_rule_set_param_history,
    refuse_a_downgrade_that_would_lose_the_param_history,
)

revision: str = "0046_meme_rule_set_history"
down_revision: str | None = "0044_meme_gate_e2b_arm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_meme_rule_set_param_history()
    create_meme_gate_refusals_by_mint()
    grant_meme_gate_refusals_by_mint_privileges()


def downgrade() -> None:
    """Refuse first, then unwind — both tables, before either drops."""
    refuse_a_downgrade_that_would_lose_the_param_history()
    refuse_a_downgrade_that_would_lose_the_refusal_trail()
    drop_meme_gate_refusals_by_mint()
    drop_meme_rule_set_param_history()
