"""Integration test for WorkerRuntime's /ready against real Postgres + Redis.

Drives the Starlette app directly through ``httpx.ASGITransport`` — no real
uvicorn server needed, per the M0 T03 brief.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from hunter_core.redis import create_redis
from hunter_core.runtime import WorkerRuntime
from hunter_core.settings import Settings

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

pytestmark = pytest.mark.integration


async def test_ready_returns_200_with_real_postgres_and_redis(
    db_engine: AsyncEngine, redis_client: redis_asyncio.Redis
) -> None:
    runtime = WorkerRuntime(
        "scanner", Settings(), instance="it-1", engine=db_engine, redis_client=redis_client
    )
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"database": True, "redis": True}


async def test_ready_returns_503_when_redis_points_to_a_closed_port(db_engine: AsyncEngine) -> None:
    dead_redis = create_redis(Settings(redis_url=SecretStr("redis://localhost:1/0")))
    runtime = WorkerRuntime(
        "scanner", Settings(), instance="it-2", engine=db_engine, redis_client=dead_redis
    )
    transport = httpx.ASGITransport(app=runtime.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["database"] is True
    assert body["redis"] is False

    await dead_redis.aclose()
