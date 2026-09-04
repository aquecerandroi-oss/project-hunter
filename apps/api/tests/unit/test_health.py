"""``/health`` and ``/api/v1/system/info``. ``/ready`` needs real Postgres and
Redis, so its 200/503 cases live in ``tests/integration/test_ready.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx

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
