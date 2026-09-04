"""``/metrics`` gating: open in dev/test with no token configured, a bearer
token required when ``METRICS_TOKEN`` is set, and hidden entirely (404) in
staging/production when no token is configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from hunter_api.app import create_app

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    import httpx
    from fastapi import FastAPI

    from hunter_api.settings import ApiSettings

pytestmark = pytest.mark.unit


async def test_metrics_is_open_in_test_env_with_no_token_configured(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/metrics/")

    assert response.status_code == 200


async def test_metrics_requires_bearer_token_when_configured(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    guarded = api_settings.model_copy(update={"metrics_token": SecretStr("s3cr3t")})
    app = create_app(guarded)

    async with client_factory(app) as test_client:
        missing = await test_client.get("/metrics/")
        wrong = await test_client.get("/metrics/", headers={"Authorization": "Bearer wrong"})
        correct = await test_client.get("/metrics/", headers={"Authorization": "Bearer s3cr3t"})

    assert missing.status_code == 401
    assert missing.headers["content-type"].startswith("application/problem+json")
    assert wrong.status_code == 401
    assert correct.status_code == 200


async def test_metrics_is_hidden_in_production_with_no_token_configured(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    prod = api_settings.model_copy(
        update={
            "hunter_env": "production",
            "web_origin": "https://hunter.example.com",
            "api_url": "https://api.hunter.example.com",
            "next_public_api_url": "https://api.hunter.example.com",
            "next_public_ws_url": "wss://api.hunter.example.com/ws",
        }
    )
    app = create_app(prod)

    async with client_factory(app) as test_client:
        response = await test_client.get("/metrics/")

    assert response.status_code == 404


async def test_metrics_is_hidden_in_staging_with_no_token_configured(
    api_settings: ApiSettings,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    staging = api_settings.model_copy(
        update={
            "hunter_env": "staging",
            "web_origin": "https://staging.hunter.example.com",
            "api_url": "https://api.staging.hunter.example.com",
            "next_public_api_url": "https://api.staging.hunter.example.com",
            "next_public_ws_url": "wss://api.staging.hunter.example.com/ws",
        }
    )
    app = create_app(staging)

    async with client_factory(app) as test_client:
        response = await test_client.get("/metrics/")

    assert response.status_code == 404


async def test_metrics_token_unset_in_production_logs_a_startup_warning(
    api_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hunter_api import app as app_module

    warnings: list[str] = []

    def _record_warning(event: str, **_kwargs: object) -> None:
        warnings.append(event)

    monkeypatch.setattr(app_module.logger, "warning", _record_warning)
    prod = api_settings.model_copy(
        update={
            "hunter_env": "production",
            "web_origin": "https://hunter.example.com",
            "api_url": "https://api.hunter.example.com",
            "next_public_api_url": "https://api.hunter.example.com",
            "next_public_ws_url": "wss://api.hunter.example.com/ws",
        }
    )
    app = create_app(prod)

    async with app.router.lifespan_context(app):
        pass

    assert "metrics_token_unset" in warnings
