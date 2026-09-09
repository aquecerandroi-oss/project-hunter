"""What ``hunter_runtime`` can actually do — proved by logging in as it.

DATABASE.md §27. Every other privilege test in this suite connects as the
container's owner and does ``SET LOCAL ROLE``; that is exactly the arrangement
``.claude/state/review-T3.15-security.md`` HIGH 1 says proves nothing about the
deployed system, because the owner can ``RESET ROLE`` back. So this module opens
a **real connection** with the login role ``0015`` creates — password generated
here and applied by the owner, never written in the repository — and asks the
questions from the outside:

- it is not the owner, and carries none of the four powers (§27.1);
- **without** ``SET ROLE`` it reaches no table at all, which is what ``NOINHERIT``
  buys and what makes a missing ``SET LOCAL ROLE`` a loud failure instead of a
  silent escalation;
- **with** ``SET LOCAL ROLE hunter_app`` the RLS policies bite: organization A
  cannot read organization B (§1.2);
- **with** ``SET LOCAL ROLE hunter_worker`` ``BYPASSRLS`` still applies, because a
  role attribute is read from the *current* role and is never inherited;
- ``ALTER TABLE … DISABLE ROW LEVEL SECURITY`` and
  ``UPDATE strategy_versions SET purpose = 'paper'`` — the two statements the
  finding names — are refused in every role it can reach;
- the guards that tell the API from the engine (§19.4, §20.2) still see them
  apart, which is the property an inheriting login would have destroyed.
"""

from __future__ import annotations

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.db.session import create_session_factory, role_session, tenant_session
from hunter_core.domain.types import uuid7

from .conftest import alembic_config, async_engine, create_database, migration_ddl

pytestmark = pytest.mark.integration

RUNTIME_DB = "hunter_runtime_login"
_DENIED = "permission denied"


@pytest.fixture(scope="module")
def runtime_db(container_url: str) -> Iterator[str]:
    """A database of its own, at ``head`` — so ``0015`` has actually run here.

    Its own database and not ``migrated_schema_db`` because this module inserts
    organizations that must not exist for anybody else's ``tenant_isolation``
    assertions, and because the login role is what is under test: a shared
    database would make a failure here ambiguous between "the role is wrong" and
    "somebody else's row was visible".
    """
    url = asyncio.run(create_database(container_url, RUNTIME_DB))
    command.upgrade(alembic_config(url), "head")
    yield url


@pytest.fixture(scope="module")
def runtime_url(runtime_db: str) -> str:
    """The DSN a runtime container would get, with a password minted right here.

    The password is ``secrets.token_hex`` and lives for the length of this
    module. That is the whole point of ``0015`` not setting one: a password in
    the repository is not a password, and the only place one may be typed is an
    operator's ``ALTER ROLE`` (``docs/DEPLOYMENT.md`` §3.5 step (b)) — which is
    literally what the statement below is.
    """
    runtime = migration_ddl("runtime_login_role")
    role: str = runtime.RUNTIME_ROLE
    password = secrets.token_hex(16)  # hex only: safe to interpolate into DDL

    async def _set_password() -> None:
        engine = async_engine(runtime_db)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(f"ALTER ROLE {role} PASSWORD '{password}'"))
        finally:
            await engine.dispose()

    asyncio.run(_set_password())
    # ``render_as_string(hide_password=False)``: ``str(URL)`` masks the password
    # as ``***``, which is right for a log and useless as a DSN.
    return (
        make_url(runtime_db)
        .set(username=role, password=password)
        .render_as_string(hide_password=False)
    )


