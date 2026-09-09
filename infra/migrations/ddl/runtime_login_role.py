"""``0015_runtime_login_role`` — the login the runtime connects with.

Until this revision ``DATABASE_URL`` and ``DATABASE_URL_MIGRATIONS`` were the
**same credential**: ``hunter``, ``rolsuper = true``, ``rolbypassrls = true``.
``hunter_app`` and ``hunter_worker`` are ``NOLOGIN`` roles granted to it
(``ddl/security.py``), so the ``SET LOCAL ROLE`` in
``hunter_core.db.session._apply_context`` was a **voluntary** reduction that a
single ``RESET ROLE`` undid. ``0011`` may revoke every write on
``strategy_versions`` from ``hunter_worker`` and it changes nothing if the
process holding the connection can simply stop being ``hunter_worker``.
``.claude/state/review-T3.15-security.md`` HIGH 1; ``docs/DATABASE.md`` §23.5.

This revision creates ``hunter_runtime``: a real login role, member of
``hunter_app`` and ``hunter_worker`` **and of nothing else**, that owns nothing,
cannot bypass RLS, cannot create a role or a database, and is not a superuser.

**``NOINHERIT`` is the decision, not a detail.** With the default ``INHERIT`` the
login would carry the *union* of both roles' ACLs with no ``SET ROLE`` at all —
and, worse, ``pg_has_role(current_user, 'hunter_app', 'USAGE')`` and
``pg_has_role(current_user, 'hunter_worker', 'USAGE')`` would both be **true**.
Every guard the schema writes to tell "the application and nothing but it" from
"the engine and nothing but it" is spelled exactly that way —
``trade_proposals_the_app_only_files_requests`` (§19.4/§21.2) fires on
``pg_has_role(app) AND NOT pg_has_role(worker)``, ``portfolios_are_born_audited``
(§20.2) on the mirror image — so a connection that satisfies *both* sides fires
**neither**: the schema reads it as the operator. Holding the union of the
privileges, that is an ``INSERT INTO trade_proposals`` already ``approved`` with
a ``risk_decision`` the Risk Engine never took. Closing the front door by
reopening the window §19.4 exists to shut.

With ``NOINHERIT`` the login has **no privilege of its own**: a code path that
forgets ``SET LOCAL ROLE`` fails loudly with *permission denied* instead of
running with the union, ``RESET ROLE`` hands back nothing, and after
``SET LOCAL ROLE hunter_app`` the ``current_user`` **is** ``hunter_app``, so
every guard bites exactly as it does today. ``SET ROLE`` itself keeps working:
it depends on the membership's ``SET`` option, never on ``INHERIT``.

``BYPASSRLS`` still reaches the workers, because a role *attribute* is never
inherited in either direction: ``SET ROLE hunter_worker`` makes ``GetUserId()``
be ``hunter_worker``, and ``check_enable_rls`` reads the current role's own
``rolbypassrls``. Measured in
``test_runtime_login_role.py``, not assumed.

**No password, ever, in this repository.** The migration creates the role
without one; the operator sets it out of band (``ALTER ROLE hunter_runtime
PASSWORD …``, step (b) of ``docs/DEPLOYMENT.md`` §3.5). The migration also does
not *claim* anything about it: ``pg_authid.rolpassword`` is superuser-only, so
there is nothing it could honestly verify.

**No table ``GRANT``.** The runtime's privilege is exactly ``hunter_app``'s and
``hunter_worker``'s, reached by ``SET ROLE``. Granting the login anything of its
own would create a third ACL to keep in step — the no-op-that-looks-like-a-
guarantee §15.6 records and §24.5 refuses to repeat.

Every list here is frozen as of this revision, the rule ``ddl/shadow.py``,
``ddl/analysis.py``, ``ddl/paper*.py``, ``ddl/strategy_purpose.py``,
``ddl/replication.py`` and ``ddl/replay_runs.py`` state for their own.

Described in ``docs/DATABASE.md`` §27.
"""

from __future__ import annotations

from alembic import op

from hunter_core.db.models import APP_ROLE, WORKER_ROLE

RUNTIME_ROLE = "hunter_runtime"
"""The login role every runtime process connects as, from ``0015`` on.

It is deliberately *not* in ``hunter_core.db.models`` next to ``APP_ROLE`` and
``WORKER_ROLE``: those two are named by grants and policies all over the schema,
this one is named by nothing but this revision and the DSN. It is also **not** in
``hunter_core.db.session.DB_ROLES`` — nothing ever does ``SET ROLE
hunter_runtime``; it is where a session *starts*, never somewhere it goes.
"""

