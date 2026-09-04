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


async def test_rejects_an_inbound_request_id_with_disallowed_characters(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "abc<script>alert(1)"})

    request_id = response.headers.get("X-Request-ID")
    assert request_id != "abc<script>alert(1)"
    assert request_id


async def test_rejects_an_inbound_request_id_over_128_chars(client: httpx.AsyncClient) -> None:
    too_long = "a" * 129
    response = await client.get("/health", headers={"X-Request-ID": too_long})

    request_id = response.headers.get("X-Request-ID")
    assert request_id != too_long
    assert request_id


async def test_accepts_an_inbound_request_id_at_the_128_char_boundary(
    client: httpx.AsyncClient,
) -> None:
    exactly_128 = "a" * 128
    response = await client.get("/health", headers={"X-Request-ID": exactly_128})

    assert response.headers.get("X-Request-ID") == exactly_128
