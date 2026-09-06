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
from typing import TYPE_CHECKING, cast

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from hunter_api import __version__, analytics
from hunter_api.auth.clerk import ClerkAuthProvider
from hunter_api.auth.clerk_api import create_profile_source
from hunter_api.auth.principal import PrincipalResolver
from hunter_api.errors import ProblemDetailsMiddleware, register_error_handlers
from hunter_api.health import router as health_router
from hunter_api.middleware.body_size import BodySizeLimitMiddleware
from hunter_api.middleware.metrics_auth import MetricsAuthMiddleware
from hunter_api.middleware.rate_limit import RateLimitMiddleware
from hunter_api.middleware.request_id import RequestIdMiddleware
from hunter_api.middleware.security_headers import SecurityHeadersMiddleware
from hunter_api.middleware.tenant_context import TenantContextMiddleware
from hunter_api.realtime.endpoint import RealtimeHub
from hunter_api.realtime.endpoint import router as realtime_router
from hunter_api.realtime.redis_bridge import RedisClientLike
from hunter_api.routers import anomalies as anomalies_router
from hunter_api.routers import audit as audit_router
from hunter_api.routers import invitations as invitations_router
from hunter_api.routers import lab as lab_router
from hunter_api.routers import markets as markets_router
from hunter_api.routers import me as me_router
from hunter_api.routers import members as members_router
from hunter_api.routers import opportunities as opportunities_router
from hunter_api.routers import organizations as organizations_router
from hunter_api.routers import radar as radar_router
from hunter_api.routers import regime as regime_router
from hunter_api.routers import system as system_router
from hunter_api.routers import webhooks as webhooks_router
from hunter_api.routers import workspaces as workspaces_router
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
    {"name": "lab", "description": "Shadow Lab: hypothetical, no-capital strategy research."},
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

        # Built once per process, not per request: the auth provider owns the
        # JWKS cache (a per-request provider would re-fetch Clerk's keys on
        # every call) and the realtime hub owns the single Redis pub/sub
        # connection every WebSocket fans out from. A test overrides either by
        # assigning to app.state after create_app.
        if not hasattr(app.state, "auth_provider"):
            app.state.auth_provider = ClerkAuthProvider(settings)
        if not hasattr(app.state, "principal_resolver"):
            app.state.principal_resolver = PrincipalResolver(
                session_factory, create_profile_source(settings)
            )
        # cast: ``RedisClientLike`` names the one method the bridge uses
        # (``pubsub()``); redis-py's own annotations for it are looser than the
        # protocol, and the alternative — typing the bridge against the whole
        # ``Redis`` surface — would make it untestable with a fake.
        realtime = RealtimeHub(cast("RedisClientLike", redis_client))
        app.state.realtime = realtime

        logger.info("api_startup", environment=settings.hunter_env)
        try:
            yield
        finally:
            await realtime.close()
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
    #
    # TenantContext is added *after* RateLimit, i.e. it wraps it. It has to:
    # the limiter reads its key off request.state before the route runs, and
    # TenantContext is what puts the Clerk webhook's per-delivery key there
    # (see its module docstring). In the other order the limiter would read
    # state that had not been written yet.
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(TenantContextMiddleware)
    # outside the limiter: a body oversized on its header alone is refused
    # without spending a Redis round trip or reading a byte of it, and the
    # streaming cap has to wrap `receive` before anything downstream reads it
    app.add_middleware(BodySizeLimitMiddleware, settings=settings)
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
    app.include_router(me_router.router)
    app.include_router(organizations_router.router)
    app.include_router(members_router.router)
    app.include_router(invitations_router.router)
    app.include_router(invitations_router.accept_router)
    app.include_router(workspaces_router.router)
    app.include_router(audit_router.router)
    app.include_router(markets_router.router)
    app.include_router(radar_router.router)
    app.include_router(opportunities_router.router)
    app.include_router(anomalies_router.router)
    app.include_router(regime_router.router)
    app.include_router(lab_router.router)
    app.include_router(system_router.router)
    app.include_router(webhooks_router.router)
    app.include_router(realtime_router)
    app.mount("/metrics", metrics_asgi_app())

    return app
