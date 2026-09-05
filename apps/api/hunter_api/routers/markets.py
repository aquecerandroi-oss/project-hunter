"""``/api/v1/markets`` — global market reference data plus Redis hot state.

Not a tenant route: markets are global, no-RLS data (``markets.py`` model
docstring), so any authenticated member of any organization may read every
row — the caller's principal is used for authentication only, never to scope
a query. ``PrincipalSession`` (``deps.py``) is what makes that a
``hunter_app`` transaction with no ``app.current_org`` set, per
``ARCHITECTURE.md`` §9's "Repositorios globais (``MarketRepository``) so
leitura para tenants."
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import AfterValidator

from hunter_api.deps import PrincipalSession, get_redis, get_settings
from hunter_api.errors import HunterError
from hunter_api.repositories.base import MAX_PAGE_SIZE
from hunter_api.repositories.markets import CandleRepository, MarketRepository
from hunter_api.schemas.markets import CandleOut, MarketDetailOut, MarketListPage
from hunter_api.services.markets import build_market_detail, build_market_list_page
from hunter_core.domain.enums import Timeframe
from hunter_core.domain.types import ensure_utc

if TYPE_CHECKING:
    import redis.asyncio as redis_asyncio

    from hunter_api.settings import ApiSettings

router = APIRouter(prefix="/api/v1/markets", tags=["markets"])

MAX_CANDLES_LIMIT = 1500
DEFAULT_CANDLES_LIMIT = 500

Redis = Annotated["redis_asyncio.Redis", Depends(get_redis)]
Settings = Annotated["ApiSettings", Depends(get_settings)]

UtcDatetime = Annotated[datetime, AfterValidator(ensure_utc)]
"""(F4) ``ensure_utc`` raises ``ValueError`` for a naive datetime -- FastAPI
turns that into a 422 in the project's RFC 9457 shape -- and normalizes any
explicit offset to UTC, so ``before`` always cuts at the same instant
asyncpg is told about regardless of the offset the caller sent or the
process's own timezone (a naive value would otherwise be interpreted in the
*process*'s timezone by asyncpg, silently changing the cut point)."""


class MarketNotFoundError(HunterError):
    def __init__(self) -> None:
        super().__init__(
            type_slug="market-not-found",
            title="Not Found",
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Market not found.",
        )


@router.get("", response_model=MarketListPage, summary="List markets")
async def list_markets(
    session: PrincipalSession,
    redis: Redis,
    settings: Settings,
    exchange: Annotated[str | None, Query(max_length=32)] = None,
    q: Annotated[str | None, Query(max_length=64)] = None,
    monitored: bool | None = None,
    limit: Annotated[int | None, Query(ge=1, le=MAX_PAGE_SIZE)] = None,
    cursor: str | None = None,
) -> MarketListPage:
    rows = await MarketRepository(session).list_markets(exchange=exchange, q=q, monitored=monitored)
    return await build_market_list_page(
        session,
        rows,
        redis,
        limit=limit,
        cursor=cursor,
        stale_after_s=settings.market_stale_after_s,
    )


@router.get("/{exchange}/{symbol}", response_model=MarketDetailOut, summary="Read one market")
async def get_market(
    exchange: str,
    symbol: str,
    session: PrincipalSession,
    redis: Redis,
    settings: Settings,
) -> MarketDetailOut:
    row = await MarketRepository(session).get_market(exchange, symbol)
    if row is None:
        raise MarketNotFoundError
    return await build_market_detail(
        session, row, redis, stale_after_s=settings.market_stale_after_s
    )


@router.get(
    "/{exchange}/{symbol}/candles", response_model=list[CandleOut], summary="Read final candles"
)
async def get_candles(
    exchange: str,
    symbol: str,
    session: PrincipalSession,
    timeframe: Timeframe = Timeframe.M1,
    limit: Annotated[int, Query(ge=1, le=MAX_CANDLES_LIMIT)] = DEFAULT_CANDLES_LIMIT,
    before: UtcDatetime | None = None,
) -> list[CandleOut]:
    market = await MarketRepository(session).get_market(exchange, symbol)
    if market is None:
        raise MarketNotFoundError
    candles = await CandleRepository(session).list_candles(
        market.id, timeframe, limit=limit, before=before
    )
    return CandleOut.from_candles(candles, timeframe)
