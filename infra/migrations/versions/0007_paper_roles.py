"""paper roles: the worker decides, the API asks

Seventh revision, and the first one that changes **who** may write the paper
wallet rather than what it looks like. Described in DATABASE.md section 19; the
decision it implements is the orchestrator's of 2026-09-07, which closes the
T3.6 findings 1 and 2, the T3.12 blockers A-D and finding 5 of the ``0006``
security review.

Why a new revision and not another amendment of ``0006``: ``0006`` is being
deployed to the VPS as this is written, so the freedom section 15 records - a
revision that never ran anywhere may be corrected in place - has expired for it.
From here every change is a revision of its own.

Four things:

1. **column grants for the engine.** ``hunter_worker`` gets ``UPDATE`` of
   ``portfolios (kill_switch_state, kill_switch_reason, updated_at)`` and of
   ``organizations (updated_at)`` - the first so one evaluation of the kill
   switch (the daily reference, the peak, the latch, the transition and the
   outbox event) fits in one transaction, the second so
   ``effective_state(lock=True)`` may take ``FOR SHARE`` on the tenant row,
   which PostgreSQL charges ``ACL_UPDATE`` for. Column grants, so neither buys
   anything else: the engine still cannot rename a wallet nor move an
   organization's kill switch. It also gets plain ``INSERT`` on ``portfolios``,
   because opening a wallet is one transaction and its curve point is now the
   engine's — without it the opening would have no role able to perform it;
2. **writes taken back from the API.** ``hunter_app`` loses
   ``INSERT``/``UPDATE``/``DELETE`` on ``portfolio_equity_snapshots`` (the curve
   is the evidence a resume reads - a fabricated point is a fabricated recovery)
   and ``UPDATE``/``DELETE`` on ``trade_proposals`` (deciding is admission's
   job). It keeps ``SELECT`` on both and ``INSERT`` on the proposal, because
   filing a manual request is the one write the API owns there;
3. **the request guard.** A grant cannot say *what shape* an ``INSERT`` may
   have, so a trigger does: a proposal filed by the application role must be a
   request - manual, ``pending``, no decision, no rejection, no FIFO place, no
   reservation;
4. **three columns.** ``trade_proposals.request_digest`` (the canonical identity
   of the request, so a replayed *refusal* is compared against what was asked
   and not only against four columns - T3.12, pending item 1);
   ``portfolio_equity_snapshots.brl_unavailable_reason`` and ``marks_stale``
   (the T3.3b debt: a point whose BRL value could not be computed says why, and
   never extrapolates, and a point marked with stale inputs says so).

``applied_attempts`` is deliberately **not** here. T3.4b derived execution
idempotency from ``fills.execution_key`` and ``orders.client_order_id``, both of
which already exist and are already unique, so a fourth counter would be a
second answer to a question the schema already answers (section 19.4).

There is no upgrade guard, and that is a statement rather than an omission: this
revision adds two nullable columns and one with a default, and narrows
privileges. Nothing that is already stored becomes unrepresentable, so there is
nothing an honest backfill could not produce. The ``downgrade`` does refuse -
dropping ``request_digest``, ``brl_unavailable_reason`` or ``marks_stale`` would
turn a qualified number back into a plain one, which is the section 17.7
boundary.

Nothing here depends on session state: no session-level prepared statement, no
``LISTEN``/``NOTIFY``, no session advisory lock. The grants are catalogue facts
and the trigger reads only ``NEW`` and ``pg_has_role``.

**Named ``0007_paper_roles`` (16 characters)** - ``alembic_version.version_num``
is ``VARCHAR(32)`` (section 17.6).

Revision ID: 0007_paper_roles
Revises: 0006_paper_wallet
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ddl.paper_roles import (
    apply_role_model,
    create_request_guard,
    drop_request_guard,
    refuse_a_downgrade_that_would_relabel_a_number,
    revert_role_model,
)

revision: str = "0007_paper_roles"
down_revision: str | None = "0006_paper_wallet"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _add_columns()
    apply_role_model()
    create_request_guard()


def downgrade() -> None:
    refuse_a_downgrade_that_would_relabel_a_number()
    drop_request_guard()
    revert_role_model()
    _drop_columns()


def _add_columns() -> None:
    """Three columns, each one a distinction the wallet could not record before."""
    op.add_column("trade_proposals", sa.Column("request_digest", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_trade_proposals_request_digest_is_meaningful"),
        "trade_proposals",
        "request_digest IS NULL OR char_length(request_digest) BETWEEN 1 AND 128",
    )
    # Added on the partitioned parent, which is the only place Postgres accepts
    # it: the LIST -> RANGE children inherit both columns, present and future.
    op.add_column(
        "portfolio_equity_snapshots", sa.Column("brl_unavailable_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "portfolio_equity_snapshots",
        sa.Column("marks_stale", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_portfolio_equity_snapshots_brl_unavailable_reason_is_honest"),
        "portfolio_equity_snapshots",
        "brl_unavailable_reason IS NULL OR (fx_observation_id IS NULL "
        "AND char_length(brl_unavailable_reason) BETWEEN 1 AND 64)",
    )


def _drop_columns() -> None:
    op.drop_constraint(
        op.f("ck_portfolio_equity_snapshots_brl_unavailable_reason_is_honest"),
        "portfolio_equity_snapshots",
        type_="check",
    )
    op.drop_column("portfolio_equity_snapshots", "marks_stale")
    op.drop_column("portfolio_equity_snapshots", "brl_unavailable_reason")
    op.drop_constraint(
        op.f("ck_trade_proposals_request_digest_is_meaningful"),
        "trade_proposals",
        type_="check",
    )
    op.drop_column("trade_proposals", "request_digest")
