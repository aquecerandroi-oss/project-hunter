"""``/api/v1/system/workers`` and ``/api/v1/system/market-status``.

Distinct from ``health.py``'s ``/api/v1/system/info`` (public, unauthenticated
metadata): these two expose operational detail — which workers are alive,
which exchange connections are up — so they sit behind the same
authentication every other route in this file requires. Not tenant routes:
worker liveness and market connectivity are process-wide facts, not scoped to
an organization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import redis.exceptions as redis_exceptions
from fastapi import APIRouter, Depends, status

from hunter_api.auth.rbac import CurrentPrincipal
from hunter_api.deps import PrincipalSession, get_redis
from hunter_api.errors import HunterError
from hunter_api.schemas.latency import LatencyOut
from hunter_api.schemas.system import MarketStatusOut, WorkerHeartbeatOut
from hunter_api.services.latency import build_latency
from hunter_api.services.system_status import build_market_status, scan_heartbeats

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

router = APIRouter(prefix="/api/v1/system", tags=["system"])

Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]


class WorkersUnavailableError(HunterError):
    """(G4) Raised when the ``hb:*`` heartbeat scan itself fails (Redis
    unreachable, or a key raising ``WRONGTYPE`` mid-scan) -- distinct from a
    healthy scan finding no heartbeats, which is a normal ``200 []``.
    ``detail`` never names the Redis key, command or connection string.
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="workers-unavailable",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Worker heartbeat data is temporarily unavailable.",
        )


class MarketStatusUnavailableError(HunterError):
    """(G4) Raised when every exchange's heartbeat read failed wholesale --
    an actual Redis outage, not "no worker has reported for any exchange
    yet". A single exchange's own heartbeat misbehaving still degrades only
    that row and returns ``200`` (``services/system_status.py``).
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="market-status-unavailable",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Market connectivity status is temporarily unavailable.",
        )


class LatencyUnavailableError(HunterError):
    """(G4) The same rule as the two errors above: a Redis outage while
    reading any of the three heartbeat sources answers ``503``, never a
    ``200`` a healthy-but-unmeasured pipeline would be indistinguishable
    from.
    """

    def __init__(self) -> None:
        super().__init__(
            type_slug="latency-unavailable",
            title="Service Unavailable",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="End-to-end latency data is temporarily unavailable.",
        )


@router.get("/workers", response_model=list[WorkerHeartbeatOut], summary="Worker liveness")
async def list_workers(principal: CurrentPrincipal, redis: Redis) -> list[WorkerHeartbeatOut]:
    """No Postgres involved — ``CurrentPrincipal`` alone is enough
    authentication, so this skips opening a transaction ``PrincipalSession``
    would otherwise pay for on every call.
    """
    del principal  # authentication only
    try:
        return await scan_heartbeats(redis)
    except redis_exceptions.RedisError as exc:
        raise WorkersUnavailableError from exc


@router.get(
    "/market-status", response_model=MarketStatusOut, summary="Per-exchange market connectivity"
)
async def market_status(session: PrincipalSession, redis: Redis) -> MarketStatusOut:
    try:
        return await build_market_status(session, redis)
    except redis_exceptions.RedisError as exc:
        raise MarketStatusUnavailableError from exc


@router.get(
    "/latency",
    response_model=LatencyOut,
    summary="End-to-end latency budget: market -> decision -> admission -> fill",
)
async def latency(principal: CurrentPrincipal, redis: Redis) -> LatencyOut:
    """No Postgres involved, same as ``/workers`` — every hop is read off a
    heartbeat hash a worker already writes (``schemas/latency.py``)."""
    del principal  # authentication only; VIEWER+ i.e. any authenticated member
    try:
        return await build_latency(redis)
    except redis_exceptions.RedisError as exc:
        raise LatencyUnavailableError from exc