@pytest_asyncio.fixture
async def runtime_engine(runtime_url: str) -> AsyncIterator[AsyncEngine]:
    """An engine that logs in as ``hunter_runtime`` — the deployed shape."""
    engine = async_engine(runtime_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def owner_engine(runtime_db: str) -> AsyncIterator[AsyncEngine]:
    """The owner connection, used only to seed rows the runtime must not forge."""
    engine = async_engine(runtime_db)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def two_organizations(owner_engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    """Organization A and organization B, each with one workspace.

    Seeded as the owner on purpose: the runtime login is the thing under test, so
    nothing it does may be part of building the fixture. ``workspaces`` is the
    tenant table used for the isolation assertion — it carries
    ``organization_id NOT NULL``, RLS enabled and forced, and its own
    ``tenant_isolation`` policy since ``0001`` (§1.2), with none of the triggers
    ``portfolios`` carries to get in the way of a fixture.
    """
    org_a, org_b = uuid7(), uuid7()
    async with owner_engine.begin() as connection:
        for org in (org_a, org_b):
            # ``uuid4``, not a slice of the ``uuid7``: the first hex digits of a
            # v7 are its millisecond, so two organizations minted in the same
            # tick produce the same slug and collide on ``uq_organizations_slug``.
            slug = f"rt-{uuid.uuid4().hex[:10]}"
            await connection.execute(
                text("INSERT INTO organizations (id, slug, name) VALUES (:id, :slug, :slug)"),
                {"id": org, "slug": slug},
            )
            await connection.execute(
                text(
                    "INSERT INTO workspaces (id, organization_id, name, objective) "
                    "VALUES (:id, :org, :name, 'paper_trading')"
                ),
                {"id": uuid7(), "org": org, "name": slug},
            )
    return org_a, org_b


async def test_the_runtime_login_is_not_the_owner_and_holds_no_power(
    runtime_engine: AsyncEngine,
) -> None:
    """The verification query of the runbook's step (e), run for real.

    ``current_user`` is the login, not ``hunter``/the container owner, and every
    one of the five attributes is off. Each is a way the finding stays open:
    ``rolsuper``/``rolbypassrls`` make ``SET LOCAL ROLE`` decorative again,
    ``rolcreaterole`` lets a compromised process mint a better credential for
    itself, and ``rolinherit`` hands it both application roles at once (§27.1).
    """
    runtime = migration_ddl("runtime_login_role")
    role: str = runtime.RUNTIME_ROLE

    async with runtime_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    "SELECT current_user, r.rolsuper, r.rolbypassrls, r.rolcreaterole, "
                    "r.rolcreatedb, r.rolinherit FROM pg_roles r WHERE r.rolname = current_user"
                )
            )
        ).one()

    assert row[0] == role
    assert list(row[1:]) == [False, False, False, False, False], row


async def test_without_set_role_the_runtime_login_reaches_no_table(
    runtime_engine: AsyncEngine,
) -> None:
    """``NOINHERIT``, measured: the login holds nothing of its own.

    This is the difference between the two designs. An inheriting login would
    read this table happily — it would hold the union of ``hunter_app``'s and
    ``hunter_worker``'s grants with no ``SET ROLE`` at all — and, because
    ``pg_has_role(current_user, …, 'USAGE')`` would then be true for *both*
    roles, every guard written as "the app and nothing but it" or "the engine and
    nothing but it" would stop firing (§27.1). Here, forgetting ``SET LOCAL
    ROLE`` is a loud error instead of a quiet escalation.
    """
    async with runtime_engine.connect() as connection:
        with pytest.raises(ProgrammingError, match=_DENIED):
            await connection.execute(text("SELECT count(*) FROM workspaces"))


