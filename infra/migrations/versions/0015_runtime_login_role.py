"""the runtime stops connecting as the owner: a login role without superuser

Fifteenth revision. **No table, no column, no index, no enum, no trigger, no
policy, no partition and no ``GRANT`` on any relation** — one cluster role, two
memberships and one ``CONNECT``. It closes ``.claude/state/review-T3.15-security.md``
HIGH 1 for real, which the T3.15d split of the compose anchors only narrowed:
that task took ``DATABASE_URL_MIGRATIONS`` out of every runtime container's
environment, and the ``DATABASE_URL`` left behind was **the same owner
credential** (``hunter``: ``rolsuper``, ``rolbypassrls``). ``hunter_app`` and
``hunter_worker`` are ``NOLOGIN`` roles granted to it, so the ``SET LOCAL ROLE``
in ``hunter_core.db.session`` was a voluntary reduction one ``RESET ROLE``
undoes: an RCE in ``api`` or in any worker could ``ALTER TABLE … DISABLE ROW
LEVEL SECURITY`` or set ``strategy_versions.purpose = 'paper'`` regardless of
everything ``0010``/``0011`` revoked.

``hunter_runtime`` is ``LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
NOREPLICATION NOINHERIT``, a member of ``hunter_app`` and ``hunter_worker`` and
of nothing else. **``NOINHERIT`` is the decision** and the reason is in
``ddl/runtime_login_role.py``: an inheriting login satisfies *both* sides of
every ``pg_has_role(app) AND NOT pg_has_role(worker)`` guard the schema uses to
tell the API from the engine (§19.4, §20.2), so it fires **neither** — the
schema would read the runtime as the operator, holding the union of both ACLs.
``BYPASSRLS`` still reaches the workers, because a role attribute is not
inherited in either direction and ``SET ROLE hunter_worker`` makes the current
role be ``hunter_worker``.

**Idempotent, and with no password anywhere.** ``CREATE ROLE`` tolerates
``duplicate_object``, the attributes are stated unconditionally afterwards (which
is also what repairs a role someone created by hand with the wrong shape), and
each attempt is followed by a **verification against the catalogue** that raises
with the exact statements to run — the ``create_roles()`` pattern of §15.6,
never a notice read as a warning. The password is the operator's, out of band
(``docs/DEPLOYMENT.md`` §3.5 step (b)); the migration does not set it and does
not claim anything about it, because ``pg_authid.rolpassword`` is superuser-only
and there is nothing it could honestly check.

**Downgrade** revokes this database's ``CONNECT`` and both memberships, and drops
the role **only if it owns nothing and nothing else references it** — a role is a
cluster object and another database in the same cluster may still be on ``0015``.
Left standing, it has no membership and no ``CONNECT`` here, so it reaches
nothing.

**Nothing here depends on session state:** one role, two memberships, one
database grant. No session prepared statement, no ``LISTEN``/``NOTIFY``, no
session advisory lock. No ``ALTER TABLE``, so no lock on any relation and no
maintenance window (unlike ``0010``/``0012``).

**Named ``0015_runtime_login_role`` (23 characters)** —
``alembic_version.version_num`` is ``VARCHAR(32)`` (§17.6). Described in
``docs/DATABASE.md`` §27, with §23.5 rewritten to say that HIGH 1 closes only
after steps (a)–(e) of the runbook, not when this revision is applied.

Revision ID: 0015_runtime_login_role
Revises: 0014_lab_signals_indexes
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

from ddl.runtime_login_role import create_runtime_login_role, drop_runtime_login_role

revision: str = "0015_runtime_login_role"
down_revision: str | None = "0014_lab_signals_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    create_runtime_login_role()


def downgrade() -> None:
    """No guard, and the absence is an assertion.

    §17.7 protects *data*: a guard exists where reversing would lose an
    obligation or a piece of evidence. This revision stores no row anywhere — it
    declares who may connect. What the downgrade gives back is the previous
    deployment shape (the runtime connecting as the owner), which is a statement
    about credentials, never a fact about data, exactly like the grants of
    ``0007`` (§19.5) and ``0008`` (§20.5).

    The operational half is not free, though, and it is written down in
    ``docs/DEPLOYMENT.md`` §3.5: reversing this revision while ``DATABASE_URL``
    still names ``hunter_runtime`` leaves every runtime process unable to reach a
    single table. Roll the DSN back **first**, then the revision — which is why
    the rollback path in the runbook does not need this downgrade at all.
    """
    drop_runtime_login_role()
