"""T3.0b — the shadow worker prices the market it was asked about.

``load_market`` resolved ``(exchange, symbol)`` with ``LIMIT 1`` and no order:
the day ``markets`` holds both listings of ``BTCUSDT`` that returns whichever
row Postgres felt like, and every candle, funding reading and signal after it
belongs to a market nobody chose. The hot-state readers had the same hole, one
level down: one key for two markets.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import msgpack
import pytest
from sqlalchemy import text

from hunter_core.db.session import role_session
from hunter_core.domain.enums import MarketStatus, MarketType, Timeframe
from hunter_core.domain.market import NormalizedCandle, to_wire
from hunter_strategy_worker import hot_state
from hunter_strategy_worker.repo import MarketRow, load_market

from . import builders

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
SPOT = MarketType.SPOT
_codec: Any = msgpack


def _candle(close: str, *, market_type: MarketType) -> bytes:
    payload = to_wire(
        NormalizedCandle(
            exchange=builders.EXCHANGE,
            symbol=builders.SYMBOL,
            market_type=market_type,
            timeframe=Timeframe.M1,
            open_time=datetime(2026, 9, 5, 11, 58, tzinfo=UTC),
            close_time=datetime(2026, 9, 5, 11, 59, tzinfo=UTC),
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=Decimal("1"),
            is_final=True,
        )
    )
    packed: Any = _codec.packb(payload, use_bin_type=True)
    return bytes(packed)


class _FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[bytes]] = {}
        self.hashes: dict[str, dict[str, str]] = {}

    async def lrange(self, key: str, start: int, end: int) -> list[bytes]:
        rows = self.lists.get(key, [])
        return rows[start : end + 1] if end >= 0 else rows[start:]

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))


@pytest.mark.unit
def test_market_row_defaults_to_the_perpetual() -> None:
    row = MarketRow(
        id=uuid.UUID(int=1),
        symbol=builders.SYMBOL,
        exchange=builders.EXCHANGE,
        is_monitored=True,
        status=MarketStatus.ACTIVE,
    )
    assert row.market_type is MarketType.PERPETUAL


@pytest.mark.unit
async def test_the_candle_tail_of_each_listing_comes_from_its_own_key() -> None:
    redis = _FakeRedis()
    redis.lists["mkt:binance:BTCUSDT:candles:1m"] = [
        _candle("100", market_type=MarketType.PERPETUAL)
    ]
    redis.lists["mkt:binance:spot:BTCUSDT:candles:1m"] = [_candle("200", market_type=SPOT)]

    perpetual = await hot_state.read_tail(
        redis,  # type: ignore[arg-type]
        exchange=builders.EXCHANGE,
        symbol=builders.SYMBOL,
        count=5,
        cut=CUT,
    )
    spot = await hot_state.read_tail(
        redis,  # type: ignore[arg-type]
        exchange=builders.EXCHANGE,
        symbol=builders.SYMBOL,
        count=5,
        cut=CUT,
        market_type=SPOT,
    )

    assert [c.close for c in perpetual] == [Decimal("100")]
    assert [c.close for c in spot] == [Decimal("200")]


@pytest.mark.unit
async def test_a_row_of_the_wrong_listing_is_refused_not_repriced() -> None:
    """Same guard the exchange/symbol check already gives: a row that says it
    is another market is dropped, never read as this one."""
    redis = _FakeRedis()
    redis.lists["mkt:binance:spot:BTCUSDT:candles:1m"] = [
        _candle("100", market_type=MarketType.PERPETUAL)
    ]

    tail = await hot_state.read_tail(
        redis,  # type: ignore[arg-type]
        exchange=builders.EXCHANGE,
        symbol=builders.SYMBOL,
        count=5,
        cut=CUT,
        market_type=SPOT,
    )

    assert tail == []


@pytest.mark.unit
async def test_derivatives_are_read_from_the_markets_own_hash() -> None:
    redis = _FakeRedis()
    redis.hashes["mkt:binance:BTCUSDT:deriv"] = {
        "funding_rate": "0.0001",
        "funding_ts": datetime(2026, 9, 5, 11, 0, tzinfo=UTC).isoformat(),
    }

    perpetual = await hot_state.read_derivatives(
        redis,  # type: ignore[arg-type]
        exchange=builders.EXCHANGE,
        symbol=builders.SYMBOL,
        cut=CUT,
    )
    spot = await hot_state.read_derivatives(
        redis,  # type: ignore[arg-type]
        exchange=builders.EXCHANGE,
        symbol=builders.SYMBOL,
        cut=CUT,
        market_type=SPOT,
    )

    assert perpetual.funding_rate == Decimal("0.0001")
    # Spot has no funding at all: the answer is "nothing here", never the
    # perpetual's rate under a spot market's name.
    assert spot.funding_rate is None


@pytest.mark.integration
async def test_load_market_returns_the_listing_it_was_asked_for(db_session_factory: Any) -> None:
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        exchange_id, perpetual_id = await builders.seed_market(session)
        spot_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO markets (id, exchange_id, symbol, market_type, status, "
                "is_monitored, last_seen_at) "
                "VALUES (:id, :exchange_id, :symbol, 'spot', 'active', false, now()) "
                "ON CONFLICT (exchange_id, symbol, market_type) DO NOTHING"
            ),
            {"id": spot_id, "exchange_id": exchange_id, "symbol": builders.SYMBOL},
        )

    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        default = await load_market(session, builders.EXCHANGE, builders.SYMBOL)
        spot = await load_market(session, builders.EXCHANGE, builders.SYMBOL, SPOT)

    assert default is not None and default.id == perpetual_id
    assert default.market_type is MarketType.PERPETUAL
    assert spot is not None and spot.id != perpetual_id
    assert spot.market_type is SPOT
