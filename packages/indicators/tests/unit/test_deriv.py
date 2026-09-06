"""Derivative features — a change needs a reference, never "since I started"."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from hunter_indicators.features.context import (
    DerivObservation,
    DerivSnapshot,
    MarketContext,
    SourceEntry,
    build_context,
)
from hunter_indicators.features.deriv import (
    FundingChange,
    FundingRate,
    OpenInterestChange,
    deriv_calculators,
)
from hunter_indicators.features.state import EMPTY_STATE
from hunter_indicators.features.vector import Reason
from packages.indicators.tests.factories import EXCHANGE, MINUTE, ORIGIN, SYMBOL, series

AS_OF = ORIGIN + timedelta(hours=12)


def _ctx(
    snapshot: DerivSnapshot | None = None, history: list[DerivObservation] | None = None
) -> MarketContext:
    entry: SourceEntry[DerivSnapshot] = (
        SourceEntry(value=snapshot, ts=max(snapshot.timestamps()))
        if snapshot is not None
        else SourceEntry(reason="missing_input")
    )
    hist: SourceEntry[tuple[DerivObservation, ...]] = (
        SourceEntry(value=tuple(history), ts=history[-1].ts, covers_from=history[0].ts)
        if history
        else SourceEntry(reason="missing_input")
    )
    return build_context(
        exchange=EXCHANGE,
        symbol=SYMBOL,
        as_of=AS_OF,
        candles=series([Decimal("100")] * 10, start=AS_OF - 10 * MINUTE),
        deriv=entry,
        deriv_history=hist,
    )


class TestFundingRate:
    def test_the_current_rate_is_published_as_a_fraction(self) -> None:
        snapshot = DerivSnapshot(
            funding_rate=Decimal("0.0001"), funding_ts=AS_OF - timedelta(seconds=5)
        )
        value = FundingRate().compute(_ctx(snapshot), EMPTY_STATE)
        assert value.key == "funding_rate"
        assert value.value == Decimal("0.0001")

    def test_a_negative_rate_survives(self) -> None:
        snapshot = DerivSnapshot(
            funding_rate=Decimal("-0.00075"), funding_ts=AS_OF - timedelta(seconds=5)
        )
        assert FundingRate().compute(_ctx(snapshot), EMPTY_STATE).value == Decimal("-0.00075")

    def test_no_derivatives_is_missing_input(self) -> None:
        assert FundingRate().compute(_ctx(), EMPTY_STATE).reason is Reason.MISSING_INPUT


class TestOpenInterestChange:
    def test_change_against_the_reference_of_one_hour_ago(self) -> None:
        snapshot = DerivSnapshot(open_interest=Decimal("115"), oi_ts=AS_OF - timedelta(minutes=1))
        history = [
            DerivObservation(ts=AS_OF - timedelta(hours=4), open_interest=Decimal("50")),
            DerivObservation(ts=AS_OF - timedelta(minutes=59), open_interest=Decimal("100")),
        ]
        value = OpenInterestChange(hours=1).compute(_ctx(snapshot, history), EMPTY_STATE)
        assert value.key == "open_interest_change_1h"
        assert value.value == Decimal("0.15")

    def test_without_history_there_is_no_change(self) -> None:
        snapshot = DerivSnapshot(open_interest=Decimal("115"), oi_ts=AS_OF)
        value = OpenInterestChange(hours=1).compute(_ctx(snapshot), EMPTY_STATE)
        assert value.reason is Reason.MISSING_INPUT

    def test_a_reference_outside_the_tolerance_is_not_used(self) -> None:
        snapshot = DerivSnapshot(open_interest=Decimal("115"), oi_ts=AS_OF)
        history = [DerivObservation(ts=AS_OF - timedelta(minutes=30), open_interest=Decimal("100"))]
        value = OpenInterestChange(hours=1, tolerance_minutes=6).compute(
            _ctx(snapshot, history), EMPTY_STATE
        )
        assert value.reason is Reason.WARMUP

    def test_the_closest_observation_inside_the_tolerance_wins(self) -> None:
        snapshot = DerivSnapshot(open_interest=Decimal("110"), oi_ts=AS_OF)
        history = [
            DerivObservation(ts=AS_OF - timedelta(minutes=64), open_interest=Decimal("50")),
            DerivObservation(ts=AS_OF - timedelta(minutes=58), open_interest=Decimal("100")),
        ]
        value = OpenInterestChange(hours=1, tolerance_minutes=6).compute(
            _ctx(snapshot, history), EMPTY_STATE
        )
        assert value.value == Decimal("0.1")

    def test_a_zero_reference_has_no_relative_change(self) -> None:
        snapshot = DerivSnapshot(open_interest=Decimal("115"), oi_ts=AS_OF)
        history = [DerivObservation(ts=AS_OF - timedelta(hours=1), open_interest=Decimal("0"))]
        value = OpenInterestChange(hours=1).compute(_ctx(snapshot, history), EMPTY_STATE)
        assert value.reason is Reason.ZERO_DIVISOR


class TestFundingChange:
    def test_the_change_is_an_absolute_difference(self) -> None:
        snapshot = DerivSnapshot(
            funding_rate=Decimal("0.0003"), funding_ts=AS_OF - timedelta(seconds=5)
        )
        history = [DerivObservation(ts=AS_OF - timedelta(hours=8), funding_rate=Decimal("0.0001"))]
        value = FundingChange(hours=8).compute(_ctx(snapshot, history), EMPTY_STATE)
        assert value.key == "funding_change_8h"
        # a relative change on a rate that crosses zero is meaningless; the
        # definition says "difference", so 0.0003 - 0.0001
        assert value.value == Decimal("0.0002")

    def test_a_sign_flip_is_a_negative_difference(self) -> None:
        snapshot = DerivSnapshot(
            funding_rate=Decimal("-0.0002"), funding_ts=AS_OF - timedelta(seconds=5)
        )
        history = [DerivObservation(ts=AS_OF - timedelta(hours=8), funding_rate=Decimal("0.0001"))]
        assert FundingChange(hours=8).compute(
            _ctx(snapshot, history), EMPTY_STATE
        ).value == Decimal("-0.0003")


def test_the_registered_v1_set_is_frozen() -> None:
    assert [calc.definition.key for calc in deriv_calculators()] == [
        "funding_change_8h",
        "funding_rate",
        "open_interest_change_1h",
        "open_interest_change_4h",
    ]
