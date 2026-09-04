"""A migrated, seeded database and a live app for the API integration suite.

Follows the pattern in ``packages/core/tests/integration/conftest.py`` — its own
database inside the session-scoped Postgres container, Alembic to ``head``, the
seed script loaded by path — but deliberately does **not** import it: the two
packages are separate uv workspace members, and a test importing across that
boundary would make ``apps/api``'s suite unrunnable on its own.

Authentication uses ``StaticKeyAuthProvider`` over an RSA keypair generated in
this process (``tests/unit/jwt_keys``). Tokens are therefore signed and
verified for real — signature, ``exp``, ``iss`` — so these tests exercise the
production dependency chain rather than a stub principal. There is no Clerk
credential anywhere in this suite.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

import httpx
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from hunter_api.app import create_app
from hunter_api.auth.clerk import StaticKeyAuthProvider
from hunter_api.auth.clerk_api import StaticProfileSource, UserProfile
from hunter_api.auth.principal import PrincipalResolver
from hunter_api.settings import ApiSettings

from ..unit.jwt_keys import FAKE_ISSUER, generate_keypair, jwks_for, sign

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
SCRIPTS_DIR = REPO_ROOT / "infra" / "scripts"
API_DB = "hunter_api_it"

FAKE_WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"FAKE-webhook-secret-000").decode()
"""A Svix-shaped secret generated for this suite. Not a Clerk credential; the
literal string "FAKE" is in it so a scanner never has to guess."""


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


def _load_script(name: str) -> ModuleType:
    """Load an ``infra/scripts`` module by path — they are operational scripts,
    not an installed package.
    """
    spec = importlib.util.spec_from_file_location(
        f"hunter_api_it_{name}", SCRIPTS_DIR / f"{name}.py"
    )
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"cannot load infra/scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _create_database(admin_url: str, name: str) -> str:
    engine = create_async_engine(
        admin_url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        await engine.dispose()
    return admin_url.rsplit("/", 1)[0] + "/" + name


@pytest.fixture(scope="session")
def api_database_url(postgres_container: PostgresContainer) -> Iterator[str]:
    """A migrated and seeded database, shared by the whole API suite.

    Sync on purpose: Alembic's ``env.py`` calls ``asyncio.run``, which cannot
    run inside an already-running loop.
    """
    url = asyncio.run(_create_database(postgres_container.get_connection_url(), API_DB))
    command.upgrade(_alembic_config(url), "head")
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    asyncio.run(_load_script("seed").seed())
    yield url


@pytest.fixture(scope="session")
def redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return generate_keypair()


@pytest.fixture
def profiles() -> StaticProfileSource:
    """What "Clerk" would answer for a just-in-time provisioned user.

    Empty by default; a test that wants JIT provisioning registers the profile
    it expects, and a test that does not gets a clean 503 instead of a silent
    network call.
    """
    return StaticProfileSource()


@pytest.fixture
def api_settings(api_database_url: str, redis_url: str) -> ApiSettings:
    return ApiSettings(
        hunter_env="test",
        database_url=SecretStr(api_database_url),
        database_url_migrations=SecretStr(api_database_url),
        redis_url=SecretStr(redis_url),
        web_origin="http://web.test",
        cors_allowed_origins=["http://web.test"],
        clerk_issuer=FAKE_ISSUER,
        clerk_webhook_secret=SecretStr(FAKE_WEBHOOK_SECRET),
        rate_limit_per_minute=100000,
    )


@pytest.fixture
def app(
    api_settings: ApiSettings, signing_key: rsa.RSAPrivateKey, profiles: StaticProfileSource
) -> FastAPI:
    """The real application, with only the identity provider swapped.

    ``create_app``'s lifespan builds the principal resolver from ``app.state``
    if one is not already there, so assigning here keeps every router, every
    dependency and every RLS session exactly as production has them.
    """
    application = create_app(api_settings)
    application.state.auth_provider = StaticKeyAuthProvider(
        jwks_for(signing_key), issuer=FAKE_ISSUER
    )
    application.state.profiles = profiles
    return application


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        # the resolver is built in the lifespan against the real Clerk source;
        # rebind it to the static profiles this test registered
        app.state.principal_resolver = PrincipalResolver(
            app.state.session_factory, app.state.profiles
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as test:
            yield test


@pytest_asyncio.fixture
async def session_factory(
    app: FastAPI, client: httpx.AsyncClient
) -> async_sessionmaker[AsyncSession]:
    """The app's own session factory — for assertions that read the database
    directly (audit rows, RLS probes) with the same engine the API uses.
    """
    factory: async_sessionmaker[AsyncSession] = app.state.session_factory
    return factory


def token_for(signing_key: rsa.RSAPrivateKey, subject: str) -> str:
    return sign(signing_key, subject=subject, azp=None)


def auth_header(signing_key: rsa.RSAPrivateKey, subject: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token_for(signing_key, subject)}"}


class Actor:
    """One signed-in person, with the header that authenticates them."""

    def __init__(self, signing_key: rsa.RSAPrivateKey, subject: str, email: str) -> None:
        self.subject = subject
        self.email = email
        self.headers = auth_header(signing_key, subject)
        self.org_id: uuid.UUID | None = None
        self.workspace_id: uuid.UUID | None = None
        self.user_id: uuid.UUID | None = None


@pytest_asyncio.fixture
async def make_actor(
    client: httpx.AsyncClient, signing_key: rsa.RSAPrivateKey, profiles: StaticProfileSource
) -> Any:
    """Factory: register a FAKE Clerk profile and return an authenticated actor.

    The user row itself is created by just-in-time provisioning on the actor's
    first request, which is the real sign-up path.
    """

    def _make(name: str) -> Actor:
        subject = f"user_FAKE_{name}"
        email = f"{name}@example.test"
        profiles.add(
            UserProfile(
                external_auth_id=subject, email=email, display_name=name.replace("-", " ").title()
            )
        )
        return Actor(signing_key, subject, email)

    return _make


async def create_org(client: httpx.AsyncClient, actor: Actor, name: str) -> Actor:
    """Sign ``actor`` up with a new organization and remember its ids."""
    response = await client.post("/api/v1/orgs", json={"name": name}, headers=actor.headers)
    assert response.status_code == 201, response.text
    body = response.json()
    actor.org_id = uuid.UUID(body["id"])
    actor.workspace_id = uuid.UUID(body["workspace_id"])
    me = await client.get("/api/v1/me", headers=actor.headers)
    actor.user_id = uuid.UUID(me.json()["user"]["id"])
    return actor