RUNTIME_MEMBER_OF_0015: tuple[str, ...] = (APP_ROLE, WORKER_ROLE)
"""The complete membership of the runtime login, frozen.

Two roles, and the migration **refuses** if the role is a member of a third: the
membership list *is* this role's entire security boundary, so an extra one is
not a detail to notice later. Widening it is a revision, never a ``GRANT`` a
human runs once and nobody reads again.
"""

RUNTIME_ATTRIBUTES_0015: tuple[str, ...] = (
    "LOGIN",
    "NOSUPERUSER",
    "NOCREATEDB",
    "NOCREATEROLE",
    "NOBYPASSRLS",
    "NOREPLICATION",
    "NOINHERIT",
)
"""What the role must be. Verified against ``pg_roles`` after the attempt to set
it, in the ``create_roles()`` pattern of §15.6: try, tolerate not being allowed
to, then prove the *outcome* — never degrade to a ``NOTICE`` and carry on."""

_SUPERUSER_ONLY = ("NOSUPERUSER", "NOBYPASSRLS", "NOREPLICATION")
"""The three attributes only a superuser may change — even to the value they
already hold. Split from the rest so a merely ``CREATEROLE`` migrating role (the
usual shape on a managed Postgres) can still fix ``LOGIN``/``NOINHERIT``/
``NOCREATEDB``/``NOCREATEROLE`` instead of losing the whole ``ALTER``."""

_OTHER_ATTRIBUTES = tuple(a for a in RUNTIME_ATTRIBUTES_0015 if a not in _SUPERUSER_ONLY)

_CREATE_STATEMENT = f"CREATE ROLE {RUNTIME_ROLE} {' '.join(RUNTIME_ATTRIBUTES_0015)};"
_GRANT_STATEMENTS = " ".join(
    f"GRANT {role} TO {RUNTIME_ROLE} WITH INHERIT FALSE, SET TRUE;"
    for role in RUNTIME_MEMBER_OF_0015
)
MANUAL_STEP_0015 = f"{_CREATE_STATEMENT} {_GRANT_STATEMENTS}"
"""What an operator has to run as a superuser when the migrating role may not
create roles — the exact statements, in the exception message, so the fix is a
copy and not an investigation (the lesson ``create_roles()`` records)."""


def _tolerate(body: str, notice: str) -> str:
    """A ``DO`` block that runs ``body`` and turns *insufficient_privilege* into a
    notice.

    Tolerating is never the end of the story here: every one of these is followed
    by a verification that reads the catalogue and raises if the outcome is
    wrong. Silence is what §15.6 calls out as the bug — a notice read as a
    warning, and a schema deployed with the wrong role.
    """
    return (
        f"DO $$ BEGIN {body} "
        f"EXCEPTION WHEN insufficient_privilege THEN RAISE NOTICE '{notice}'; END $$;"
    )


def create_runtime_login_role() -> None:
    """Create (or normalize) ``hunter_runtime``, grant the two memberships and
    ``CONNECT``, then prove all three in the catalogue.

    Idempotent by construction: ``CREATE ROLE`` tolerates ``duplicate_object``,
    ``ALTER ROLE`` states the attributes unconditionally, ``GRANT`` a membership
    that already exists is a no-op, and ``GRANT CONNECT`` twice is one grant.
    """
    _create_role()
    _normalize_attributes()
    _prove_the_role_is_what_it_claims()
    _grant_memberships()
    _prove_the_membership_is_exactly_two_and_does_not_inherit()
    _grant_connect()
    _prove_connect()


def drop_runtime_login_role() -> None:
    """Reverse :func:`create_runtime_login_role`, and drop the role **only if
    nothing else depends on it**.

    A role is a *cluster* object; a migration is a *database* one. Another
    database in the same cluster may already be on ``0015`` — it is literally the
    case in the test container, which holds four — and each one's ``GRANT
    CONNECT`` leaves a row in ``pg_shdepend``. An unconditional ``DROP ROLE``
    would either fail with *dependent objects still exist* or take the login away
    from a database still using it.

    So: revoke this database's ``CONNECT``, revoke both memberships, and drop the
    role only when it owns nothing and nothing else depends on it. A login with
    no membership and no ``CONNECT`` reaches nothing, which is why leaving it
    standing is not leaving privilege behind — and it is the precedent ``0001``
    set by never dropping ``hunter_app``/``hunter_worker`` either.

    **Declared:** membership is cluster-wide, so reversing in *one* database
    revokes it for every database in that cluster. That is inherent to a cluster
    role and equally true of the upgrade's ``CREATE ROLE``; the VPS has one
    database.
    """
    _revoke_connect()
    _revoke_memberships()
    _drop_role_if_nothing_depends_on_it()


