"""``/health``, ``/ready`` and the public ``/api/v1/system/info``.

``/metrics`` is not here: it is a separate ASGI app (``metrics_asgi_app()``)
mounted directly in ``app.py``, not a router endpoint.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from hunter_api import __version__
from hunter_core.db.session import check_database
from hunter_core.redis import check_redis

if TYPE_CHECKING:
    from hunter_api.settings import ApiSettings

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: the process is up. Never touches Postgres/Redis."""
    return {"status": "ok", "role": "api", "version": __version__}


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    """Readiness: 200 only when both Postgres and Redis answer, else 503
    with per-dependency detail.
    """
    db_ok = await check_database(request.app.state.engine)
    redis_ok = await check_redis(request.app.state.redis)
    body = {"database": db_ok, "redis": redis_ok}
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
