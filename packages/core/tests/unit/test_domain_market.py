"""Unit tests for hunter_core.domain.market."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel, TypeAdapter, ValidationError

from hunter_core.domain.enums import MarketStatus, MarketType, OrderSide, Timeframe
from hunter_core.domain.market import (
    BookLevel,
    DataQuality,
    NormalizedCandle,
    NormalizedEvent,
    NormalizedFunding,
    NormalizedLiquidation,
    NormalizedMarket,
    NormalizedOpenInterest,
    NormalizedOrderBook,
    NormalizedTicker,
    NormalizedTrade,
    align_open_time,
    close_time_for,
    data_quality,
    from_wire,
    is_aligned,
    timeframe_seconds,
    to_wire,
)

pytestmark = pytest.mark.unit

NAIVE = datetime(2026, 1, 1)  # noqa: DTZ001 - intentionally naive for tests
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def _market(**overrides: object) -> NormalizedMarket:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "market_type": MarketType.PERPETUAL,
        "base": "BTC",
        "quote": "USDT",
        "status": MarketStatus.ACTIVE,
        "tick_size": Decimal("0.1"),
        "step_size": Decimal("0.001"),
        "min_notional": Decimal("5"),
    }
    fields.update(overrides)
    return NormalizedMarket(**fields)  # type: ignore[arg-type]


def _ticker(**overrides: object) -> NormalizedTicker:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "ts": T0,
        "last": Decimal("50000"),
        "bid": Decimal("49999"),
        "ask": Decimal("50001"),
    }
    fields.update(overrides)
    return NormalizedTicker(**fields)  # type: ignore[arg-type]


def _trade(**overrides: object) -> NormalizedTrade:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "ts": T0,
        "trade_id": "1",
        "price": Decimal("50000"),
        "qty": Decimal("0.5"),
        "side": OrderSide.BUY,
    }
    fields.update(overrides)
    return NormalizedTrade(**fields)  # type: ignore[arg-type]


def _book(**overrides: object) -> NormalizedOrderBook:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "ts": T0,
        "bids": [
            BookLevel(price=Decimal("100"), qty=Decimal("3")),
            BookLevel(price=Decimal("99"), qty=Decimal("2")),
        ],
        "asks": [
            BookLevel(price=Decimal("101"), qty=Decimal("1")),
            BookLevel(price=Decimal("102"), qty=Decimal("1")),
        ],
        "is_snapshot": True,
    }
    fields.update(overrides)
    return NormalizedOrderBook(**fields)  # type: ignore[arg-type]


def _candle(**overrides: object) -> NormalizedCandle:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "timeframe": Timeframe.M1,
        "open_time": T0,
        "close_time": T0 + timedelta(minutes=1),
        "open": Decimal("100"),
        "high": Decimal("110"),
        "low": Decimal("95"),
        "close": Decimal("105"),
        "volume": Decimal("10"),
        "is_final": True,
    }
    fields.update(overrides)
    return NormalizedCandle(**fields)  # type: ignore[arg-type]


def _funding(**overrides: object) -> NormalizedFunding:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "ts": T0,
        "funding_rate": Decimal("0.0001"),
        "mark_price": Decimal("50000"),
    }
    fields.update(overrides)
    return NormalizedFunding(**fields)  # type: ignore[arg-type]


def _open_interest(**overrides: object) -> NormalizedOpenInterest:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "ts": T0,
        "open_interest": Decimal("1234.5"),
    }
    fields.update(overrides)
    return NormalizedOpenInterest(**fields)  # type: ignore[arg-type]


def _liquidation(**overrides: object) -> NormalizedLiquidation:
    fields: dict[str, Any] = {
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "ts": T0,
        "side": OrderSide.SELL,
        "qty": Decimal("2"),
        "price": Decimal("100"),
    }
    fields.update(overrides)
    return NormalizedLiquidation(**fields)  # type: ignore[arg-type]


# --- construction from valid data -------------------------------------------------


def test_normalized_market_constructs() -> None:
    market = _market()
    assert market.exchange == "binance"
    assert market.metadata == {}


def test_normalized_ticker_constructs() -> None:
    assert _ticker().last == Decimal("50000")


def test_normalized_trade_constructs() -> None:
    assert _trade().side == OrderSide.BUY


def test_normalized_order_book_constructs() -> None:
    assert _book().is_snapshot is True


def test_normalized_candle_constructs() -> None:
    assert _candle().is_final is True


def test_normalized_funding_constructs() -> None:
    assert _funding().funding_rate == Decimal("0.0001")


def test_normalized_candle_event_ts_defaults_none() -> None:
    assert _candle().event_ts is None


def test_normalized_candle_event_ts_accepts_aware() -> None:
    assert _candle(event_ts=T0).event_ts == T0


def test_normalized_funding_kind_defaults_estimated() -> None:
    assert _funding().funding_kind == "estimated"


def test_normalized_funding_kind_accepts_realized() -> None:
    assert _funding(funding_kind="realized").funding_kind == "realized"


def test_normalized_funding_metadata_defaults_empty() -> None:
    assert _funding().metadata == {}


def test_normalized_open_interest_constructs() -> None:
    assert _open_interest().open_interest == Decimal("1234.5")


def test_normalized_liquidation_constructs() -> None:
    assert _liquidation().side == OrderSide.SELL


# --- naive datetime / negative qty rejected ---------------------------------------


def test_naive_datetime_rejected_on_ticker() -> None:
    with pytest.raises(ValidationError):
        _ticker(ts=NAIVE)


def test_naive_datetime_rejected_on_received_at() -> None:
    with pytest.raises(ValidationError):
        _ticker(received_at=NAIVE)


def test_naive_datetime_rejected_on_candle_open_time() -> None:
    with pytest.raises(ValidationError):
        _candle(open_time=NAIVE, close_time=NAIVE + timedelta(minutes=1))


def test_naive_datetime_rejected_on_candle_event_ts() -> None:
    with pytest.raises(ValidationError):
        _candle(event_ts=NAIVE)


def test_invalid_funding_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        _funding(funding_kind="bogus")


def test_negative_qty_rejected_on_book_level() -> None:
    with pytest.raises(ValidationError):
        BookLevel(price=Decimal("1"), qty=Decimal("-1"))


# --- order book ---------------------------------------------------------------------


def test_book_bids_must_be_sorted_descending() -> None:
    with pytest.raises(ValidationError):
        _book(
            bids=[
                BookLevel(price=Decimal("99"), qty=Decimal("1")),
                BookLevel(price=Decimal("100"), qty=Decimal("1")),
            ]
        )


def test_book_asks_must_be_sorted_ascending() -> None:
    with pytest.raises(ValidationError):
        _book(
            asks=[
                BookLevel(price=Decimal("102"), qty=Decimal("1")),
                BookLevel(price=Decimal("101"), qty=Decimal("1")),
            ]
        )


def test_book_best_bid_ask_mid_spread() -> None:
    book = _book()
    assert book.best_bid == Decimal("100")
    assert book.best_ask == Decimal("101")
    assert book.mid == Decimal("100.5")
    assert book.spread_pct == (Decimal("1") / Decimal("100.5")) * 100


def test_book_imbalance_math() -> None:
    book = _book()
    # bids 3+2=5, asks 1+1=2 -> (5-2)/7 = 3/7
    assert book.imbalance(2) == Decimal("3") / Decimal("7")


def test_book_imbalance_none_when_both_sides_empty() -> None:
    book = _book(bids=[], asks=[])
    assert book.imbalance(2) is None


# --- ticker spread_pct ---------------------------------------------------------------


def test_ticker_spread_pct_computed() -> None:
    ticker = _ticker(bid=Decimal("100"), ask=Decimal("102"))
    assert ticker.spread_pct == Decimal("2") / Decimal("101") * 100


@pytest.mark.parametrize(("bid", "ask"), [(None, Decimal("100")), (Decimal("100"), None)])
def test_ticker_spread_pct_none_when_bid_or_ask_missing(
    bid: Decimal | None, ask: Decimal | None
) -> None:
    assert _ticker(bid=bid, ask=ask).spread_pct is None


# --- candle invariants ---------------------------------------------------------------


def test_candle_rejects_high_below_close_or_open() -> None:
    with pytest.raises(ValidationError):
        _candle(high=Decimal("90"))


def test_candle_rejects_low_above_close_or_open() -> None:
    with pytest.raises(ValidationError):
        _candle(low=Decimal("101"))


def test_candle_rejects_close_time_not_after_open_time() -> None:
    with pytest.raises(ValidationError):
        _candle(close_time=T0)


def test_candle_rejects_misaligned_open_time() -> None:
    with pytest.raises(ValidationError):
        _candle(
            open_time=T0 + timedelta(seconds=30),
            close_time=T0 + timedelta(seconds=90),
        )


def test_candle_accepts_aligned_open_time() -> None:
    assert _candle(open_time=T0, close_time=T0 + timedelta(minutes=1)).open_time == T0


# --- liquidation notional default -----------------------------------------------------


def test_liquidation_computes_notional_when_missing() -> None:
    liq = _liquidation(qty=Decimal("2"), price=Decimal("100"))
    assert liq.notional == Decimal("200")


def test_liquidation_keeps_given_notional() -> None:
    liq = _liquidation(qty=Decimal("2"), price=Decimal("100"), notional=Decimal("199"))
    assert liq.notional == Decimal("199")


# --- timeframe helpers -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("tf", "seconds"),
    [
        (Timeframe.M1, 60),
        (Timeframe.M5, 300),
        (Timeframe.M15, 900),
        (Timeframe.H1, 3600),
        (Timeframe.H4, 14400),
        (Timeframe.D1, 86400),
    ],
)
def test_timeframe_seconds(tf: Timeframe, seconds: int) -> None:
    assert timeframe_seconds(tf) == seconds


@pytest.mark.parametrize(
    ("tf", "ts", "expected"),
    [
        (
            Timeframe.M1,
            datetime(2026, 1, 1, 12, 0, 30, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        ),
        (
            Timeframe.M15,
            datetime(2026, 1, 1, 12, 20, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 15, 0, tzinfo=UTC),
        ),
        (
            Timeframe.H1,
            datetime(2026, 1, 1, 12, 40, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
        ),
        (
            Timeframe.D1,
            datetime(2026, 1, 1, 18, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
        ),
    ],
)
def test_align_open_time(tf: Timeframe, ts: datetime, expected: datetime) -> None:
    assert align_open_time(ts, tf) == expected


@pytest.mark.parametrize(
    ("tf", "open_time", "expected_close"),
    [
        (Timeframe.M1, T0, T0 + timedelta(minutes=1)),
        (Timeframe.M15, T0, T0 + timedelta(minutes=15)),
        (Timeframe.H1, T0, T0 + timedelta(hours=1)),
        (Timeframe.D1, T0, T0 + timedelta(days=1)),
    ],
)
def test_close_time_for(tf: Timeframe, open_time: datetime, expected_close: datetime) -> None:
    assert close_time_for(open_time, tf) == expected_close


def test_is_aligned_true_and_false() -> None:
    assert is_aligned(T0, Timeframe.M1) is True
    assert is_aligned(T0 + timedelta(seconds=1), Timeframe.M1) is False


@given(
    st.datetimes(
        min_value=datetime(2020, 1, 1),  # noqa: DTZ001 - hypothesis bounds are naive by design
        max_value=datetime(2035, 1, 1),  # noqa: DTZ001 - hypothesis bounds are naive by design
    ),
    st.sampled_from(list(Timeframe)),
)
def test_align_open_time_is_idempotent(dt: datetime, tf: Timeframe) -> None:
    aware = dt.replace(tzinfo=UTC)
    aligned = align_open_time(aware, tf)
    assert align_open_time(aligned, tf) == aligned


# --- data_quality ------------------------------------------------------------------------


def test_data_quality_unavailable_when_never_seen() -> None:
    assert (
        data_quality(None, now=T0, stale_after_s=10, has_open_gap=False) is DataQuality.UNAVAILABLE
    )


def test_data_quality_degraded_when_gap_open() -> None:
    assert (
        data_quality(T0, now=T0 + timedelta(seconds=1), stale_after_s=10, has_open_gap=True)
        is DataQuality.DEGRADED
    )


def test_data_quality_stale_when_too_old() -> None:
    assert (
        data_quality(T0, now=T0 + timedelta(seconds=11), stale_after_s=10, has_open_gap=False)
        is DataQuality.STALE
    )


def test_data_quality_ok() -> None:
    assert (
        data_quality(T0, now=T0 + timedelta(seconds=1), stale_after_s=10, has_open_gap=False)
        is DataQuality.OK
    )


# --- wire round trip -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "build",
    [_market, _ticker, _trade, _book, _candle, _funding, _open_interest, _liquidation],
)
def test_wire_round_trip(build: Callable[[], BaseModel]) -> None:
    model = build()
    wire = to_wire(model)
    restored = from_wire(type(model), wire)
    assert restored == model


@pytest.mark.parametrize("value", [Decimal("0.00000001"), Decimal("123456789.123456789")])
def test_wire_round_trip_preserves_decimal_precision(value: Decimal) -> None:
    ticker = _ticker(last=value)
    restored = from_wire(NormalizedTicker, to_wire(ticker))
    assert restored.last == value
    assert str(restored.last) == str(value)


def test_wire_round_trip_candle_with_event_ts() -> None:
    candle = _candle(event_ts=T0 + timedelta(seconds=1))
    restored = from_wire(NormalizedCandle, to_wire(candle))
    assert restored == candle
    assert restored.event_ts == T0 + timedelta(seconds=1)


def test_wire_round_trip_candle_without_event_ts() -> None:
    candle = _candle()
    restored = from_wire(NormalizedCandle, to_wire(candle))
    assert restored == candle
    assert restored.event_ts is None


def test_wire_round_trip_funding_realized_with_metadata() -> None:
    funding = _funding(funding_kind="realized", metadata={"raw_event": "fundingRate"})
    restored = from_wire(NormalizedFunding, to_wire(funding))
    assert restored == funding
    assert restored.funding_kind == "realized"
    assert restored.metadata == {"raw_event": "fundingRate"}


# --- discriminated union -------------------------------------------------------------------


def test_normalized_event_discriminates_by_kind() -> None:
    adapter: TypeAdapter[NormalizedEvent] = TypeAdapter(NormalizedEvent)
    for model in (
        _ticker(),
        _trade(),
        _book(),
        _candle(),
        _funding(),
        _open_interest(),
        _liquidation(),
    ):
        restored = adapter.validate_python(to_wire(model))
        assert type(restored) is type(model)
        assert restored == model
