"""Unit tests for hunter_core.db.session (no real Postgres — fakes only)."""

import uuid
from typing import Any

import pytest

from hunter_core.db.session import (
    DB_ROLES,
    bootstrap_session,
    check_database,
    create_engine,
    role_session,
    tenant_session,
    user_session,
)
from hunter_core.settings import Settings

pytestmark = pytest.mark.unit


class _FakeResult:
    def __init__(self, calls: list[tuple[Any, Any]]) -> None:
        self._calls = calls


class _FakeSession:
    def __init__(self, calls: list[tuple[Any, Any]]) -> None:
        self._calls = calls

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    def begin(self) -> "_FakeSession":
        return self

    async def execute(self, statement: Any, params: Any = None) -> _FakeResult:
        self._calls.append((statement, params))
        return _FakeResult(self._calls)


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    def __call__(self) -> _FakeSession:
        return _FakeSession(self.calls)


class _FailingConnection:
    async def __aenter__(self) -> "_FailingConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def execute(self, statement: Any) -> None:
        raise ConnectionRefusedError("no postgres here")


class _FailingEngine:
    def connect(self) -> _FailingConnection:
        return _FailingConnection()


def _sql(factory: _FakeSessionFactory) -> list[str]:
    return [str(statement) for statement, _ in factory.calls]


def test_create_engine_raises_when_database_url_missing() -> None:
    settings = Settings(database_url=None)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        create_engine(settings)


async def test_tenant_session_downgrades_role_then_sets_current_org() -> None:
    factory = _FakeSessionFactory()
    org_id = uuid.uuid4()

    async with tenant_session(factory, org_id):  # type: ignore[arg-type]
        pass

    assert len(factory.calls) == 2
    role_statement, role_params = factory.calls[0]
    # the role downgrade comes first, so every later statement in the
    # transaction — including set_config — runs as hunter_app
    assert str(role_statement) == "SET LOCAL ROLE hunter_app"
    assert role_params is None

    org_statement, org_params = factory.calls[1]
    assert "set_config('app.current_org'" in str(org_statement)
    assert org_params == {"value": str(org_id)}
    # the org id must be a bound parameter, never interpolated into the SQL text
    assert str(org_id) not in str(org_statement)


async def test_tenant_session_sets_current_user_when_given() -> None:
    factory = _FakeSessionFactory()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async with tenant_session(factory, org_id, user_id):  # type: ignore[arg-type]
        pass

    statements = _sql(factory)
    assert len(statements) == 3
    assert "app.current_org" in statements[1]
    assert "app.current_user" in statements[2]
    assert factory.calls[2][1] == {"value": str(user_id)}


async def test_user_session_sets_only_current_user() -> None:
    factory = _FakeSessionFactory()
    user_id = uuid.uuid4()

    async with user_session(factory, user_id):  # type: ignore[arg-type]
        pass

    statements = _sql(factory)
    assert statements == [
        "SET LOCAL ROLE hunter_app",
        "SELECT set_config('app.current_user', :value, true)",
    ]


async def test_bootstrap_session_sets_both_ids_before_they_exist() -> None:
    factory = _FakeSessionFactory()
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async with bootstrap_session(factory, org_id=org_id, user_id=user_id):  # type: ignore[arg-type]
        pass

    statements = _sql(factory)
    assert "app.current_org" in statements[1]
    assert "app.current_user" in statements[2]


async def test_role_session_accepts_the_worker_role() -> None:
    factory = _FakeSessionFactory()

    async with role_session(factory, db_role="hunter_worker"):  # type: ignore[arg-type]
        pass

    assert _sql(factory) == ["SET LOCAL ROLE hunter_worker"]


@pytest.mark.parametrize(
    "db_role",
    ["postgres", "hunter_app; DROP TABLE users", "", "HUNTER_APP", "superuser"],
)
async def test_role_session_rejects_any_role_outside_the_allowlist(db_role: str) -> None:
    factory = _FakeSessionFactory()

    with pytest.raises(ValueError, match="unknown database role"):
        async with role_session(factory, db_role=db_role):  # type: ignore[arg-type]
            pass

    assert factory.calls == []


def test_db_roles_allowlist_is_exactly_the_two_application_roles() -> None:
    assert DB_ROLES == frozenset({"hunter_app", "hunter_worker"})


async def test_check_database_returns_false_on_connection_error() -> None:
    assert await check_database(_FailingEngine()) is False  # type: ignore[arg-type]