def _create_role() -> None:
    op.execute(
        f"DO $$ BEGIN CREATE ROLE {RUNTIME_ROLE} {' '.join(RUNTIME_ATTRIBUTES_0015)}; "
        f"EXCEPTION WHEN duplicate_object THEN "
        f"RAISE NOTICE 'role {RUNTIME_ROLE} already exists; normalizing its attributes'; "
        f"WHEN insufficient_privilege THEN "
        f"RAISE NOTICE 'cannot create role {RUNTIME_ROLE}; create it with a superuser role'; "
        f"END $$;"
    )


def _normalize_attributes() -> None:
    """State the attributes on a role that may pre-date this revision.

    This is the half that *fixes* a role somebody created by hand with the wrong
    shape — a ``hunter_runtime`` that inherits, or that carries ``BYPASSRLS``,
    is worse than no role at all, because the DSN would look correct.
    """
    for attributes in (_SUPERUSER_ONLY, _OTHER_ATTRIBUTES):
        clause = " ".join(attributes)
        op.execute(
            _tolerate(
                # S608: every interpolated fragment is a constant of this module.
                f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') "  # noqa: S608
                f"THEN ALTER ROLE {RUNTIME_ROLE} {clause}; END IF;",
                f"cannot set [{clause}] on {RUNTIME_ROLE}; a superuser must run: "
                f"ALTER ROLE {RUNTIME_ROLE} {clause};",
            )
        )


def _prove_the_role_is_what_it_claims() -> None:
    """Read ``pg_roles`` and refuse unless every attribute holds.

    The §15.6 pattern: what is verified is the *outcome*, not the statement.
    A missing role, a role that cannot log in, or a role carrying any of the four
    powers this one must not have, stops the migration here with the exact
    statements to run — instead of a hundred statements later, or never.
    """
    op.execute(
        # S608: every interpolated fragment is a constant of this module.
        "DO $$ DECLARE wrong text[] := '{}'; "  # noqa: S608
        "can_login boolean; is_super boolean; can_bypass boolean; "
        "can_createrole boolean; can_createdb boolean; does_inherit boolean; "
        "can_replicate boolean; BEGIN "
        "SELECT rolcanlogin, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, "
        "rolinherit, rolreplication "
        "INTO can_login, is_super, can_bypass, can_createrole, can_createdb, "
        "does_inherit, can_replicate "
        f"FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}'; "
        "IF NOT FOUND THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: the runtime login role {RUNTIME_ROLE} is missing' "
        "USING HINT = 'the migrating role may not create roles on this server. Run as a "
        f"superuser, then re-run the migration: {MANUAL_STEP_0015}'; END IF; "
        "IF NOT can_login THEN wrong := wrong || 'LOGIN'; END IF; "
        "IF is_super THEN wrong := wrong || 'NOSUPERUSER'; END IF; "
        "IF can_bypass THEN wrong := wrong || 'NOBYPASSRLS'; END IF; "
        "IF can_createrole THEN wrong := wrong || 'NOCREATEROLE'; END IF; "
        "IF can_createdb THEN wrong := wrong || 'NOCREATEDB'; END IF; "
        "IF can_replicate THEN wrong := wrong || 'NOREPLICATION'; END IF; "
        "IF does_inherit THEN wrong := wrong || 'NOINHERIT'; END IF; "
        "IF cardinality(wrong) > 0 THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: the runtime login role {RUNTIME_ROLE} carries the "
        "wrong attributes; it still needs: %', array_to_string(wrong, ' ') "
        f"USING HINT = 'run as a superuser: ALTER ROLE {RUNTIME_ROLE} ' || "
        "array_to_string(wrong, ' ') || ';'; END IF; END $$;"
    )


def _grant_memberships() -> None:
    """``hunter_app`` and ``hunter_worker``, explicitly non-inheriting.

    ``WITH INHERIT FALSE`` restates what ``NOINHERIT`` on the role already
    decides, because a membership carries its own option since Postgres 16 and a
    later ``ALTER ROLE hunter_runtime INHERIT`` must not quietly turn the union
    back on for a membership granted under the old default.
    """
    for role in RUNTIME_MEMBER_OF_0015:
        op.execute(
            _tolerate(
                f"GRANT {role} TO {RUNTIME_ROLE} WITH INHERIT FALSE, SET TRUE;",
                f"cannot grant {role} to {RUNTIME_ROLE}; a superuser must run: "
                f"GRANT {role} TO {RUNTIME_ROLE} WITH INHERIT FALSE, SET TRUE;",
            )
        )


