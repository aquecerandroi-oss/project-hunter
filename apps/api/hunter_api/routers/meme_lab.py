"""``GET /api/v1/orgs/{org_id}/meme/lab`` — the continuous paper Lab's scoreboard
(T4.6), read-only.

Nested under the organization like ``routers/meme.py`` (VIEWER+ under the org
session) although the ``0022_meme_lab`` tables carry no ``organization_id``:
the org segment gates *who* may look, the repository filters nothing.

Two sources, both named in the payload: the database (rule sets, bets, the
scoreboard view) and the meme-worker's own heartbeat hash ``hb:meme:radar``,
whose ``lab_*`` fields say when the loop last ticked — the contract's
§Semântica 5: a stopped loop must be visible, so Redis being unavailable is
reported as a source state, never as an empty scoreboard.

The operator's routes (approve/reject/manual/sell-now/cancel) are T4.7's
(``routers/meme_desk.py``); nothing here writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Depends, Query

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, get_redis
from hunter_api.repositories.meme_lab import MemeLabRepository
from hunter_api.schemas.meme_lab import MemeLabOut
from hunter_api.services.meme_lab import DEFAULT_DAYS_LIMIT, build_meme_lab
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

__all__ = ["MEME_HEARTBEAT_KEY", "router"]

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/orgs/{org_id}/meme", tags=["meme"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]

MEME_HEARTBEAT_KEY = keys.heartbeat("meme", "radar")
"""The collector is a singleton with a fixed instance name (``services/meme-worker``
``config.INSTANCE``), so its heartbeat key is known rather than scanned."""

MAX_DAYS = 90


async def _heartbeat(redis: redis_asyncio.Redis) -> tuple[dict[str, str] | None, str | None]:
    """The worker's hash, decoded; ``(None, error_type)`` when Redis cannot answer."""
    try:
        raw = cast("dict[bytes, bytes]", await redis.hgetall(MEME_HEARTBEAT_KEY))
    except redis_exceptions.RedisError as exc:
        logger.warning("meme_lab_heartbeat_unavailable", error_type=type(exc).__name__)
        return None, type(exc).__name__
    return {k.decode(errors="replace"): v.decode(errors="replace") for k, v in raw.items()}, None


@router.get(
    "/lab",
    response_model=MemeLabOut,
    summary="The paper Lab's scoreboard per rule set per Brasília day, the goal, the sources",
)
async def get_meme_lab(
    context: ViewerOrg,
    session: OrgSession,
    redis: Redis,
    days: Annotated[int, Query(ge=1, le=MAX_DAYS)] = DEFAULT_DAYS_LIMIT,
) -> MemeLabOut:
    heartbeat, error = await _heartbeat(redis)
    return await build_meme_lab(
        MemeLabRepository(session),
        heartbeat,
        as_of=utcnow(),
        heartbeat_key=MEME_HEARTBEAT_KEY,
        redis_error=error,
        days_limit=days,
    )
