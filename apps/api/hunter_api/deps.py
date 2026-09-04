"""FastAPI dependency providers.

Everything here reads from ``app.state``, populated once at startup by
``create_app``'s lifespan (``app.py``). T06 adds ``get_principal`` /
``require_role`` alongside these once auth exists.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_api.settings import ApiSettings


def get_settings(request: Request) -> ApiSettings:
    """The ``ApiSettings`` this process was started with."""
    settings: ApiSettings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """A plain (non-tenant) SQLAlchemy session for the lifetime of the request.

    Tenant-scoped sessions (``SET LOCAL app.current_org``) are a T06 concern,
    once a ``Principal``/``org_id`` exists to scope them to.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_redis(request: Request) -> redis_asyncio.Redis:
    """The process-wide Redis client."""
    client: redis_asyncio.Redis = request.app.state.redis
    return client


def get_request_id(request: Request) -> str:
    """The request id bound by ``RequestIdMiddleware`` (inbound header or minted)."""
    request_id: str = request.state.request_id
    return request_id
