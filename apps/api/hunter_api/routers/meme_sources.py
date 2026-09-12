"""``GET /api/v1/orgs/{org_id}/meme/sources`` — the meme radar's sources (T4.2c),
read-only, VIEWER+ under the org session like ``routers/meme.py``.

Two witnesses, both named in the payload: the worker's heartbeat hash
``hb:meme:radar`` (the per-source blocks and the adendo's flat fields, written
by ``services/meme-worker``) and the newest row each source left in the
database. Redis being unavailable is a ``radar_status`` of its own, never an
empty list of healthy-looking sources.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Depends

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, get_redis
from hunter_api.repositories.meme_sources import MemeSourcesRepository
from hunter_api.routers.meme_lab import MEME_HEARTBEAT_KEY
from hunter_api.schemas.meme_sources import MemeSourcesOut
from hunter_api.services.meme_sources import build_meme_sources
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

__all__ = ["router"]

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/orgs/{org_id}/meme", tags=["meme"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]

STALLED_AFTER_S = 60
"""The worker writes its fields every 15 s; a minute without them is a stalled radar."""


async def _heartbeat(redis: redis_asyncio.Redis) -> tuple[dict[str, str] | None, str | None]:
    try:
        raw = cast("dict[bytes, bytes]", await redis.hgetall(MEME_HEARTBEAT_KEY))
    except redis_exceptions.RedisError as exc:
        logger.warning("meme_sources_heartbeat_unavailable", error_type=type(exc).__name__)
        return None, type(exc).__name__
    return {k.decode(errors="replace"): v.decode(errors="replace") for k, v in raw.items()}, None


@router.get(
    "/sources",
    response_model=MemeSourcesOut,
    summary="Every source of the meme radar: connected?, last observed_at, lag, errors, budget",
)
async def get_meme_sources(context: ViewerOrg, session: OrgSession, redis: Redis) -> MemeSourcesOut:
    heartbeat, error = await _heartbeat(redis)
    latest = await MemeSourcesRepository(session).latest_rows()
    return build_meme_sources(
        heartbeat,
        latest,
        as_of=utcnow(),
        heartbeat_key=MEME_HEARTBEAT_KEY,
        redis_error=error,
        stalled_after_s=STALLED_AFTER_S,
    )
