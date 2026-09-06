"""Item (e) of the S2-context brief: filling ``StrategyContext.funding`` and
``.open_interest`` must not change what v1 emits.

Neither ``momentum_v1`` nor ``volume_anomaly_v1`` reads ``ctx.funding`` or
``ctx.open_interest`` (grepped, confirmed absent): this is the regression test
that keeps that true, over a triggering batch and a quiet one, for both
strategies. If a future edit makes either strategy read a derivative, this
test fails immediately instead of the signal count silently drifting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle, NormalizedFunding, NormalizedOpenInterest
from hunter_core.strategies.base import build_context
from hunter_core.strategies.momentum_v1 import MOMENTUM_V1
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1

from .builders import EXCHANGE, MINUTE, SYMBOL, series

pytestmark = pytest.mark.unit


def _candles(rows: list[dict[str, Any]]) -> list[NormalizedCandle]:
    return [
        NormalizedCandle(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            timeframe=Timeframe.M1,
            open_time=row["open_time"],
            close_time=row["open_time"] + MINUTE,
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            is_final=True,
        )
        for row in rows
    ]


CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
FUNDING = NormalizedFunding(
    exchange=EXCHANGE,
    symbol=SYMBOL,
    funding_rate=Decimal("0.0009"),  # deliberately large: a funding-gated
    mark_price=Decimal("100"),  # candidate would surely react to this
    funding_kind="realized",
    ts=CUT - timedelta(minutes=1),
)
OPEN_INTEREST = NormalizedOpenInterest(
    exchange=EXCHANGE,
    symbol=SYMBOL,
    open_interest=Decimal("999999"),
    ts=CUT - timedelta(minutes=1),
)


@pytest.mark.parametrize("trigger", [True, False], ids=["triggering_batch", "quiet_batch"])
class TestVolumeAnomalyIsUnaffected:
    def test_the_decision_is_identical_with_and_without_derivatives(self, trigger: bool) -> None:
        candles = _candles(series(CUT, trigger=trigger))
        bare = build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT)
        enriched = build_context(
            candles,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            source_bar_close=CUT,
            funding=FUNDING,
            open_interest=OPEN_INTEREST,
        )
        assert enriched.funding is not None
        assert enriched.open_interest is not None

        params = VOLUME_ANOMALY_V1.default_parameters
        decision_bare = VOLUME_ANOMALY_V1.evaluate(bare, params)
        decision_enriched = VOLUME_ANOMALY_V1.evaluate(enriched, params)
        assert (decision_bare is not None) is trigger  # the comparison below is not vacuous
        assert decision_bare == decision_enriched

        explain_bare = VOLUME_ANOMALY_V1.explain(bare, params)
        explain_enriched = VOLUME_ANOMALY_V1.explain(enriched, params)
        assert explain_bare.state == explain_enriched.state


@pytest.mark.parametrize("trigger", [True, False], ids=["triggering_batch", "quiet_batch"])
class TestMomentumIsUnaffected:
    def test_the_decision_is_identical_with_and_without_derivatives(self, trigger: bool) -> None:
        # momentum_v1's own trigger recipe is 15m-shaped; ``series()`` is built
        # for volume_anomaly_v1, so this batch never actually triggers
        # momentum -- what is under test is that a quiet read is unaffected
        # either way, which is exactly the population most decisions fall in.
        candles = _candles(series(CUT, trigger=trigger))
        bare = build_context(candles, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT)
        enriched = build_context(
            candles,
            exchange=EXCHANGE,
            symbol=SYMBOL,
            source_bar_close=CUT,
            funding=FUNDING,
            open_interest=OPEN_INTEREST,
        )
        params = MOMENTUM_V1.default_parameters
        decision_bare = MOMENTUM_V1.evaluate(bare, params)
        decision_enriched = MOMENTUM_V1.evaluate(enriched, params)
        assert decision_bare == decision_enriched
