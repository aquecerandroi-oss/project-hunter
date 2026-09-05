"""Shared testcontainers plumbing for the M1 market pipeline suite (T1.7).

Mirrors the pattern already used three times in this repo (``packages/core/
tests/conftest.py``, ``apps/api/tests/conftest.py``,
``services/market-worker/tests/conftest.py``): a session-scoped Postgres +
Redis container pair, migrated with Alembic, with ``hunter_app``/
``hunter_worker`` roles created so ``role_session(..., db_role="hunter_worker")``
(what every market-worker function under test uses) works exactly as it does
in production.

This suite deliberately owns its *own* database inside the shared container
(``hunter_pipeline_it``) rather than importing another package's ``tests``
conftest across the workspace-member boundary -- the same reasoning
``apps/api/tests/integration/conftest.py`` gives for not importing
``packages/core``'s.

Two "sides" share one physical Postgres/Redis: the market-worker functions
under test write through ``hunter_core.settings.Settings`` (``hunter_worker``
role), and the real FastAPI app reads back through ``hunter_api.settings
.ApiSettings`` (``hunter_app`` role) -- exactly the boundary the real system
has, just both pointed at the same containers instead of separate deployed
processes.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_api.app import create_app
from hunter_api.auth.clerk import StaticKeyAuthProvider
from hunter_api.auth.clerk_api import StaticProfileSource
from hunter_api.auth.principal import PrincipalResolver
from hunter_api.settings import ApiSettings
from hunter_core.db.session import create_engine, create_session_factory
from hunter_core.redis import create_redis
from hunter_core.settings import Settings

if TYPE_CHECKING:
    import httpx
    import redis.asyncio as redis_asyncio
    from cryptography.hazmat.primitives.asymmetric import rsa
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"
PIPELINE_DB = "hunter_pipeline_it"
WEB_ORIGIN = "http://web.test"


def _load_module(path: Path, name: str) -> ModuleType:
    """Load a module by file path, exactly like ``apps/api/tests/integration
    /conftest.py``'s ``load_script`` -- avoids importing another workspace
    member's ``tests`` package by dotted path (``services/market-worker``'s
    directory name is not a valid Python identifier anyway).
    """
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_jwt_keys = _load_module(
    REPO_ROOT / "apps" / "api" / "tests" / "unit" / "jwt_keys.py", "hunter_pipeline_it_jwt_keys"
)
FAKE_ISSUER: str = _jwt_keys.FAKE_ISSUER
generate_keypair = _jwt_keys.generate_keypair
jwks_for = _jwt_keys.jwks_for
sign = _jwt_keys.sign


def _docker_reachable() -> bool:
    try:
        import docker

        docker.from_env().ping()  # type: ignore[reportUnknownMemberType]
    except Exception as exc:
        from hunter_core.logging import get_logger

        get_logger(__name__).warning("docker_unreachable", error=str(exc))
        return False
    return True


@pytest.fixture(scope="session")
def docker_available() -> bool:
    return _docker_reachable()


async def _create_app_roles(url: str, login_role: str) -> None:
    engine = create_async_engine(
        url, isolation_level="AUTOCOMMIT", connect_args={"statement_cache_size": 0}
    )
    try:
        async with engine.connect() as connection:
            for role, extra_attributes in (("hunter_app", ""), ("hunter_worker", " BYPASSRLS")):
                exists = await connection.scalar(
                    text("SELECT 1 FROM pg_roles WHERE rolname = :name"), {"name": role}
                )
                if not exists:
                    await connection.execute(text(f"CREATE ROLE {role} NOLOGIN{extra_attributes}"))
            await connection.execute(text(f'GRANT hunter_app, hunter_worker TO "{login_role}"'))
            await connection.execute(
                text("GRANT ALL ON SCHEMA public TO hunter_app, hunter_worker")
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def postgres_container(docker_available: bool) -> Iterator[PostgresContainer]:
    if not docker_available:
        pytest.skip("Docker is not reachable; skipping Postgres-backed integration tests")
    from testcontainers.community.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        asyncio.run(_create_app_roles(container.get_connection_url(), container.username))
        yield container


@pytest.fixture(scope="session")
def redis_container(docker_available: bool) -> Iterator[RedisContainer]:
    if not docker_available:
        pytest.skip("Docker is not reachable; skipping Redis-backed integration tests")
    from testcontainers.community.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as container:
        yield container


def _alembic_config(url: str) -> Config:
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    os.environ["DATABASE_URL_MIGRATIONS"] = url
    config = Config(str(MIGRATIONS_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return config


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
def pipeline_db_url(postgres_container: PostgresContainer) -> Iterator[str]:
    """A database in the shared container, migrated to ``head``.

    Also runs ``infra/scripts/create_partitions.py``-equivalent lookahead via
    the migrations themselves (they create partitions through the current
    month); ``services/market-worker/hunter_market_worker/partitions.py``'s
    ``assert_writable_partitions`` needs a partition for *now*, which the
    initial migration already provides for any reasonably current test run.
    """
    url = asyncio.run(_create_database(postgres_container.get_connection_url(), PIPELINE_DB))
    command.upgrade(_alembic_config(url), "head")
    yield url


@pytest.fixture(scope="session")
def pipeline_redis_url(redis_container: RedisContainer) -> str:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return f"redis://{host}:{port}/0"


@pytest.fixture
def worker_settings(pipeline_db_url: str, pipeline_redis_url: str) -> Settings:
    """``hunter_core.settings.Settings`` -- the shape every market-worker
    function under test (``refresh_universe``, ``handle_event``,
    ``flush_batch``, ``check_gaps``, ...) actually receives in production.
    """
    return Settings(
        database_url=SecretStr(pipeline_db_url),
        redis_url=SecretStr(pipeline_redis_url),
        market_stale_after_s=10,
    )


@pytest_asyncio.fixture
async def worker_engine(worker_settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(worker_settings)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def worker_session_factory(
    worker_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return create_session_factory(worker_engine)


@pytest_asyncio.fixture
async def worker_redis(worker_settings: Settings) -> AsyncIterator[redis_asyncio.Redis]:
    client = create_redis(worker_settings)
    try:
        await client.flushdb()  # type: ignore[misc]
        yield client
    finally:
        await client.aclose()


@pytest.fixture
def api_settings(pipeline_db_url: str, pipeline_redis_url: str) -> ApiSettings:
    return ApiSettings(
        hunter_env="test",
        database_url=SecretStr(pipeline_db_url),
        database_url_migrations=SecretStr(pipeline_db_url),
        redis_url=SecretStr(pipeline_redis_url),
        web_origin=WEB_ORIGIN,
        cors_allowed_origins=[WEB_ORIGIN],
        clerk_issuer=FAKE_ISSUER,
        clerk_webhook_secret=SecretStr("whsec_" + "0" * 32),
        rate_limit_per_minute=100000,
        market_stale_after_s=10,
    )


@pytest.fixture(scope="session")
def signing_key() -> rsa.RSAPrivateKey:
    return generate_keypair()


@pytest.fixture
def profiles() -> StaticProfileSource:
    return StaticProfileSource()


@pytest.fixture
def pipeline_app(
    api_settings: ApiSettings, signing_key: rsa.RSAPrivateKey, profiles: StaticProfileSource
) -> FastAPI:
    application = create_app(api_settings)
    application.state.auth_provider = StaticKeyAuthProvider(
        jwks_for(signing_key), issuer=FAKE_ISSUER, allowed_azp=api_settings.cors_allowed_origins
    )
    application.state.profiles = profiles
    return application


@pytest_asyncio.fixture
async def pipeline_client(pipeline_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    import httpx

    async with pipeline_app.router.lifespan_context(pipeline_app):
        pipeline_app.state.principal_resolver = PrincipalResolver(
            pipeline_app.state.session_factory, pipeline_app.state.profiles
        )
        transport = httpx.ASGITransport(app=pipeline_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


def auth_headers(
    signing_key: rsa.RSAPrivateKey, subject: str = "user_FAKE_pipeline"
) -> dict[str, str]:
    """A signed, verifiable FAKE token -- not a Clerk credential (see
    ``jwt_keys.py``). ``azp`` defaults to this suite's own allowed origin.
    """
    token = sign(signing_key, subject=subject, azp=WEB_ORIGIN)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def authed_actor(
    pipeline_client: httpx.AsyncClient,
    signing_key: rsa.RSAPrivateKey,
    profiles: StaticProfileSource,
) -> dict[str, str]:
    """Registers a FAKE profile and returns auth headers for a just-in-time
    provisioned user -- markets/system routes are global (no membership
    needed), so this alone is enough to call them."""
    from hunter_api.auth.clerk_api import UserProfile

    subject = f"user_FAKE_{uuid.uuid4().hex[:8]}"
    profiles.add(UserProfile(external_auth_id=subject, email=f"{subject}@example.test"))
    return auth_headers(signing_key, subject)
