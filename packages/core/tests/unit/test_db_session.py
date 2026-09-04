"""Unit tests for hunter_core.db.session (no real Postgres — fakes only)."""

import uuid
from typing import Any

import pytest

from hunter_core.db.session import check_database, create_engine, tenant_session
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


def test_create_engine_raises_when_database_url_missing() -> None:
    settings = Settings(database_url=None)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        create_engine(settings)


async def test_tenant_session_sets_current_org_parameterized() -> None:
    factory = _FakeSessionFactory()
    org_id = uuid.uuid4()

    async with tenant_session(factory, org_id):  # type: ignore[arg-type]
        pass

    assert len(factory.calls) == 1
    statement, params = factory.calls[0]
    assert "set_config('app.current_org'" in str(statement)
    assert params == {"org_id": str(org_id)}
    # the org id must be a bound parameter, never interpolated into the SQL text
    assert str(org_id) not in str(statement)


async def test_check_database_returns_false_on_connection_error() -> None:
    assert await check_database(_FailingEngine()) is False  # type: ignore[arg-type]