def _prove_the_membership_is_exactly_two_and_does_not_inherit() -> None:
    """Both memberships usable by ``SET ROLE``, neither one inherited, and no third.

    ``pg_has_role(role, other, 'MEMBER')`` is "may ``SET ROLE``";
    ``'USAGE'`` is "already holds the privileges without ``SET ROLE``". Asking the
    two questions separately is what proves ``NOINHERIT`` is doing its job —
    reading ``rolinherit`` alone would miss a membership granted ``WITH INHERIT
    TRUE``.

    The third check is the boundary itself: this role's entire security surface is
    *which roles it may become*, so a membership nobody wrote down here stops the
    migration rather than being discovered by a security review later.
    """
    members = ", ".join(f"('{role}')" for role in RUNTIME_MEMBER_OF_0015)
    allowed = ", ".join(f"'{role}'" for role in RUNTIME_MEMBER_OF_0015)
    op.execute(
        # S608: every interpolated fragment is a constant defined in this module.
        "DO $$ DECLARE missing text; inherited text; extra text; BEGIN "  # noqa: S608
        "SELECT string_agg(r.name, ', ') INTO missing FROM "
        f"(VALUES {members}) AS r(name) "
        f"WHERE NOT pg_has_role('{RUNTIME_ROLE}', r.name, 'MEMBER'); "
        "IF missing IS NOT NULL THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: {RUNTIME_ROLE} is not a member of: %', missing "
        f"USING HINT = 'run as a superuser: {_GRANT_STATEMENTS}'; END IF; "
        "SELECT string_agg(r.name, ', ') INTO inherited FROM "
        f"(VALUES {members}) AS r(name) "
        f"WHERE pg_has_role('{RUNTIME_ROLE}', r.name, 'USAGE'); "
        "IF inherited IS NOT NULL THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: {RUNTIME_ROLE} inherits the privileges of: % - "
        "the runtime login must hold nothing until it does SET ROLE (DATABASE.md 27.1)', "
        "inherited "
        f"USING HINT = 'run as a superuser: ALTER ROLE {RUNTIME_ROLE} NOINHERIT; "
        f"{_GRANT_STATEMENTS}'; END IF; "
        "SELECT string_agg(g.rolname, ', ') INTO extra "
        "FROM pg_auth_members m JOIN pg_roles g ON g.oid = m.roleid "
        f"WHERE m.member = (SELECT oid FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') "
        f"AND g.rolname NOT IN ({allowed}); "
        "IF extra IS NOT NULL THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: {RUNTIME_ROLE} is also a member of: % - the "
        "runtime login is a member of hunter_app and hunter_worker only', extra "
        f"USING HINT = 'revoke it (REVOKE <role> FROM {RUNTIME_ROLE};) or widen "
        "RUNTIME_MEMBER_OF_0015 in a new revision - never by hand'; END IF; END $$;"
    )


def _grant_connect() -> None:
    """``GRANT CONNECT`` on the database the migration is running in.

    Dynamic SQL because the database name is not a literal — ``quote_ident``
    rather than a format placeholder so nothing in this string can be mistaken
    for a DBAPI parameter marker.
    """
    op.execute(
        _tolerate(
            "EXECUTE 'GRANT CONNECT ON DATABASE ' || quote_ident(current_database()) || "
            f"' TO {RUNTIME_ROLE}';",
            f"cannot grant CONNECT to {RUNTIME_ROLE}; PUBLIC holds it by default, so this "
            "is only a problem where CONNECT was revoked from PUBLIC",
        )
    )


def _prove_connect() -> None:
    """The runtime can reach this database — the outcome, not the statement.

    ``PUBLIC`` holds ``CONNECT`` by default, so this passes even where the
    ``GRANT`` above was refused. That is the point: what has to be true is that
    the runtime can open a connection, not that a particular command ran.
    """
    op.execute(
        "DO $$ BEGIN IF NOT has_database_privilege("
        f"'{RUNTIME_ROLE}', current_database(), 'CONNECT') THEN "
        f"RAISE EXCEPTION 'PROJECT HUNTER: {RUNTIME_ROLE} cannot CONNECT to %', "
        "current_database() "
        "USING HINT = 'run as the database owner: GRANT CONNECT ON DATABASE <db> TO "
        f"{RUNTIME_ROLE};'; END IF; END $$;"
    )


