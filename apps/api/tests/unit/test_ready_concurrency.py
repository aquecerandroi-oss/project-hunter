"""``/ready`` checks Postgres and Redis at the same time, not one after the other.

They are independent, so running them in sequence makes the worst case the
*sum* of the timeouts. With the default 3 s that is 6 s — past the readiness
probe deadline of most orchestrators, which turns "one dependency is slow" into
"kill the pod".
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

import pytest

from hunter_api import health

if TYPE_CHECKING:
    import httpx
    from fastapi import FastAPI

pytestmark = pytest.mark.unit

TIMEOUT_S = 0.4


async def _hang(*_args: Any, **_kwargs: Any) -> bool:
    await asyncio.sleep(3600)
    return True


async def test_both_checks_hang_and_ready_still_answers_in_about_one_timeout(
    app: FastAPI, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "check_database", _hang)
    monkeypatch.setattr(health, "check_redis", _hang)
    app.state.settings.ready_check_timeout_s = TIMEOUT_S

    started = time.monotonic()
    response = await client.get("/ready")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.json() == {
        "database": False,
        "redis": False,
        "database_detail": "timeout",
        "redis_detail": "timeout",
    }
    # concurrent: ~one timeout, not two. The upper bound is generous enough
    # for a loaded CI box and still far below the 2x that sequencing costs.
    assert elapsed < TIMEOUT_S * 1.8, f"took {elapsed:.2f}s, expected about {TIMEOUT_S}s"
