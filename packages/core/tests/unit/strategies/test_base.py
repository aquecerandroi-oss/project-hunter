"""``StrategyContext``, ``Decision`` and the parameter helpers.

The context is the *only* thing a strategy sees, so its invariants are the
anti-look-ahead guarantee: final 1-minute candles, strictly increasing, none at
or after ``source_bar_close``. The strict constructor states the invariant;
:func:`build_context` is the filter the worker uses to reach it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from hunter_core.domain.enums import Timeframe, TradeDirection
from hunter_core.domain.market import NormalizedCandle, NormalizedFunding
from hunter_core.strategies.base import (
    PURPOSE_RESEARCH_ONLY,
    Decision,
    Invalidation,
    StrategyContext,
    build_context,
    param_decimal,
    param_int,
)
from hunter_core.strategies.envelope import AssumedCosts, FeatureEvidence, SupportingFeatures

from .conftest import EXCHANGE, ORIGIN, SYMBOL, D, flat, minute, series

pytestmark = pytest.mark.unit

CUT = ORIGIN + timedelta(minutes=15)


def clean_candles() -> list[NormalizedCandle]:
    return series([flat(D("100"), D("1"), D("10"))], timeframe=Timeframe.M15)


def envelope() -> SupportingFeatures:
    return SupportingFeatures(
        observation_ts=CUT,
        timeframe="15m",
        strategy_key="unit_test",
        strategy_version="v1",
        features=(FeatureEvidence(name="close", value=D("100")),),
        assumed_costs=AssumedCosts(
            spread_bps=D("2"), slippage_bps=D("5"), fee_bps=D("4"), max_entry_delay_s=120
        ),
        eligible=True,
    )


# --------------------------------------------------------------------------- context


def test_context_accepts_a_clean_series() -> None:
    ctx = StrategyContext(
        exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(clean_candles())
    )
    assert len(ctx.candles_1m) == 15
    assert ctx.eligible is True


def test_context_rejects_a_candle_at_or_after_the_cut() -> None:
    candles = clean_candles()
    candles.append(minute(CUT, D("100"), D("100"), D("100"), D("100"), D(0)))

    with pytest.raises(ValidationError, match="source_bar_close"):
        StrategyContext(
            exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(candles)
        )


def test_context_rejects_a_non_final_candle() -> None:
    candles = clean_candles()
    candles[-1] = minute(
        ORIGIN + timedelta(minutes=14), D("100"), D("100"), D("100"), D("100"), D(0), is_final=False
    )

    with pytest.raises(ValidationError, match="is_final"):
        StrategyContext(
            exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(candles)
        )


def test_context_rejects_unsorted_or_duplicated_candles() -> None:
    candles = clean_candles()
    candles[3], candles[4] = candles[4], candles[3]
    with pytest.raises(ValidationError, match="increasing"):
        StrategyContext(
            exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(candles)
        )

    duplicated = clean_candles()
    duplicated.append(duplicated[-1])
    with pytest.raises(ValidationError, match="increasing"):
        StrategyContext(
            exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(duplicated)
        )


def test_context_rejects_a_candle_from_another_market() -> None:
    """Two symbols interleaved would pass "increasing, no gaps" and aggregate
    two assets into one bar."""
    candles = clean_candles()
    candles[5] = candles[5].model_copy(update={"symbol": "ETHUSDT"})

    with pytest.raises(ValidationError, match="does not belong to"):
        StrategyContext(
            exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(candles)
        )


def test_context_rejects_a_candle_that_is_not_one_minute_long() -> None:
    candles = clean_candles()
    candles[0] = candles[0].model_copy(
        update={"close_time": candles[0].open_time + timedelta(minutes=5)}
    )

    with pytest.raises(ValidationError, match="exactly one minute"):
        StrategyContext(
            exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, candles_1m=tuple(candles)
        )


def test_context_rejects_funding_from_another_market() -> None:
    funding = NormalizedFunding(
        exchange=EXCHANGE,
        symbol="ETHUSDT",
        ts=CUT - timedelta(minutes=1),
        funding_rate=D("0.0001"),
        mark_price=D("100"),
    )
    with pytest.raises(ValidationError, match="does not belong to"):
        StrategyContext(exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, funding=funding)


def test_context_rejects_a_naive_cut() -> None:
    with pytest.raises(ValidationError):
        StrategyContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            source_bar_close=datetime(2026, 1, 1, 0, 15),  # noqa: DTZ001 - naive on purpose
            candles_1m=(),
        )


def test_context_rejects_derivatives_observed_after_the_cut() -> None:
    funding = NormalizedFunding(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        ts=CUT + timedelta(seconds=1),
        funding_rate=D("0.0001"),
        mark_price=D("100"),
    )
    with pytest.raises(ValidationError, match="source_bar_close"):
        StrategyContext(
            exchange=EXCHANGE,
            symbol=SYMBOL,
            source_bar_close=CUT,
            candles_1m=tuple(clean_candles()),
            funding=funding,
        )


def test_build_context_drops_non_final_and_future_candles_and_sorts() -> None:
    candles = clean_candles()
    polluted = [
        minute(CUT, D("100"), D("9999"), D("1"), D("500"), D("999")),  # future
        *reversed(candles),
        minute(  # the minute still forming
            CUT - timedelta(minutes=1),
            D("100"),
            D("9999"),
            D("1"),
            D("500"),
            D("9"),
            is_final=False,
        ),
    ]

    ctx = build_context(polluted, exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT)

    assert [candle.open_time for candle in ctx.candles_1m] == [
        candle.open_time for candle in candles
    ]


def test_build_context_carries_eligibility() -> None:
    ctx = build_context(
        clean_candles(),
        exchange=EXCHANGE,
        symbol=SYMBOL,
        source_bar_close=CUT,
        eligible=False,
        eligibility_reason="delisted",
    )
    assert ctx.eligible is False
    assert ctx.eligibility_reason == "delisted"


def test_build_context_keeps_derivatives_up_to_the_cut_only() -> None:
    stale = NormalizedFunding(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        ts=CUT - timedelta(minutes=1),
        funding_rate=D("0.0001"),
        mark_price=D("100"),
    )
    future = stale.model_copy(update={"ts": CUT + timedelta(minutes=1)})

    assert (
        build_context(
            [], exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, funding=future
        ).funding
        is None
    )
    assert (
        build_context(
            [], exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT, funding=stale
        ).funding
        is stale
    )


def test_build_context_normalises_a_non_utc_cut() -> None:
    ctx = build_context([], exchange=EXCHANGE, symbol=SYMBOL, source_bar_close=CUT.astimezone(UTC))
    assert ctx.source_bar_close == CUT


# --------------------------------------------------------------------------- decision


def decision(**overrides: object) -> Decision:
    fields: dict[str, object] = {
        "direction": TradeDirection.LONG,
        "reference_price": D("100"),
        "stop": D("97"),
        "target1": D("103"),
        "targets_informational": (D("106"), D("109")),
        "invalidations": (Invalidation(kind="close_below", level=D("99"), timeframe="15m"),),
        "horizon_s": 14400,
        "confidence": D("0.5"),
        "reason": "teste",
        "supporting_features": envelope(),
    }
    fields.update(overrides)
    return Decision.model_validate(fields)


def test_decision_is_frozen() -> None:
    dec = decision()
    with pytest.raises(ValidationError):
        dec.stop = D("1")  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [("stop", D("100")), ("stop", D("101")), ("target1", D("100")), ("target1", D("99"))],
)
def test_decision_rejects_broken_geometry(field: str, value: Decimal) -> None:
    with pytest.raises(ValidationError, match="stop < reference_price < target1"):
        decision(**{field: value})


def test_decision_rejects_short_in_v0() -> None:
    with pytest.raises(ValidationError):
        decision(direction=TradeDirection.SHORT)


def test_decision_rejects_a_non_positive_horizon() -> None:
    with pytest.raises(ValidationError):
        decision(horizon_s=0)


@pytest.mark.parametrize("value", [Decimal("-0.1"), Decimal("1.1")])
def test_decision_confidence_stays_in_the_unit_interval(value: Decimal) -> None:
    with pytest.raises(ValidationError):
        decision(confidence=value)


def test_decision_envelope_is_research_only_and_has_no_decision_time() -> None:
    payload = decision().supporting_features.to_jsonable()

    assert payload["purpose"] == PURPOSE_RESEARCH_ONLY
    assert payload["params_format"] == "1"
    assert payload["observation_ts"] == "2026-01-01T00:15:00Z"
    assert "decision_at" not in payload
    assert "cohort" not in payload


# --------------------------------------------------------------------------- params


def test_param_decimal_accepts_the_canonical_string_form() -> None:
    assert param_decimal({"rvol_min": "1.5"}, "rvol_min") == D("1.5")
    assert param_decimal({"rvol_min": D("1.5")}, "rvol_min") == D("1.5")
    assert param_decimal({"rvol_min": 2}, "rvol_min") == D("2")


def test_param_decimal_rejects_float_and_missing_keys() -> None:
    with pytest.raises(TypeError):
        param_decimal({"rvol_min": 1.5}, "rvol_min")
    with pytest.raises(KeyError):
        param_decimal({}, "rvol_min")


def test_param_int_rejects_a_fractional_value() -> None:
    assert param_int({"atr_period": "14"}, "atr_period") == 14
    with pytest.raises(ValueError, match="atr_period"):
        param_int({"atr_period": "14.5"}, "atr_period")