def _revoke_connect() -> None:
    op.execute(
        _tolerate(
            # S608: every interpolated fragment is a constant of this module.
            f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN "  # noqa: S608
            "EXECUTE 'REVOKE CONNECT ON DATABASE ' || quote_ident(current_database()) || "
            f"' FROM {RUNTIME_ROLE}'; END IF;",
            f"cannot revoke CONNECT from {RUNTIME_ROLE}",
        )
    )


def _revoke_memberships() -> None:
    roles = ", ".join(RUNTIME_MEMBER_OF_0015)
    op.execute(
        _tolerate(
            # S608: every interpolated fragment is a constant of this module.
            f"IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN "  # noqa: S608
            f"REVOKE {roles} FROM {RUNTIME_ROLE}; END IF;",
            f"cannot revoke [{roles}] from {RUNTIME_ROLE}; a superuser must run: "
            f"REVOKE {roles} FROM {RUNTIME_ROLE};",
        )
    )


def _drop_role_if_nothing_depends_on_it() -> None:
    """Drop the login only when it owns nothing and nothing still references it.

    Both halves are needed. Ownership is the brief's condition ("drop the role
    only if it owns nothing"); ``pg_shdepend`` is the half the brief could not
    know about, because it is where *another database's* ``GRANT CONNECT`` lives.
    Neither is a failure: a role that survives here has no membership and no
    ``CONNECT`` in this database, so it reaches nothing, and the notice says so
    out loud rather than a downgrade pretending it removed something it did not.

    **Both branches announce themselves** (security review of T3.15f, MEDIUM 2).
    The branch that keeps the role always said so; the branch that *drops* it was
    silent, and it is the one that happens on the VPS — one database, a role that
    owns nothing. Dropping the login takes its password with it, and the very
    next ``compose.sh update`` runs ``alembic upgrade head``, which recreates the
    role **without a password** while ``HUNTER_RUNTIME_DB_PASSWORD`` is still in
    the ``.env``: ``api`` and every worker then fail authentication at boot with
    a credential that looks correct in every file. So the drop says, in the
    migration output, that step (b) of ``docs/DEPLOYMENT.md`` §3.5 has to be
    redone. A notice is not a guarantee — the guarantee is the runbook's rollback
    step, which this sentence exists to make impossible to miss.
    """
    op.execute(
        # S608: every interpolated fragment is a constant of this module.
        "DO $$ DECLARE role_oid oid; owned bigint; referenced bigint; BEGIN "  # noqa: S608
        f"SELECT oid INTO role_oid FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}'; "
        "IF role_oid IS NULL THEN RETURN; END IF; "
        "SELECT count(*) INTO owned FROM ("
        "SELECT 1 FROM pg_class WHERE relowner = role_oid "
        "UNION ALL SELECT 1 FROM pg_namespace WHERE nspowner = role_oid "
        "UNION ALL SELECT 1 FROM pg_proc WHERE proowner = role_oid "
        "UNION ALL SELECT 1 FROM pg_type WHERE typowner = role_oid "
        "UNION ALL SELECT 1 FROM pg_database WHERE datdba = role_oid) owner_rows; "
        "SELECT count(*) INTO referenced FROM pg_shdepend "
        "WHERE refclassid = 'pg_authid'::regclass AND refobjid = role_oid; "
        "IF owned > 0 OR referenced > 0 THEN "
        f"RAISE NOTICE 'role {RUNTIME_ROLE} owns % object(s) and is referenced by % "
        "dependency row(s) (another database in this cluster may still be on 0015); "
        "leaving it in place - it has no membership and no CONNECT here', owned, referenced; "
        f"ELSE DROP ROLE {RUNTIME_ROLE}; "
        f"RAISE NOTICE 'dropped role {RUNTIME_ROLE}, and its password went with it. "
        "A later upgrade recreates the role WITHOUT a password, so redo step (b) of "
        "docs/DEPLOYMENT.md 3.5 (ALTER ROLE ... PASSWORD, with the value already in "
        "the .env) before bringing api and the workers back up, or they will fail to "
        "authenticate.'; END IF; "
        "EXCEPTION WHEN insufficient_privilege OR dependent_objects_still_exist THEN "
        f"RAISE NOTICE 'could not drop role {RUNTIME_ROLE}; it keeps no membership and no "
        "CONNECT in this database'; END $$;"
    )
