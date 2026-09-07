"""Who writes the paper wallet, and with which privilege — DATABASE.md §19.

``0007_paper_roles`` answers one question that ``0006`` left open in six
different places: **the worker decides and writes risk state; the API asks,
reads and authorises people.** Until this revision no deployed role could write
one evaluation of the kill switch (T3.6, finding 1), the shared admission
service could not take the organization row lock at all (T3.12, blocking A) and
``hunter_app`` held full DML over the equity curve — the very evidence a resume
reads to believe a wallet recovered (security review of ``0006``, finding 5).

Three moves, and each is a privilege rather than a promise:

- ``hunter_worker`` receives **column** grants, never table ones, on the two
  identity tables it has to touch: ``portfolios (kill_switch_state,
  kill_switch_reason, updated_at)`` — the latch the workers read, its motive and
  the timestamp SQLAlchemy's ``onupdate`` writes with them — and ``organizations
  (updated_at)``, which exists for exactly one reason: PostgreSQL charges
  ``ACL_UPDATE`` for ``SELECT ... FOR SHARE``, and the admission path locks the
  tenant row before the wallet row. Neither grant lets the engine rename a
  wallet, archive it, or move ``organizations.kill_switch_state``. The shape is
  the one ``0006`` measured for ``portfolio_risk_state`` (§18.7): a column grant
  satisfies the row mark and refuses every ``UPDATE`` that writes a value, and a
  privilege — unlike a ``current_user`` test — travels with role inheritance.
  It also receives plain ``INSERT`` on ``portfolios``, because opening a wallet
  is one transaction and the curve moved to the engine
  (:data:`WORKER_INSERT_TABLES_0007`);
- ``hunter_app`` **loses** ``INSERT``/``UPDATE``/``DELETE`` on
  ``portfolio_equity_snapshots`` and ``UPDATE``/``DELETE`` on
  ``trade_proposals``. The curve becomes read-only to the API because it is
  evidence: a single fabricated point at the right timestamp is a recovery the
  resume believes, and RLS does not protect the integrity of a tenant's numbers
  from that tenant's own request handler. The proposal keeps ``INSERT`` because
  filing a manual request *is* the API's job — and only that, which
  :func:`create_request_guard` makes true in the schema instead of in a review;
- the resume stays with the API and moves from TRADER to **OWNER** in
  ``apps/api/hunter_api/routers/risk.py`` (directive §5, "retomar somente com
  minha autorização"). That half is not DDL and is recorded in
  ``docs/SECURITY.md`` §2.

Every list here is **frozen as of this revision**, like ``ddl/tables.py`` as of
``0001`` and ``ddl/paper.py`` as of ``0006``: the privileges the downgrade hands
back are the ones ``0001`` granted, spelled out, not "whatever happens to be
there".

Nothing here depends on session state: the grants are catalogue facts and the
guard reads only ``NEW`` and ``pg_has_role`` — no session prepared statement, no
``LISTEN``/``NOTIFY``, no session advisory lock (§18.10).
"""

from __future__ import annotations

from collections.abc import Mapping

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

WORKER_COLUMN_UPDATES_0007: Mapping[str, tuple[str, ...]] = {
    "portfolios": ("kill_switch_state", "kill_switch_reason", "updated_at"),
    "organizations": ("updated_at",),
}
"""``table -> columns`` ``hunter_worker`` may ``UPDATE`` — and nothing else.

``portfolios``: the engine escalates and clears the latch itself
(``hunter_core.risk.transitions.record_transition``, which writes the state, the
reason and — through ``TimestampMixin.onupdate`` — ``updated_at`` in one
statement, next to the ``kill_switch_transitions`` row the deferred trigger of
§18.7 demands). Everything else about a wallet stays the API's: a worker that
could ``UPDATE portfolios`` at table level could rename it, archive it, or flip
``is_arena`` and free a second principal wallet.

``organizations``: ``updated_at`` alone, and never ``kill_switch_state``.
Blocking a whole organization is a human act performed through the API by an
OWNER; what the worker needs is the *lock*, because
``effective_state(lock=True)`` acquires system → organization (``FOR SHARE``) →
wallet (``FOR UPDATE``) and PostgreSQL demands ``ACL_UPDATE`` for the row mark.
Strictly narrower than the ``DELETE`` the role has held on that table since
``0001`` (§15.4).
"""

