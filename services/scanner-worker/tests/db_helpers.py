"""Shared DB seeding for integration tests — one market row per call, with
assets/exchange upserted idempotently so parallel tests never collide on the
unique ``assets.symbol``/``exchanges.code`` constraints."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hunter_core.db.models.markets import Asset, Exchange, Market
from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketType


async def _upsert_asset(session: Any, symbol: str) -> Any:
    stmt = (
        pg_insert(Asset)
        .values(symbol=symbol)
        .on_conflict_do_update(index_elements=["symbol"], set_={"symbol": symbol})
        .returning(Asset.id)
    )
    return await session.scalar(stmt)


async def _upsert_exchange(session: Any, code: str) -> Any:
    stmt = (
        pg_insert(Exchange)
        .values(code=code, name=code)
        .on_conflict_do_update(index_elements=["code"], set_={"code": code})
        .returning(Exchange.id)
    )
    return await session.scalar(stmt)


async def seed_market(
    session_factory: Any, exchange_code: str, symbol: str, *, base: str = "BTC", quote: str = "USDT"
) -> Any:
    """Create (or find) an exchange, its base/quote assets, and one perpetual
    market for ``symbol``. Returns the market's id."""
    async with role_session(session_factory, db_role="hunter_worker") as session:
        existing = await session.scalar(
            select(Market.id)
            .join(Exchange, Exchange.id == Market.exchange_id)
            .where(Exchange.code == exchange_code, Market.symbol == symbol)
        )
        if existing is not None:
            return existing
        exchange_id = await _upsert_exchange(session, exchange_code)
        base_id = await _upsert_asset(session, base)
        quote_id = await _upsert_asset(session, quote)
        market = Market(
            exchange_id=exchange_id,
            symbol=symbol,
            market_type=MarketType.PERPETUAL,
            base_asset_id=base_id,
            quote_asset_id=quote_id,
        )
        session.add(market)
        await session.flush()
        return market.id