async def test_org_a_cannot_read_org_bs_rows_through_the_runtime_login(
    runtime_engine: AsyncEngine, two_organizations: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """The RLS isolation test (§1.2), through the credential production will use.

    Same code path the API uses — ``tenant_session`` opens the transaction, sets
    ``SET LOCAL ROLE hunter_app`` and then ``app.current_org`` — only now the
    connection underneath is a login that *cannot* undo the role. Organization A
    sees its own workspace and exactly zero of B's, in both directions.
    """
    org_a, org_b = two_organizations
    factory = create_session_factory(runtime_engine)

    for mine, theirs in ((org_a, org_b), (org_b, org_a)):
        async with tenant_session(factory, mine) as session:
            visible = (
                (
                    await session.execute(
                        text("SELECT organization_id FROM workspaces ORDER BY organization_id")
                    )
                )
                .scalars()
                .all()
            )
        assert visible == [mine], visible
        assert theirs not in visible


async def test_the_engine_role_still_bypasses_rls_through_the_runtime_login(
    runtime_engine: AsyncEngine, two_organizations: tuple[uuid.UUID, uuid.UUID]
) -> None:
    """``SET ROLE hunter_worker`` still scans every organization.

    A role *attribute* is never inherited in either direction, so a
    ``NOBYPASSRLS`` login losing the workers' ability to scan the whole schema
    was the obvious way this revision could have broken the system quietly.
    ``check_enable_rls`` reads ``rolbypassrls`` of the **current** role, and after
    ``SET ROLE`` the current role is ``hunter_worker`` — measured here rather
    than argued from the manual.
    """
    org_a, org_b = two_organizations
    factory = create_session_factory(runtime_engine)

    async with role_session(factory, db_role="hunter_worker") as session:
        visible = (
            (await session.execute(text("SELECT organization_id FROM workspaces"))).scalars().all()
        )

    assert {org_a, org_b} <= set(visible)


async def test_the_runtime_login_cannot_disable_row_level_security(
    runtime_engine: AsyncEngine,
) -> None:
    """The first statement the finding names, refused in all three roles it can be.

    ``ALTER TABLE`` is an owner-only operation, and the runtime owns nothing —
    which is the whole reason the role owns nothing. ``hunter_app`` and
    ``hunter_worker`` are checked too because "it cannot do it as itself" would
    be worthless if one ``SET ROLE`` away it could.
    """
    statement = "ALTER TABLE portfolios DISABLE ROW LEVEL SECURITY"

    for role in (None, "hunter_app", "hunter_worker"):
        async with runtime_engine.connect() as connection:
            await connection.begin()
            if role is not None:
                await connection.execute(text(f"SET LOCAL ROLE {role}"))
            with pytest.raises(DBAPIError) as raised:
                await connection.execute(text(statement))
            assert "must be owner of table portfolios" in str(raised.value), (role, raised.value)


async def test_the_runtime_login_cannot_promote_a_strategy_version_to_paper(
    runtime_engine: AsyncEngine,
) -> None:
    """The second statement the finding names — refused before any row is read.

    A privilege failure precedes execution, so this holds on an empty table too:
    the point is the ACL, not the population. Bare, the login has no privilege at
    all on ``strategy_versions`` (``NOINHERIT``); as ``hunter_worker`` it is the
    column grant of ``0010``/``0011`` (§22.3) that refuses ``purpose``; as
    ``hunter_app`` the table has been ``SELECT``-only since ``0001``.
    """
    statement = "UPDATE strategy_versions SET purpose = 'paper'"

    for role in (None, "hunter_app", "hunter_worker"):
        async with runtime_engine.connect() as connection:
            await connection.begin()
            if role is not None:
                await connection.execute(text(f"SET LOCAL ROLE {role}"))
            with pytest.raises(DBAPIError) as raised:
                await connection.execute(text(statement))
            assert _DENIED in str(raised.value), (role, raised.value)


async def test_the_runtime_login_cannot_become_the_owner(
    runtime_engine: AsyncEngine, owner_engine: AsyncEngine
) -> None:
    """``SET ROLE`` reaches the two application roles and stops there.

    ``RESET ROLE`` is in the finding for a reason: it is how the old arrangement
    was undone. Here it returns to a login that holds nothing, and the owner is
    not a role this connection may assume at all.
    """
    async with owner_engine.connect() as connection:
        owner = (await connection.execute(text("SELECT current_user"))).scalar_one()

    async with runtime_engine.connect() as connection:
        await connection.begin()
        with pytest.raises(DBAPIError, match="permission denied to set role"):
            await connection.execute(text(f'SET LOCAL ROLE "{owner}"'))


async def test_the_guards_still_tell_the_application_and_the_engine_apart(
    runtime_engine: AsyncEngine,
) -> None:
    """``pg_has_role(current_user, …, 'USAGE')`` — the exact expression the guards use.

    ``trade_proposals_the_app_only_files_requests`` (§19.4/§21.2) fires on
    ``pg_has_role(app) AND NOT pg_has_role(worker)`` and
    ``portfolios_are_born_audited`` (§20.2) on the mirror image. This table is
    what makes both of them keep working under the new login — and the first row
    is what an inheriting login would have turned into ``(True, True)``, firing
    neither guard and being read by the schema as the operator.
    """
    probe = text(
        "SELECT pg_has_role(current_user, 'hunter_app', 'USAGE'), "
        "pg_has_role(current_user, 'hunter_worker', 'USAGE')"
    )
    expected = {None: (False, False), "hunter_app": (True, False), "hunter_worker": (False, True)}

    for role, wanted in expected.items():
        async with runtime_engine.connect() as connection:
            await connection.begin()
            if role is not None:
                await connection.execute(text(f"SET LOCAL ROLE {role}"))
            assert tuple((await connection.execute(probe)).one()) == wanted, role