WORKER_INSERT_TABLES_0007: tuple[str, ...] = ("portfolios",)
"""``INSERT`` for ``hunter_worker`` — because **opening a wallet is one transaction**.

``open_paper_wallet`` writes the wallet, its lock row, its currency anchor, the
first point of the equity curve and the audit entry in a single commit, and
DATABASE.md §18.2 says plainly that this atomicity is the only proof that the
four were born together. Once the curve became the engine's (see below), the
wallet row had to follow: ``hunter_app`` can no longer write the curve and
``hunter_worker`` could not write ``portfolios``, so the opening had **no role
that could perform it** — the same wall T3.6 hit on the kill switch, one table
over. Measured, not theorised: *permission denied for table portfolios*.

``INSERT`` only. The engine creates a wallet and moves its kill switch; it still
cannot rename one, archive one, flip ``is_arena`` or rewrite its opening capital
(§18.8 keeps those frozen once anchored, and the grant does not reach them). A
second principal wallet stays impossible for everyone —
``uq_portfolios_principal_paper`` is an index, not a privilege.
"""

APP_PRIVILEGES_REVOKED_0007: Mapping[str, tuple[str, ...]] = {
    "portfolio_equity_snapshots": ("INSERT", "UPDATE", "DELETE"),
    "trade_proposals": ("UPDATE", "DELETE"),
}
"""What ``hunter_app`` gives back, table by table — and what the downgrade regrants.

``portfolio_equity_snapshots``: the curve is the durable evidence of a recovery
(``hunter_core.risk.curve``) and the ceiling every rising peak is measured
against (§18.7). With write access, a request handler — or an injection into
one, inside the *correct* organization, where RLS says yes — could write one
point of 20.000 and the next resume would accept a recovery that never happened.
The API reads it; the worker writes it.

``trade_proposals``: ``SELECT`` and ``INSERT`` remain, so a person can file a
manual request; ``UPDATE`` and ``DELETE`` go, because deciding is admission's
job and admission runs as the engine (the FIFO counter lives in
``portfolio_risk_state``, which the API may not write). Without this, a handler
could flip a rejected proposal to ``approved`` or quietly widen a reservation
after the decision that sized it.
"""

REQUEST_GUARD = "trade_proposals_the_app_only_files_requests"

_HAS_APP = f"pg_has_role(current_user, '{APP_ROLE}', 'USAGE')"
_HAS_WORKER = f"pg_has_role(current_user, '{WORKER_ROLE}', 'USAGE')"
_CALLER_IS_THE_APP = f"({_HAS_APP} AND NOT {_HAS_WORKER})"
"""The session holds the API's privileges and nothing beyond them.

Spelled out here rather than imported from :mod:`ddl.paper` for the reason every
list in this package is frozen per revision: ``0006`` describes the schema
``0006`` built, and a later edit there must not silently redefine what ``0007``
installed. The membership test — not ``current_user = 'hunter_app'`` — is the
T3.1b lesson: a login that merely *inherits* the role keeps every privilege
while reporting its own name (§18.7).
"""

_REQUEST_SHAPE = (
    "NEW.source <> 'manual' OR NEW.status <> 'pending' "
    "OR NEW.reservation_state <> 'none' OR NEW.reserved_slot "
    "OR NEW.admission_seq IS NOT NULL OR NEW.decided_at IS NOT NULL "
    "OR NEW.rejection_reason IS NOT NULL OR NEW.risk_decision <> '{}'::jsonb"
)
"""Everything a *request* is not yet: a decision, a place in the queue, a reservation."""


def apply_role_model() -> None:
    """Hand the engine its two column grants and take the API's writes back."""
    for table, columns in WORKER_COLUMN_UPDATES_0007.items():
        op.execute(f"GRANT UPDATE ({', '.join(columns)}) ON {table} TO {WORKER_ROLE}")
    for table in WORKER_INSERT_TABLES_0007:
        op.execute(f"GRANT INSERT ON {table} TO {WORKER_ROLE}")
    for table, privileges in APP_PRIVILEGES_REVOKED_0007.items():
        op.execute(f"REVOKE {', '.join(privileges)} ON {table} FROM {APP_ROLE}")


def revert_role_model() -> None:
    """Give back exactly what ``0001`` granted, and take back only what this added.

    Not ``REVOKE ALL``/``GRANT ALL``: the API keeps the ``SELECT``/``INSERT`` it
    has had all along on both tables, and the worker keeps every table-level
    privilege ``0001``–``0006`` gave it.
    """
    for table, privileges in APP_PRIVILEGES_REVOKED_0007.items():
        op.execute(f"GRANT {', '.join(privileges)} ON {table} TO {APP_ROLE}")
    for table in WORKER_INSERT_TABLES_0007:
        op.execute(f"REVOKE INSERT ON {table} FROM {WORKER_ROLE}")
    for table, columns in WORKER_COLUMN_UPDATES_0007.items():
        op.execute(f"REVOKE UPDATE ({', '.join(columns)}) ON {table} FROM {WORKER_ROLE}")


