"""Hourly returns out of persisted 1-minute candles — and the look-ahead proof.

The rule this module exists to enforce: an hour is a **sample** only when it is a
complete hour of *final* minutes. Sixty contiguous, aligned, final 1-minute
candles, and a predecessor hour that is itself complete, or there is no return
for that hour at all. Nothing is interpolated, nothing is thinned, and the candle
still printing never reaches the arithmetic.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from hunter_core.domain.market import NormalizedCandle
from hunter_indicators.beta import BetaSpec, hourly_closes, hourly_returns
from packages.indicators.tests.factories import candle

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)
H0 = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


def hour(
    start: datetime,
    close: Decimal,
    *,
    minutes: int = 60,
    final: bool = True,
    last_close: Decimal | None = None,
) -> list[NormalizedCandle]:
    """``minutes`` 1-minute candles inside the UTC hour that opens at ``start``.

    ``last_close`` overrides the price of the :59 candle — the hour's own close,
    and the only price an hourly return reads. ``final=False`` marks *only* that
    last candle as still printing, so a test can perturb exactly one non-final
    candle and nothing else (Astra, T3.2 diff review).
    """
    return [
        candle(
            start + index * MINUTE,
            close=close if index < minutes - 1 or last_close is None else last_close,
            is_final=final or index < minutes - 1,
        )
        for index in range(minutes)
    ]


def hours(closes: Sequence[Decimal], *, start: datetime = H0) -> list[NormalizedCandle]:
    out: list[NormalizedCandle] = []
    for index, close in enumerate(closes):
        out.extend(hour(start + index * HOUR, close))
    return out


def test_a_complete_hour_closes_at_its_last_minute() -> None:
    candles = hours([Decimal("100"), Decimal("110")])
    closes = hourly_closes(candles, as_of=H0 + 2 * HOUR)
    assert closes == {H0: Decimal("100"), H0 + HOUR: Decimal("110")}


def test_returns_are_simple_and_hour_over_hour() -> None:
    candles = hours([Decimal("100"), Decimal("110"), Decimal("121")])
    returns = hourly_returns(candles, as_of=H0 + 3 * HOUR)
    assert [item.hour_start for item in returns] == [H0 + HOUR, H0 + 2 * HOUR]
    assert [item.value for item in returns] == [Decimal("0.1"), Decimal("0.1")]


def test_a_missing_minute_costs_its_hour_and_the_next_return() -> None:
    """One absent 1-minute candle — the unit ``ingestion_gaps`` records — is a hole.

    The hour that lost the minute yields no close, and the hour after it loses
    its predecessor, so a single missing minute removes **two** hourly returns.
    """
    candles = hours([Decimal("100"), Decimal("110"), Decimal("121"), Decimal("133.1")])
    thinned = [item for item in candles if item.open_time != H0 + HOUR + 30 * MINUTE]
    returns = hourly_returns(thinned, as_of=H0 + 4 * HOUR)
    assert [item.hour_start for item in returns] == [H0 + 3 * HOUR]


def test_an_hour_of_fifty_nine_minutes_is_not_an_hour() -> None:
    candles = [*hour(H0, Decimal("100")), *hour(H0 + HOUR, Decimal("110"), minutes=59)]
    assert hourly_closes(candles, as_of=H0 + 2 * HOUR) == {H0: Decimal("100")}


def test_an_hour_that_has_not_closed_yet_is_never_sampled() -> None:
    candles = hours([Decimal("100"), Decimal("110")])
    # 01:30: the 01:00 hour is still printing even though its minutes are final.
    assert hourly_closes(candles, as_of=H0 + HOUR + 30 * MINUTE) == {H0: Decimal("100")}


def test_the_forming_minute_cannot_change_a_single_return() -> None:
    """The no-look-ahead proof: perturbing a non-final candle changes nothing.

    The 02:59 candle is the one still printing, and it is the **only** candle
    that differs between the two inputs: it is moved from 121 to 999, a 726%
    move, and every hourly return of the series stays byte-identical, because
    the hour it belongs to is not complete in *final* candles. ``as_of`` is
    deliberately 03:00, past the end of that hour: the cut alone would not
    exclude it, only the ``is_final`` rule does.
    """
    settled = hours([Decimal("100"), Decimal("110")])
    forming_low = [
        *settled,
        *hour(H0 + 2 * HOUR, Decimal("110"), last_close=Decimal("121"), final=False),
    ]
    forming_high = [
        *settled,
        *hour(H0 + 2 * HOUR, Decimal("110"), last_close=Decimal("999"), final=False),
    ]

    def shape(items: list[NormalizedCandle]) -> list[tuple[datetime, Decimal, bool]]:
        return [(item.open_time, item.close, item.is_final) for item in items]

    assert shape(forming_low[:-1]) == shape(forming_high[:-1])  # only the last one moved
    assert forming_low[-1].close != forming_high[-1].close
    assert forming_low[-1].is_final is False
    as_of = H0 + 3 * HOUR
    low = hourly_returns(forming_low, as_of=as_of)
    high = hourly_returns(forming_high, as_of=as_of)
    assert low == high
    assert [item.value for item in low] == [Decimal("0.1")]


def test_candles_after_the_cut_are_not_read() -> None:
    candles = hours([Decimal("100"), Decimal("110"), Decimal("121")])
    early = hourly_returns(candles, as_of=H0 + 2 * HOUR)
    assert [item.hour_start for item in early] == [H0 + HOUR]


def test_only_the_window_the_spec_declares_is_returned() -> None:
    spec = BetaSpec()
    candles = hours([Decimal("100")] * 3, start=H0 - timedelta(days=31))
    candles.extend(hours([Decimal("100"), Decimal("110")], start=H0))
    returns = hourly_returns(candles, as_of=H0 + 2 * HOUR, spec=spec)
    assert [item.hour_start for item in returns] == [H0 + HOUR]


def test_a_zero_close_yields_no_return_instead_of_a_division() -> None:
    candles = hours([Decimal("0"), Decimal("110"), Decimal("121")])
    returns = hourly_returns(candles, as_of=H0 + 3 * HOUR)
    assert [item.hour_start for item in returns] == [H0 + 2 * HOUR]


def test_a_duplicated_minute_is_refused_never_silently_deduplicated() -> None:
    candles = hours([Decimal("100")])
    with pytest.raises(ValueError, match="twice"):
        hourly_closes([*candles, candle(H0, close=Decimal("101"))], as_of=H0 + HOUR)


def test_a_five_minute_candle_is_refused() -> None:
    """Only the 1-minute timeframe: a 5m bar would silently count as one minute."""
    from hunter_core.domain.enums import Timeframe

    wrong = candle(H0, close=Decimal("100")).model_copy(
        update={"timeframe": Timeframe.M5, "close_time": H0 + 5 * MINUTE}
    )
    with pytest.raises(ValueError, match="1-minute"):
        hourly_closes([wrong], as_of=H0 + HOUR)
