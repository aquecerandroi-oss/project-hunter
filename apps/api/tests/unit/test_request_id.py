"""``X-Request-ID`` is echoed back when provided, and generated otherwise."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx

pytestmark = pytest.mark.unit


async def test_echoes_the_provided_request_id(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "given-id-123"})

    assert response.headers["X-Request-ID"] == "given-id-123"


async def test_generates_a_request_id_when_absent(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")

    request_id = response.headers.get("X-Request-ID")
    assert request_id
    assert len(request_id) > 0
