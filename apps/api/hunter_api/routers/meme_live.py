"""``/api/v1/orgs/{org_id}/meme/live`` — the real executor's ledger and heartbeat
(VIEWER+), and ``sell-now`` on a real position (TRADER+, ``Idempotency-Key``).

The API never signs and never reads a key: ``api_live_enabled`` is its own flag,
read so the desk can show "Aprovar (REAL)"; everything about the executor comes
from ``hb:meme:executor`` and the ``0028`` tables. A ``sell-now`` sets the two
columns ``hunter_app`` is granted on ``meme_live_positions`` and nothing else —
the executor sells on its next pass, at the curve's price then, never at the
mark shown now. Idempotent by construction (a second request finds the first)
and audited in the caller's transaction.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Annotated, cast

import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Depends, status

from hunter_api.auth.rbac import OrgContext, require_org
from hunter_api.deps import OrgSession, get_redis, get_settings
from hunter_api.repositories.meme_live import MemeLiveRepository
from hunter_api.routers.orders import IdempotencyKey
from hunter_api.schemas.meme_live import MemeLiveOut, SellNowOut
from hunter_api.services.meme_desk_common import actor_id
from hunter_api.services.meme_desk_idempotency import key_hash
from hunter_api.services.meme_lab import day_bounds_brt
from hunter_api.services.meme_live import LivePositionNotFoundError, build_meme_live
from hunter_core.audit import AuditEvent, get_audit_sink
from hunter_core.domain.enums import OrganizationRole
from hunter_core.domain.types import utcnow
from hunter_core.logging import get_logger
from hunter_core.redis import keys

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_api.settings import ApiSettings

__all__ = ["MEME_EXECUTOR_HEARTBEAT_KEY", "router"]

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/orgs/{org_id}/meme", tags=["meme"])

ViewerOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.VIEWER))]
OperatorOrg = Annotated[OrgContext, Depends(require_org(OrganizationRole.TRADER))]
Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]
Settings = Annotated["ApiSettings", Depends(get_settings)]

MEME_EXECUTOR_HEARTBEAT_KEY = keys.heartbeat("meme", "executor")
RECENT_ORDERS = 50


async def _heartbeat(redis: redis_asyncio.Redis) -> tuple[dict[str, str] | None, str | None]:
    try:
        raw = cast("dict[bytes, bytes]", await redis.hgetall(MEME_EXECUTOR_HEARTBEAT_KEY))
    except redis_exceptions.RedisError as exc:
        logger.warning("meme_live_heartbeat_unavailable", error_type=type(exc).__name__)
        return None, type(exc).__name__
    return {k.decode(errors="replace"): v.decode(errors="replace") for k, v in raw.items()}, None


@router.get(
    "/live",
    response_model=MemeLiveOut,
    summary="The real executor: heartbeat, orders and positions — label REAL",
)
async def get_meme_live(
    context: ViewerOrg, session: OrgSession, redis: Redis, settings: Settings
) -> MemeLiveOut:
    now = utcnow()
    repo = MemeLiveRepository(session)
    _day, day_start, _end = day_bounds_brt(now)
    heartbeat, error = await _heartbeat(redis)
    return build_meme_live(
        await repo.list_orders(limit=RECENT_ORDERS),
        await repo.list_positions(closed_since=day_start - timedelta(days=1)),
        heartbeat,
        as_of=now,
        heartbeat_key=MEME_EXECUTOR_HEARTBEAT_KEY,
        redis_error=error,
        api_live_enabled=settings.enable_meme_live_trading,
    )


@router.post(
    "/live/positions/{position_id}/sell-now",
    response_model=SellNowOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ask the executor to sell a real position on its next pass (TRADER+)",
)
async def sell_now_route(
    context: OperatorOrg,
    session: OrgSession,
    position_id: uuid.UUID,
    idempotency_key: IdempotencyKey,
) -> SellNowOut:
    repo = MemeLiveRepository(session)
    position = await repo.get_position(position_id)
    if position is None:
        raise LivePositionNotFoundError(position_id)
    now = utcnow()
    requested = await repo.request_sell(position_id, by=actor_id(context), now=now)
    sink = get_audit_sink()
    if requested and sink is not None:
        await sink.record(
            AuditEvent(
                actor_type="user",
                actor_id=str(context.principal.user_id),
                organization_id=context.org_id,
                action="meme_live.position.sell_now",
                entity_type="meme_live_position",
                entity_id=str(position_id),
                after={"mint": position.mint, "idempotency_key_hash": key_hash(idempotency_key)},
                metadata={"source": "meme_live", "mode": "live"},
            )
        )
    fresh = await repo.get_position(position_id)
    assert fresh is not None
    return SellNowOut(
        position_id=position_id,
        status=fresh.status,
        sell_requested_at=fresh.sell_requested_at,
        sell_requested_by=fresh.sell_requested_by,
        already_requested=not requested,
    )
