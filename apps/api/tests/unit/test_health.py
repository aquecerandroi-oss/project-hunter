"""``/health`` and ``/api/v1/system/info``. ``/ready`` needs real Postgres and
Redis, so its 200/503 cases live in ``tests/integration/test_ready.py``. The
timeout behavior of ``/ready`` is a unit concern (it never needs a real
database to prove a slow dependency check gets cut off), so it lives here.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import pytest

from hunter_api import health
from hunter_api.app import create_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    import httpx
    from fastapi import FastAPI

    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.unit


async def test_health_returns_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["role"] == "api"
    assert "version" in body


async def test_system_info_is_public_and_has_no_secrets(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/info")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"environment", "version", "git_sha", "features"}
    assert body["environment"] == "test"
    assert body["git_sha"] == "unknown"
    assert isinstance(body["features"], dict)
    assert body["features"]["enable_live_trading"] is False

    dumped = str(body)
    assert "SecretStr" not in dumped
    assert "**********" not in dumped


async def test_ready_times_out_a_hanging_dependency_check(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fast_timeout_settings = api_settings.model_copy(update={"ready_check_timeout_s": 0.05})
    app = create_app(fast_timeout_settings)

    async def _never_returns(*_args: object, **_kwargs: object) -> bool:
        await asyncio.sleep(3600)
        return True

    monkeypatch.setattr(health, "check_database", _never_returns)

    started = time.monotonic()
    async with client_factory(app) as test_client:
        response = await test_client.get("/ready")
    elapsed = time.monotonic() - started

    assert elapsed < 2.0
    assert response.status_code == 503
    body = response.json()
    assert body["database"] is False
    assert body["database_detail"] == "timeout"
