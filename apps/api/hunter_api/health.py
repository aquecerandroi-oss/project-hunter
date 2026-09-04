"""``/health``, ``/ready`` and the public ``/api/v1/system/info``.

``/metrics`` is not here: it is a separate ASGI app (``metrics_asgi_app()``)
mounted directly in ``app.py``, not a router endpoint.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from hunter_api import __version__
from hunter_core.db.session import check_database
from hunter_core.redis import check_redis

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from hunter_api.settings import ApiSettings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up. Never touches Postgres/Redis."""
    return {"status": "ok", "role": "api", "version": __version__}


async def _check_with_timeout(
    coro: Coroutine[Any, Any, bool], timeout_s: float
) -> tuple[bool, str | None]:
    """Run a readiness check, bounding it to ``timeout_s``.

    A dependency that never answers must not hang ``/ready`` forever — a
    slow/wedged Postgres or Redis should surface as "not ready" quickly
    enough for an orchestrator's own liveness/readiness probe timeout to
    still work.
    """
    try:
        ok = await asyncio.wait_for(coro, timeout=timeout_s)
    except TimeoutError:
        return False, "timeout"
    return ok, None


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness: 200 only when both Postgres and Redis answer within
    ``ApiSettings.ready_check_timeout_s``, else 503 with per-dependency
    detail (``"timeout"`` when that dependency didn't answer in time).
    """
    settings: ApiSettings = request.app.state.settings
    timeout_s = settings.ready_check_timeout_s
    db_ok, db_detail = await _check_with_timeout(
        check_database(request.app.state.engine), timeout_s
    )
    redis_ok, redis_detail = await _check_with_timeout(
        check_redis(request.app.state.redis), timeout_s
    )
    body: dict[str, Any] = {"database": db_ok, "redis": redis_ok}
    if db_detail is not None:
        body["database_detail"] = db_detail
    if redis_detail is not None:
        body["redis_detail"] = redis_detail
    return JSONResponse(body, status_code=200 if db_ok and redis_ok else 503)


@router.get("/api/v1/system/info")
async def system_info(request: Request) -> dict[str, Any]:
    """Public, unauthenticated system metadata. No secret ever appears here."""
    settings: ApiSettings = request.app.state.settings
    return {
        "environment": settings.hunter_env,
        "version": __version__,
        "git_sha": os.environ.get("HUNTER_RELEASE", "unknown"),
        "features": {
            "enable_live_trading": settings.enable_live_trading,
            "enable_social_intelligence": settings.enable_social_intelligence,
            "enable_onchain": settings.enable_onchain,
            "enable_stripe": settings.enable_stripe,
            "enable_llm_analysis": settings.enable_llm_analysis,
            "enable_arena": settings.enable_arena,
            "enable_backtests": settings.enable_backtests,
        },
    }
