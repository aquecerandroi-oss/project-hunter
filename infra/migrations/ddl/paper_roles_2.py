"""What the API may no longer write, and what a wallet must be born with — §20.

``0008_paper_roles_2`` closes the four "must fix" of the security review of
``0007`` (``.claude/state/review-T3.1c-security.md``). Three of them are in this
module; the fourth (D2) is a coverage guard in the API test suite and has no DDL.

- **D1 — the execution tables stop being writable by the API.** ``hunter_app``
  held full DML on ``orders``, ``fills``, ``positions`` and ``trades`` since
  ``0001``. The review reproduced it as the role, in the *correct* organization,
  where RLS says yes: a fabricated fill, ``positions.qty × 1000``, ``DELETE FROM
  trades``, ``UPDATE orders`` — all accepted. That is the same hole ``0007``
  closed on ``portfolio_equity_snapshots``, one level down: the curve is
  *derived* from these four tables, so forging the source makes the worker write
  the forged point itself, signed by the role everything trusts. §19.6 declared
  this gap and deferred it to "uma revisão própria com a T3.5/T3.8 na mão"; this
  is that revision, and the answer from T3.5/T3.8 is that **no route writes
  them** — the API lists them and nothing more.
- **D3 — a wallet the engine inserts is a paper wallet, and it is audited.**
  ``0007`` gave ``hunter_worker`` plain ``INSERT`` on ``portfolios`` so that
  ``open_paper_wallet`` could be one transaction (§19.2, item 1b). ``INSERT``
  carries every column, and the role has ``BYPASSRLS``, so the grant also bought
  a wallet with ``is_arena = true``, or ``type = 'live'``, or one in **another
  organization** — with no anchor, no lock row and no audit entry.
  :func:`create_birth_guard` makes the shape of an engine-written wallet an
  invariant of the schema instead of a property of the one code path.
- **D4 — the motive travels with the latch.** The two kill-switch guards of
  §18.7 fired only ``WHEN`` ``kill_switch_state`` changed, so
  ``UPDATE portfolios SET kill_switch_reason = '…'`` rewrote the text an OWNER
  reads on the screen with no transition, no actor and no history. The ``WHEN``
  now covers the reason as well.

Every list here is **frozen as of this revision**, like ``ddl/tables.py`` as of
``0001`` and ``ddl/paper_roles.py`` as of ``0007``: the privileges the downgrade
hands back are the ones ``0001`` granted, spelled out.

Nothing here depends on session state: the grants are catalogue facts and both
triggers read only ``NEW``/``OLD``, ``pg_has_role`` and ``pg_current_xact_id``
— no session prepared statement, no ``LISTEN``/``NOTIFY``, no session advisory
lock (§18.10, §19.7).
"""

from __future__ import annotations

from alembic import op

from ddl.paper import (
    KILL_SWITCH_AUDITED,
    ORG_KILL_SWITCH_AUDITED,
    create_kill_switch_audit_guard,
)
from hunter_core.db.models import APP_ROLE, WORKER_ROLE

APP_READ_ONLY_TABLES_0008: tuple[str, ...] = ("orders", "fills", "positions", "trades")
"""The four execution tables, **reclassified** from ``APP_WRITE_TABLES`` to read-only.

This is a *move*, not a new class of table: every name here is one ``0001``
already classified (``ddl/tables.py``), so the partition of the schema over the
``hunter_app`` grant classes stays exact — ``test_schema_privileges.py``
subtracts this tuple from ``APP_WRITE_TABLES`` before counting, and
``test_migrations.py::test_0008_reclassifies_only_tables_0001_had_already_classified``
is what stops it ever becoming the back door for an unclassified table (the same
role ``test_0005_touches_no_table_0003_had_not_already_classified`` plays).

Why these four and why now. ``hunter_app`` could write them because in the M0
schema the API was the only writer of anything; T3.4/T3.5 moved execution to the
engine and T3.8a landed the API's side of it, which is **seven ``GET``s**
(``apps/api/hunter_api/routers/portfolio.py``): list, summary, anchor,
equity-curve, positions, orders, trades. So the answer §19.6 was waiting for is
in: the API reads execution and writes none of it.

``trade_proposals`` is deliberately **not** here. Filing a manual request is the
one write the API genuinely owns on the execution path (§19.2, item 3), and
``trade_proposals_the_app_only_files_requests`` (§19.4) already constrains its
shape. It keeps ``SELECT``/``INSERT``.
"""

BIRTH_GUARD = "portfolios_are_born_audited"

