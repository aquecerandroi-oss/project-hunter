"""Smoke test for ``tests/integration/conftest.py``'s plumbing itself.

Not one of T1.7's seven proof items -- exists only so a broken fixture fails
fast, close to the fixture, instead of thousands of lines into the real
pipeline tests with a confusing traceback.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import httpx

pytestmark = pytest.mark.integration


async def test_pipeline_client_reaches_the_real_app(
    pipeline_client: httpx.AsyncClient, authed_actor: dict[str, str]
) -> None:
    """Not an isolation assertion: this Postgres database is shared and
    accumulates rows across the whole suite (see ``test_market_pipeline.py``'s
    isolation note), so this only checks the fixture wiring reaches a real,
    schema-shaped response -- never an empty-database assumption.
    """
    response = await pipeline_client.get("/api/v1/markets", headers=authed_actor)
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["items"], list)
    assert body["summary"]["markets_total"] >= len(body["items"])  # items is one page of the total
