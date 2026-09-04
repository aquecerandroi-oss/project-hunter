"""Static security headers — SECURITY.md §5."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hunter_api.app import create_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    import httpx
    from fastapi import FastAPI

    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.unit


async def test_security_headers_present(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "Permissions-Policy" in response.headers


async def test_cache_control_no_store_on_api_paths(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/info")

    assert response.headers["Cache-Control"] == "no-store"


async def test_cache_control_absent_outside_api_paths(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    assert response.headers.get("Cache-Control") != "no-store"


async def test_hsts_present_when_not_development(client: httpx.AsyncClient) -> None:
    """The shared ``client`` fixture uses ``HUNTER_ENV=test``."""
    response = await client.get("/health")

    assert "Strict-Transport-Security" in response.headers


async def test_hsts_absent_in_development(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    dev_settings = api_settings.model_copy(update={"hunter_env": "development"})
    app = create_app(dev_settings)

    async with client_factory(app) as dev_client:
        response = await dev_client.get("/health")

    assert "Strict-Transport-Security" not in response.headers