_HAS_APP = f"pg_has_role(current_user, '{APP_ROLE}', 'USAGE')"
_HAS_WORKER = f"pg_has_role(current_user, '{WORKER_ROLE}', 'USAGE')"
_CALLER_IS_ONLY_THE_ENGINE = f"({_HAS_WORKER} AND NOT {_HAS_APP})"
"""The session holds the engine's privileges **and nothing beyond them**.

The mirror of ``ddl.paper._CALLER_IS_THE_APP``, and spelled out here rather than
imported for the reason every list in this package is frozen per revision: a
later edit to ``0006``'s module must not silently redefine what ``0008``
installed. Membership, never ``current_user = 'hunter_worker'`` — a login that
merely *inherits* the role keeps every privilege while reporting its own name
(§18.7, "nome não é privilégio").

The second half is what keeps an operator out of the guard: the owner and a
superuser hold *both* roles, so they are not "only the engine" and may still
write a shadow or a live portfolio by hand. What this catches is exactly the
grant ``0007`` handed out — ``hunter_worker`` and anything inheriting only it.
"""

_AUDITED_IN_THIS_TRANSACTION = (
    "EXISTS (SELECT 1 FROM audit_logs a "
    "WHERE a.organization_id = NEW.organization_id "
    "AND a.xmin = pg_current_xact_id()::xid)"
)
"""An audit row of this organization, written by **this** transaction.

Same shape and the same reasoning as §18.7's proof for a kill-switch move: being
audited *at some point* is not being audited *for this act*, and ``xmin`` costs
no column in a hot table, no FK from a tenant table to an append-only one and no
change to any writer — ``open_paper_wallet`` already writes the wallet, the lock
row, the anchor, the first curve point and the audit entry in one commit
(§18.2), which is the atomicity this now enforces from the schema side.

``audit_logs`` is RANGE-partitioned and ``xmin`` reads correctly through the
partitioned parent on Postgres 16 (measured); the engine has ``BYPASSRLS``, so
the row it just wrote is visible to it here.

**The declared price is the same one §18.7 declares, and it is a false refusal,
never a false pass:** a row inserted inside a ``SAVEPOINT`` carries the
sub-transaction's xid, so an opening that wraps its audit entry in a
``begin_nested`` would be refused. No write path does, and the rule is written
down rather than left to be discovered.
"""


def apply_execution_read_only() -> None:
    """Take back the API's DML on the four execution tables (D1).

    ``SELECT`` stays — the seven portfolio routes are reads and they are the
    whole of the API's business with execution. ``REVOKE`` names the three
    privileges rather than ``REVOKE ALL`` for the reason ``0007``'s revert does:
    a privilege statement should say what it means, and ``ALL`` would also take
    back the ``SELECT`` this revision is deliberately keeping.
    """
    for table in APP_READ_ONLY_TABLES_0008:
        op.execute(f"REVOKE INSERT, UPDATE, DELETE ON {table} FROM {APP_ROLE}")


def revert_execution_read_only() -> None:
    """Give back exactly what ``0001`` granted on those four tables, and no more."""
    for table in APP_READ_ONLY_TABLES_0008:
        op.execute(f"GRANT INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}")