def create_request_guard() -> None:
    """A proposal the API writes is a *request*, and the schema says so.

    The grant alone stops the API editing a decision; it does not stop the API
    *writing* one, because ``INSERT`` carries every column. Without this guard a
    handler could file a row already stamped ``status = 'approved'`` with a
    ``risk_decision`` of its own making and a reservation attached — a decision
    the Risk Engine never took, indistinguishable afterwards from one it did,
    and holding capital in the participation budget (§18.5).

    So: when the caller is the application role and nothing more, the row has to
    be a request — manual origin, ``pending``, no decision, no rejection, no
    sequence, no reservation. The engine (and an operator) inserts freely; the
    admission service assigns the FIFO place and the reservation under the wallet
    lock afterwards (§18.3).
    """
    op.execute(f"""
CREATE FUNCTION {REQUEST_GUARD}() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
    BEGIN
        IF NOT {_CALLER_IS_THE_APP} THEN
            RETURN NEW;
        END IF;
        IF {_REQUEST_SHAPE} THEN
            RAISE EXCEPTION USING
                MESSAGE = 'trade_proposal ' || NEW.id || ' was filed by ' || current_user
                    || ' carrying a decision: the API files requests, the engine admits them',
                HINT = 'an INSERT by the application role must be a manual request: '
                    || 'source = manual, status = pending, no risk_decision, no '
                    || 'rejection_reason, no decided_at, no admission_seq and no '
                    || 'reservation. The sequence and the reservation are assigned under '
                    || 'the wallet lock by hunter_core.admission, which runs as the engine';
        END IF;
        RETURN NEW;
    END;
$$
""")
    op.execute(
        f"CREATE TRIGGER {REQUEST_GUARD} BEFORE INSERT ON trade_proposals "
        f"FOR EACH ROW EXECUTE FUNCTION {REQUEST_GUARD}()"
    )


def drop_request_guard() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {REQUEST_GUARD} ON trade_proposals")
    op.execute(f"DROP FUNCTION IF EXISTS {REQUEST_GUARD}()")


_DOWNGRADE_GUARDS: tuple[tuple[str, str, str], ...] = (
    (
        "SELECT 1 FROM trade_proposals WHERE request_digest IS NOT NULL",
        "trade_proposals carry a request_digest; dropping the column discards the "
        "canonical identity of the request each decision answered, which is what a "
        "replay of a refusal is compared against (T3.12) and is not derivable from the "
        "four columns that remain",
        "export the digests with their proposal ids before reversing, and clear the "
        "column deliberately, knowing a later replay can no longer tell a repeated "
        "request from a different one that happens to share a key",
    ),
    (
        "SELECT 1 FROM portfolio_equity_snapshots "
        "WHERE brl_unavailable_reason IS NOT NULL OR marks_stale",
        "portfolio_equity_snapshots points declare that their BRL value was "
        "unavailable, or that the marks behind them were stale; dropping the columns "
        "turns each of them back into a point that looks fully priced and freshly "
        "marked, which is the extrapolation DATABASE.md section 18.2 exists to forbid",
        "export those points before reversing — after the downgrade nothing "
        "distinguishes a curve point measured with live marks from one the wallet "
        "could only estimate",
    ),
)


def refuse_a_downgrade_that_would_relabel_a_number() -> None:
    """Reversing is allowed; losing the reason a number is qualified is not.

    Same boundary as §17.7 and §18.9: a guard exists for an obligation still
    standing or for evidence that survives the reversal, never for something
    recomputable. The grants themselves need no guard — a downgrade widens them
    back to ``0001``'s, which is a privilege statement, not a fact about data.
    """
    for count_sql, message, hint in _DOWNGRADE_GUARDS:
        safe_message = message.replace("'", "''")
        safe_hint = hint.replace("'", "''")
        op.execute(
            f"DO $$ DECLARE offenders bigint; BEGIN "  # noqa: S608
            f"SELECT count(*) INTO offenders FROM ({count_sql}) AS offending; "
            f"IF offenders > 0 THEN RAISE EXCEPTION USING "
            f"MESSAGE = 'PROJECT HUNTER: ' || offenders || ' {safe_message}', "
            f"HINT = '{safe_hint}'; END IF; END $$;"
        )
