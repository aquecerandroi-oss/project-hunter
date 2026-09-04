"""RFC 9457 problem+json: 404, 422 and unexpected-exception (500) responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    import httpx
    from fastapi import FastAPI

pytestmark = pytest.mark.unit

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance"}


def _assert_problem_json(response: httpx.Response, expected_status: int) -> dict[str, Any]:
    assert response.status_code == expected_status
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = response.json()
    assert PROBLEM_KEYS.issubset(body.keys())
    assert body["status"] == expected_status
    return body


async def test_404_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/this-route-does-not-exist")

    body = _assert_problem_json(response, 404)
    assert body["title"] == "Not Found"
    assert body["type"] == "https://hunter.dev/problems/not-found"


class _Payload(BaseModel):
    name: str


async def test_422_is_problem_json_with_field_errors(
    app: FastAPI,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    def _validate(payload: _Payload) -> dict[str, str]:
        return {"name": payload.name}

    app.post("/__test__/validate")(_validate)

    async with client_factory(app) as test_client:
        response = await test_client.post("/__test__/validate", json={})

    body = _assert_problem_json(response, 422)
    assert "errors" in body
    assert body["errors"][0]["loc"] == ["body", "name"]


async def test_500_hides_internals_and_includes_request_id(
    app: FastAPI,
    client_factory: Callable[[FastAPI], AbstractAsyncContextManager[httpx.AsyncClient]],
) -> None:
    def _boom() -> None:
        raise RuntimeError("internal secret: password=hunter2")

    app.get("/__test__/boom")(_boom)

    async with client_factory(app) as test_client:
        response = await test_client.get("/__test__/boom")

    body = _assert_problem_json(response, 500)
    dumped = str(body)
    assert "password" not in dumped
    assert "hunter2" not in dumped
    assert "RuntimeError" not in dumped
    assert "request_id" in body
    assert response.headers["X-Request-ID"] == body["request_id"]
