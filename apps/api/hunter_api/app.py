"""The FastAPI application factory.

Wires logging/Sentry, the engine/session-factory/Redis client (stored on
``app.state`` and disposed on shutdown), every middleware, error handlers,
and the routes that exist so far (``system``). OpenAPI tags are declared for
the whole product up front (ARCHITECTURE.md §7's router list) even though
only ``system`` has routes today — tags are metadata about where routers
*will* live, not a claim that they exist.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from hunter_api import __version__, analytics
from hunter_api.errors import ProblemDetailsMiddleware, register_error_handlers
from hunter_api.health import router as health_router
from hunter_api.middleware.metrics_auth import MetricsAuthMiddleware
from hunter_api.middleware.rate_limit import RateLimitMiddleware
from hunter_api.middleware.request_id import RequestIdMiddleware
from hunter_api.middleware.security_headers import SecurityHeadersMiddleware
from hunter_api.middleware.tenant_context import TenantContextMiddleware
from hunter_api.realtime.endpoint import router as realtime_router
from hunter_core.db.session import create_engine, create_session_factory
from hunter_core.logging import configure_logging, get_logger
from hunter_core.observability import init_sentry, metrics_asgi_app
from hunter_core.redis import create_redis

if TYPE_CHECKING:
    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)

OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "auth", "description": "Session and current-user identity (Clerk-backed)."},
    {"name": "organizations", "description": "Organizations, plans and org-level settings."},
    {"name": "workspaces", "description": "Workspaces within an organization."},
    {"name": "members", "description": "Membership, roles and invitations."},
    {"name": "markets", "description": "Exchanges, markets and market data."},
    {"name": "radar", "description": "The cross-market opportunity radar."},
    {"name": "opportunities", "description": "Scored trading opportunities."},
    {"name": "portfolios", "description": "Paper/shadow/live portfolios."},
    {"name": "trades", "description": "Orders, fills, positions and trades."},
    {"name": "agents", "description": "Trading agents (strategies) and their signals."},
    {"name": "risk", "description": "Risk profiles, risk events and the kill switch."},
    {"name": "analytics", "description": "Performance statistics and signal outcomes."},
    {"name": "system", "description": "Health, readiness, metrics and system info."},
    {"name": "audit", "description": "The append-only audit log."},
]

_ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
_ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-Request-ID", "Idempotency-Key"]


def create_app(settings: ApiSettings) -> FastAPI:
    """Build the ``api`` FastAPI application for ``settings``."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        configure_logging(settings, "api")
        init_sentry(settings, "api")
        analytics.configure(settings)

        if settings.hunter_env in ("staging", "production") and (
            settings.metrics_token is None or not settings.metrics_token.get_secret_value()
        ):
            logger.warning("metrics_token_unset", environment=settings.hunter_env)

        engine = create_engine(settings)
        session_factory = create_session_factory(engine)
        redis_client = create_redis(settings)

        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.redis = redis_client

        logger.info("api_startup", environment=settings.hunter_env)
        try:
            yield
        finally:
            await engine.dispose()
            await redis_client.aclose()
            logger.info("api_shutdown")

    app = FastAPI(
        title="PROJECT HUNTER API",
        version=__version__,
        openapi_tags=OPENAPI_TAGS,
        servers=[{"url": settings.api_url}],
        docs_url="/docs" if settings.openapi_enabled else None,
        redoc_url="/redoc" if settings.openapi_enabled else None,
        openapi_url="/openapi.json" if settings.openapi_enabled else None,
        lifespan=lifespan,
    )

    register_error_handlers(app)

    # Added innermost-first: the LAST middleware added is the outermost layer
    # (Starlette prepends on add_middleware), so this list reads
    # inner -> outer. RequestId must be outermost so it can stamp every
    # response, including ones ProblemDetailsMiddleware builds from an
    # unhandled exception; CORS must wrap ProblemDetails/RateLimit/Tenant so
    # preflight and error responses alike get CORS headers.
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(MetricsAuthMiddleware, settings=settings)
    app.add_middleware(ProblemDetailsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=_ALLOWED_METHODS,
        allow_headers=_ALLOWED_HEADERS,
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health_router)
    app.include_router(realtime_router)
    app.mount("/metrics", metrics_asgi_app())

    return app