def create_birth_guard() -> None:
    """A wallet the engine inserts is a paper wallet, in the open, and audited (D3).

    ``0007`` gave ``hunter_worker`` ``INSERT`` on ``portfolios`` because opening
    a wallet has to be one transaction. ``INSERT`` carries every column, and the
    role holds ``BYPASSRLS``, so that grant also bought three rows nobody
    intended, each reproduced by the review as the role itself:

    - ``is_arena = true`` — outside ``uq_portfolios_principal_paper``, so it does
      not collide with the principal wallet and is invisible to the permanence
      index that makes "one wallet" true (§18.8);
    - ``type = 'live'`` — a live portfolio in a milestone whose directive is
      paper-only, which every downstream reader would treat as real money;
    - a wallet in **another organization** — RLS does not stop a role that
      bypasses it, and no other constraint looks at who asked.

    All three arrived with no anchor, no ``portfolio_risk_state`` and no audit
    entry, which is the deeper problem: a wallet whose birth nobody recorded has
    no beginning to reconstruct, and the directive's ban on resets is enforced
    by exactly that history.

    Two conditions, and both only for a caller who has the engine's privileges
    and nothing else. An operator or the owner (who hold both roles) still writes
    a shadow portfolio by hand, and ``hunter_app`` is untouched — the API creates
    non-principal portfolios today and this revision does not change that.

    **A deferred constraint trigger, and that is not style.** The audit entry is
    the *last* thing ``open_paper_wallet`` writes (§18.2), so a ``BEFORE INSERT``
    check would refuse the very path it exists to bless. Deferred to COMMIT, the
    whole picture exists and the guard dictates no statement order — the same
    reasoning, and the same shape, as ``portfolio_risk_state_opens_honestly``
    (§18.7).
    """
    op.execute(f"""
CREATE FUNCTION {BIRTH_GUARD}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    BEGIN
        IF NOT {_CALLER_IS_ONLY_THE_ENGINE} THEN
            RETURN NEW;
        END IF;
        IF NEW.type <> 'paper' OR NEW.is_arena THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || NEW.id || ' was opened by ' || current_user
                    || ' as type=' || NEW.type || ', is_arena=' || NEW.is_arena
                    || ': the engine opens the paper wallet and nothing else',
                HINT = 'a wallet written with only the engine''s privileges must be '
                    || 'type = paper and is_arena = false. An arena wallet sits outside '
                    || 'uq_portfolios_principal_paper, so it is a second wallet the '
                    || 'permanence index cannot see, and a live portfolio is money the '
                    || 'directive does not authorise. An operator holding both roles may '
                    || 'still write one by hand';
        END IF;
        IF NOT {_AUDITED_IN_THIS_TRANSACTION} THEN
            RAISE EXCEPTION USING
                MESSAGE = 'portfolio ' || NEW.id || ' was opened by ' || current_user
                    || ' for organization ' || NEW.organization_id
                    || ' with no audit_logs row written in this transaction',
                HINT = 'a wallet is born audited: write the audit entry in the same '
                    || 'transaction as the wallet, its lock row, its anchor and the first '
                    || 'point of its curve, the way hunter_core.portfolio.open_paper_wallet '
                    || 'does. A row banked by an earlier transaction does not record this '
                    || 'opening, and a SAVEPOINT around the audit entry hides its xid from '
                    || 'pg_current_xact_id()';
        END IF;
        RETURN NEW;
    END;
$$
""")
    op.execute(
        f"CREATE CONSTRAINT TRIGGER {BIRTH_GUARD} AFTER INSERT ON portfolios "
        f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
        f"EXECUTE FUNCTION {BIRTH_GUARD}()"
    )


def drop_birth_guard() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {BIRTH_GUARD} ON portfolios")
    op.execute(f"DROP FUNCTION IF EXISTS {BIRTH_GUARD}()")


_WHEN_0008 = (
    "WHEN (OLD.kill_switch_state IS DISTINCT FROM NEW.kill_switch_state "
    "OR OLD.kill_switch_reason IS DISTINCT FROM NEW.kill_switch_reason)"
)
"""§18.7's condition, widened to the motive (D4).

``kill_switch_reason`` was rewritable with no transition at all: the guard never
fired, ``kill_switch_transitions`` kept saying one thing and the column an
OWNER's screen reads said another (``routers/risk.py``,
``services/radar_org_derivation.py``). The two are one fact — ``record_transition``
has always written them in a single ``UPDATE``, and ``0007``'s column grant names
them together for exactly that reason (``ddl/paper_roles.py``) — so the guard now
watches both.

The consequence, declared rather than discovered: a reason-only rewrite becomes
**impossible for every role**, because ``kill_switch_transitions`` carries
``CHECK (from_state <> to_state)`` and therefore cannot describe a standstill.
That is the intended reading of the finding, not a side effect — a motive nobody
can attribute to a movement is a caption, not a record — and nothing writes one:
``hunter_core.risk.transitions.record_transition`` is the single write path and
it moves both columns in the same statement.
"""

