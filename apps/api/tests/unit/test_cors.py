"""CORS: exact allowlist, no wildcard — SECURITY.md §5."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx

pytestmark = pytest.mark.unit

ALLOWED_ORIGIN = "http://localhost:3000"
DISALLOWED_ORIGIN = "http://evil.example.com"


async def test_preflight_from_an_allowed_origin_succeeds(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/api/v1/system/info",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


async def test_disallowed_origin_gets_no_cors_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/system/info", headers={"Origin": DISALLOWED_ORIGIN})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


async def test_preflight_from_a_disallowed_origin_gets_no_cors_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.options(
        "/api/v1/system/info",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
