"""T3.0b — the scanner reads and writes the keys of *one* market.

Every projection the scanner owns (``feat:``, ``opp:``, the Radar ZSET member,
``scan:state:``) and every read it makes (hot state, tape coverage) is keyed by
exchange + symbol. With two listings of ``BTCUSDT`` that is one key for two
markets: the spot context would be built from perpetual candles, and the
perpetual's warm checkpoint would be overwritten by the spot scanner's.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from hunter_core.domain.enums import (
    MarketType,
    OpportunityStage,
    OpportunityStatus,
    TradeDirection,
)
from hunter_scanner_worker.checkpoint import load_checkpoint, save_checkpoint
from hunter_scanner_worker.context import build_market_context
from hunter_scanner_worker.coverage import read_coverage
from hunter_scanner_worker.publish import drop_from_radar, publish_features, publish_radar
from hunter_scanner_worker.registry import MarketRef

from . import builders

pytestmark = pytest.mark.unit

SPOT = MarketType.SPOT
CUT = builders.ORIGIN + timedelta(hours=3)
SPOT_REF = MarketRef(
    market_id=UUID(int=2),
    exchange=builders.EXCHANGE,
    symbol=builders.SYMBOL,
    market_type=SPOT,
)


def test_the_registry_ref_carries_the_market_type() -> None:
    """Default perpetual: the scanner's universe query is perpetual-only."""
    assert builders.REF.market_type is MarketType.PERPETUAL
    assert SPOT_REF.market_type is SPOT


async def test_the_context_of_a_spot_market_is_not_built_from_perpetual_candles() -> None:
    redis = builders.FakeHotState()
    redis.load(candles=builders.series(40), as_of=CUT)  # perpetual keys only

    coverage = await read_coverage(cast("Any", redis), builders.EXCHANGE, now=CUT)
    build = await build_market_context(
        cast("Any", redis),
        exchange=builders.EXCHANGE,
        symbol=builders.SYMBOL,
        coverage=coverage,
        now=CUT,
        market_type=SPOT,
    )

    assert build.context.final_candles == ()
    assert build.context.book.value is None


async def test_coverage_is_read_per_venue_and_market_type() -> None:
    redis = builders.FakeHotState()
    redis.publish_coverage(session_since=builders.ORIGIN, covered_until=CUT)

    perpetual = await read_coverage(cast("Any", redis), builders.EXCHANGE, now=CUT)
    spot = await read_coverage(cast("Any", redis), builders.EXCHANGE, now=CUT, market_type=SPOT)

    assert perpetual.for_symbol(builders.SYMBOL) == (builders.ORIGIN, CUT)
    assert spot.for_symbol(builders.SYMBOL) == (None, None)


async def test_the_warm_checkpoint_of_each_listing_is_its_own() -> None:
    redis = builders.FakeHotState()
    checkpoint = await load_checkpoint(cast("Any", redis), builders.EXCHANGE, builders.SYMBOL)

    await save_checkpoint(
        cast("Any", redis), builders.EXCHANGE, builders.SYMBOL, checkpoint, market_type=SPOT
    )

    assert "scan:state:binance:spot:BTCUSDT" in redis.strings
    assert "scan:state:binance:BTCUSDT" not in redis.strings


def _scored_evaluation() -> Any:
    """The smallest evaluation ``publish_radar`` accepts as publishable."""
    state = SimpleNamespace(
        score=Decimal("42.00"),
        status=OpportunityStatus.HOT,
        stage=OpportunityStage.NONE,
        direction=TradeDirection.LONG,
    )
    return SimpleNamespace(
        score=SimpleNamespace(score=Decimal("42.00"), confidence=Decimal("0.5"), eligible=True),
        status=SimpleNamespace(state_out=state),
        observation_ts=CUT,
        scored=True,
        vector=SimpleNamespace(
            ts=CUT,
            feature_set_version="v1",
            as_json=lambda: {"f": 1},
        ),
    )


async def test_projections_of_the_two_listings_never_share_a_key() -> None:
    redis = builders.FakeHotState()
    evaluation = _scored_evaluation()

    await publish_features(cast("Any", redis), "test", SPOT_REF, evaluation)
    await publish_radar(cast("Any", redis), SPOT_REF, evaluation)

    assert "feat:binance:spot:BTCUSDT" in redis.strings
    assert "feat:binance:BTCUSDT" not in redis.strings
    assert "opp:binance:spot:BTCUSDT" in redis.strings
    assert "opp:binance:BTCUSDT" not in redis.strings
    assert redis.zsets["radar:scores"] == {"binance:spot:BTCUSDT": 42.0}

    await drop_from_radar(cast("Any", redis), SPOT_REF)

    assert redis.zsets["radar:scores"] == {}
    assert "opp:binance:spot:BTCUSDT" not in redis.strings
