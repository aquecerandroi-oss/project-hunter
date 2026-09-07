"""paper roles, second pass: the API stops writing execution, a wallet is born audited

Eighth revision. It carries no new table and no new column: it closes the three
DDL findings of the security review of ``0007``
(``.claude/state/review-T3.1c-security.md``, "deve corrigir" D1, D3 and D4), each
of which was reproduced against a real database as the real role. Described in
DATABASE.md section 20; the role model it tightens is section 19.

1. **D1 — ``hunter_app`` loses ``INSERT``/``UPDATE``/``DELETE`` on ``orders``,
   ``fills``, ``positions`` and ``trades``.** It has held full DML on all four
   since ``0001``, when the API was the only writer of anything. The review
   fabricated a fill, multiplied a position's quantity by a thousand, deleted
   from ``trades`` and rewrote an order — every one accepted, inside the
   *correct* organization, where RLS says yes. It is the hole ``0007`` closed on
   the equity curve, one level down: the curve is derived from these four
   tables, so forging the source makes the engine compute and sign the forged
   point itself. ``SELECT`` stays, because the seven routes T3.8a landed
   (``routers/portfolio.py``) read them and nothing writes them. Section 19.6
   declared this gap and deferred it to "uma revisão própria com a T3.5/T3.8 na
   mão"; this is it.
2. **D3 — ``portfolios_are_born_audited``.** ``0007`` gave ``hunter_worker``
   plain ``INSERT`` on ``portfolios`` so an opening could be one transaction
   (section 19.2, item 1b). ``INSERT`` carries every column and the role holds
   ``BYPASSRLS``, so the same grant bought a wallet with ``is_arena = true``
   (outside ``uq_portfolios_principal_paper``, therefore a second wallet the
   permanence index cannot see), a ``type = 'live'`` portfolio, or a wallet in
   **another organization** — none of them with an anchor, a lock row or an
   audit entry. A deferred constraint trigger now requires an engine-only
   caller's wallet to be ``paper``, not arena, and to carry an ``audit_logs``
   row of the same organization written in **this** transaction
   (``xmin = pg_current_xact_id()``, the same proof section 18.7 uses for a
   kill-switch move). The real opening
   (``hunter_core.portfolio.open_paper_wallet``) already writes that entry in
   the same commit and keeps passing.
3. **D4 — the two kill-switch guards watch the motive too.** Their ``WHEN``
   named only ``kill_switch_state``, so ``UPDATE portfolios SET
   kill_switch_reason = '...'`` rewrote the text an OWNER reads with no
   transition, no actor and no history. Both are recreated with
   ``OR OLD.kill_switch_reason IS DISTINCT FROM NEW.kill_switch_reason`` and one
   extra branch, so the refusal says what happened rather than "moved from
   WARNING to WARNING".

**There is no upgrade guard, and that is an assertion.** This revision narrows
privileges and adds one ``INSERT`` trigger; nothing already stored becomes
unrepresentable, so there is nothing an honest backfill could not produce. The
existing rows the new trigger would have refused cannot exist retroactively — it
fires on ``INSERT`` only.

**There is no downgrade guard either, for the same reason ``0007``'s grants have
none** (section 19.5): reversing widens two privilege statements and drops one
trigger, and neither is a fact about data. A ``kill_switch_reason`` already
stored survives untouched; what comes back is only the ability to rewrite one
without a transition. The ``downgrade`` hands back exactly what ``0001`` granted
on the four tables — never ``GRANT ALL`` — and restores the two guards from
``0006``'s own frozen description of them.

Nothing here depends on session state: the grants are catalogue facts and both
triggers read only ``NEW``/``OLD``, ``pg_has_role`` and ``pg_current_xact_id``.
No session-level prepared statement, no ``LISTEN``/``NOTIFY``, no session
advisory lock.

**Named ``0008_paper_roles_2`` (18 characters)** — ``alembic_version.version_num``
is ``VARCHAR(32)`` (section 17.6).

Revision ID: 0008_paper_roles_2
Revises: 0007_paper_roles
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.paper_roles_2 import (
    apply_execution_read_only,
    create_birth_guard,
    drop_birth_guard,
    narrow_kill_switch_when,
    revert_execution_read_only,
    widen_kill_switch_when,
)

revision: str = "0008_paper_roles_2"
down_revision: str | None = "0007_paper_roles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    apply_execution_read_only()
    create_birth_guard()
    widen_kill_switch_when()


def downgrade() -> None:
    narrow_kill_switch_when()
    drop_birth_guard()
    revert_execution_read_only()
