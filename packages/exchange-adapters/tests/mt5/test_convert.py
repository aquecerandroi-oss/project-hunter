"""Decimal <-> float at the MT5 boundary (contract I-$-1): exact for every tick multiple."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from hunter_exchanges.mt5.convert import (
    OffGridError,
    ceil_to_tick,
    decimal_from_float,
    epoch_from_utc,
    floor_to_tick,
    from_float_on_grid,
    money_from_float,
    nearest_to_tick,
    to_float_on_grid,
    utc_from_epoch,
    utc_from_msc,
)

pytestmark = pytest.mark.unit

TICKS = [Decimal("5"), Decimal("1"), Decimal("0.01"), Decimal("0.005"), Decimal("0.25")]


@given(tick=st.sampled_from(TICKS), n=st.integers(min_value=1, max_value=10_000_000))
def test_round_trip_is_exact_for_every_tick_multiple(tick: Decimal, n: int) -> None:
    price = n * tick
    assert from_float_on_grid(to_float_on_grid(price, tick), tick) == price


@given(tick=st.sampled_from(TICKS), n=st.integers(min_value=1, max_value=10_000_000))
def test_one_ulp_of_float_noise_snaps_back_to_the_grid(tick: Decimal, n: int) -> None:
    price = n * tick
    noisy_up = math.nextafter(float(price), math.inf)
    noisy_down = math.nextafter(float(price), -math.inf)
    assert from_float_on_grid(noisy_up, tick) == price
    assert from_float_on_grid(noisy_down, tick) == price


def test_known_noise_example_from_the_terminal() -> None:
    assert from_float_on_grid(130005.00000000001, Decimal("5")) == Decimal("130005")


def test_decimal_off_the_grid_is_refused_on_the_way_out() -> None:
    with pytest.raises(OffGridError):
        to_float_on_grid(Decimal("130003"), Decimal("5"))


def test_float_off_the_grid_is_refused_on_the_way_in() -> None:
    with pytest.raises(OffGridError):
        from_float_on_grid(130003.0, Decimal("5"))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_refused(bad: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        from_float_on_grid(bad, Decimal("5"))
    with pytest.raises(ValueError, match="finite"):
        decimal_from_float(bad)
    with pytest.raises(ValueError, match="finite"):
        money_from_float(bad, 2)


def test_non_positive_step_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        to_float_on_grid(Decimal("10"), Decimal("0"))
    with pytest.raises(ValueError, match="positive"):
        from_float_on_grid(10.0, Decimal("-1"))


def test_floor_ceil_nearest() -> None:
    tick = Decimal("5")
    assert floor_to_tick(Decimal("130003"), tick) == Decimal("130000")
    assert ceil_to_tick(Decimal("130003"), tick) == Decimal("130005")
    assert nearest_to_tick(Decimal("130003"), tick) == Decimal("130005")
    assert nearest_to_tick(Decimal("130001"), tick) == Decimal("130000")
    for exact in (Decimal("130000"), Decimal("130005")):
        assert floor_to_tick(exact, tick) == exact
        assert ceil_to_tick(exact, tick) == exact


def test_rounding_helpers_refuse_a_float() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        floor_to_tick(1.5, Decimal("0.5"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Decimal"):
        ceil_to_tick(Decimal("1.5"), 0.5)  # type: ignore[arg-type]


def test_money_quantizes_to_the_account_currency_digits() -> None:
    assert money_from_float(1234.5600000000002, 2) == Decimal("1234.56")
    assert money_from_float(100000.0, 2) == Decimal("100000.00")
    assert money_from_float(-0.256, 3) == Decimal("-0.256")


def test_decimal_from_float_uses_the_shortest_repr_without_exponent() -> None:
    assert decimal_from_float(0.2) == Decimal("0.2")
    assert str(decimal_from_float(100.0)) == "100"
    assert str(decimal_from_float(1e-05)) == "0.00001"
    assert decimal_from_float(0.0) == 0


def test_epoch_helpers_are_utc_and_reject_naive_datetimes() -> None:
    moment = utc_from_epoch(1_760_000_000)
    assert moment.tzinfo is UTC
    assert epoch_from_utc(moment) == 1_760_000_000
    assert utc_from_msc(1_760_000_000_123) == moment + timedelta(milliseconds=123)
    with pytest.raises(ValueError, match="naive"):
        epoch_from_utc(datetime(2026, 10, 17, 12, 0, 0))  # noqa: DTZ001 - the point of the test
    brt = timezone(timedelta(hours=-3))
    assert epoch_from_utc(datetime(2026, 10, 17, 9, 0, 0, tzinfo=brt)) == epoch_from_utc(
        datetime(2026, 10, 17, 12, 0, 0, tzinfo=UTC)
    )


def test_the_supported_range_is_a_billion_steps_and_beyond_it_a_value_is_exact_or_refused() -> None:
    for tick in TICKS:
        price = 10**9 * tick
        assert from_float_on_grid(to_float_on_grid(price, tick), tick) == price


@given(n=st.integers(min_value=10**9, max_value=10**15))
def test_outside_the_supported_range_the_answer_is_never_a_different_number(n: int) -> None:
    tick = Decimal("0.01")
    price = n * tick
    try:
        back = from_float_on_grid(to_float_on_grid(price, tick), tick)
    except OffGridError:
        return  # refused: fine
    assert back == price  # accepted: must be exact