_AUDITED_MOVE_BODY_0008 = """
    DECLARE latest record;
    BEGIN
        IF OLD.kill_switch_state IS NOT DISTINCT FROM NEW.kill_switch_state THEN
            RAISE EXCEPTION USING
                MESSAGE = '{subject} ' || NEW.id || ' rewrote its kill switch reason while '
                    || 'the switch stayed at ' || NEW.kill_switch_state
                    || ', with no transition to explain the new text',
                HINT = 'the reason is the motive of the latch and it is what an OWNER reads '
                    || 'on the screen: it moves with the switch and with nothing else. A '
                    || 'transition carries from_state <> to_state, so a standstill cannot be '
                    || 'written as one — set the reason in the same statement that moves the '
                    || 'switch, the way hunter_core.risk.transitions.record_transition does, '
                    || 'or leave the text the transition that latched it wrote';
        END IF;
        SELECT t.from_state, t.to_state, t.xmin INTO latest
        FROM kill_switch_transitions t
        WHERE t.scope = '{scope}' AND t.scope_id = NEW.id
          AND t.organization_id = {organization}
        ORDER BY t.created_at DESC, t.id DESC
        LIMIT 1;
        IF NOT FOUND
            OR latest.from_state IS DISTINCT FROM OLD.kill_switch_state
            OR latest.to_state IS DISTINCT FROM NEW.kill_switch_state THEN
            RAISE EXCEPTION USING
                MESSAGE = '{subject} ' || NEW.id || ' moved its kill switch from '
                    || OLD.kill_switch_state || ' to ' || NEW.kill_switch_state
                    || ' without an audited transition',
                HINT = 'write the kill_switch_transitions row in the same transaction, and '
                    || 'let it be the newest one for this scope: the state the workers read '
                    || 'and the history a human reads may not disagree, and leaving a '
                    || 'latched block needs a named person';
        END IF;
        IF latest.xmin IS DISTINCT FROM pg_current_xact_id()::xid THEN
            RAISE EXCEPTION USING
                MESSAGE = '{subject} ' || NEW.id || ' moved its kill switch from '
                    || OLD.kill_switch_state || ' to ' || NEW.kill_switch_state
                    || ' citing a transition written by an earlier transaction',
                HINT = 'one move, one row, one transaction: a transition banked earlier '
                    || 'would unblock this wallet again every time it is latched. Write '
                    || 'the row and the column together';
        END IF;
        RETURN NEW;
    END;
"""
"""The audited-move body **this** revision installs, frozen here in full.

A copy of ``0006``'s (``ddl.paper._audited_move_body``) with one branch added at
the top, and it is a copy on purpose: reading ``0006``'s helper at migration time
would let a later edit there silently redefine what ``0008`` installs, which is
the retroactive-change trap §16.5 and §17.1 froze every other list in this
package to avoid. The two do not drift unnoticed —
``test_schema_paper.py::test_the_audited_move_guard_still_proves_the_same_transition``
asserts the three original refusals still bite at head, as the real roles.

The ``downgrade`` is the other direction and calls ``0006``'s own
``create_kill_switch_audit_guard()``: reverting to ``0006`` means the guard
``0006`` describes, and ``ddl/paper.py`` is that description.
"""

_SUBJECTS: tuple[tuple[str, str, str, str], ...] = (
    (KILL_SWITCH_AUDITED, "portfolios", "portfolio", "NEW.organization_id"),
    (ORG_KILL_SWITCH_AUDITED, "organizations", "organization", "NEW.id"),
)
"""``(trigger, table, subject, organization expression)`` — the two guarded latches.

The ``system`` scope has no row (it is process configuration read by
``hunter_core.risk.scopes``), so it has no column to tie to a transition and no
trigger. §18.9 records that absence as deliberate rather than forgotten.
"""


def widen_kill_switch_when() -> None:
    """Fire the two audited-move guards on the motive as well as the state (D4).

    A trigger's ``WHEN`` cannot be altered, so each is dropped and recreated
    around a ``CREATE OR REPLACE`` of its function. Both halves are needed: the
    wider ``WHEN`` is what makes a reason-only rewrite reach the guard at all,
    and the new branch is what makes the refusal say what actually happened
    instead of *"moved its kill switch from WARNING to WARNING"*.
    """
    for trigger, table, subject, organization in _SUBJECTS:
        body = _AUDITED_MOVE_BODY_0008.format(
            subject=subject, scope=subject, organization=organization
        )
        op.execute(
            f"CREATE OR REPLACE FUNCTION {trigger}() RETURNS trigger "
            f"LANGUAGE plpgsql SET search_path = pg_catalog, public AS $${body}$$"
        )
        op.execute(f"DROP TRIGGER {trigger} ON {table}")
        op.execute(
            f"CREATE CONSTRAINT TRIGGER {trigger} AFTER UPDATE ON {table} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW {_WHEN_0008} "
            f"EXECUTE FUNCTION {trigger}()"
        )


def narrow_kill_switch_when() -> None:
    """Put both guards back to what ``0006`` shipped: the state alone.

    Dropped rather than replaced, because ``create_kill_switch_audit_guard``
    issues a plain ``CREATE FUNCTION``. Nothing is lost by reversing — a
    ``kill_switch_reason`` already stored stays exactly as it is; what comes
    back is only the ability to rewrite one without a transition, which is a
    privilege statement and not a fact about data (§19.5).
    """
    for trigger, table, _subject, _organization in _SUBJECTS:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {trigger}()")
    create_kill_switch_audit_guard()
