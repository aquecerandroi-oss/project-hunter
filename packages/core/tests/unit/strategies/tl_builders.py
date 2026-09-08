"""Synthetic OHLC series with pivots we can name by hand — the T3.34 generator.

Copied (not imported) from ``packages/indicators/tests/patterns/builders.py``:
``hunter_core`` must not depend on ``hunter_indicators``, in tests any more than
in production, and the parity test is precisely the place where the *same*
series has to be fed to both implementations without one of them owning it.

The wave is deterministic on purpose: a linear trend plus a triangular
oscillation, so the swing lows sit *exactly* on one straight line and the swing
highs on another, parallel one. Every expected value in the trend-line tests is
derived from these two formulas, never from a previous run of the detector.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hunter_core.strategies.aggregate import Bar

ORIGIN = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
STEP = timedelta(minutes=15)

LOW0 = Decimal("100")
TREND = Decimal("0.5")
AMP = Decimal("1.5")
PERIOD = 10
HEIGHT = Decimal("2")
PHASE0 = 5
"""Bar index of the first trough — lows sit at 5, 15, 25 …, highs at 10, 20 …"""


def offset(index: int) -> Decimal:
    phase = (index - PHASE0) % PERIOD
    half = PERIOD // 2
    return AMP * Decimal(phase if phase <= half else PERIOD - phase)


def wave_low(index: int) -> Decimal:
    return LOW0 + TREND * Decimal(index) + offset(index)


def support_price(index: int) -> Decimal:
    """The line the troughs sit on: ``low`` at every ``index`` with offset 0."""
    return LOW0 + TREND * Decimal(index)


def resistance_price(index: int) -> Decimal:
    """The line the peaks sit on: ``high`` at every peak index."""
    return support_price(index) + AMP * Decimal(PERIOD // 2) + HEIGHT


def bars(count: int, *, volume: Decimal = Decimal("10")) -> tuple[Bar, ...]:
    out: list[Bar] = []
    previous_close: Decimal | None = None
    for index in range(count):
        low = wave_low(index)
        high = low + HEIGHT
        close = low + HEIGHT / 2
        open_price = previous_close if previous_close is not None else close
        out.append(
            Bar(
                open_time=ORIGIN + index * STEP,
                close_time=ORIGIN + (index + 1) * STEP,
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        previous_close = close
    return tuple(out)


def replace_bar(
    series: Sequence[Bar],
    index: int,
    *,
    high: Decimal | None = None,
    low: Decimal | None = None,
    close: Decimal | None = None,
    volume: Decimal | None = None,
) -> tuple[Bar, ...]:
    """One bar changed, everything else identical — for violation/breakout cases."""
    current = series[index]
    edited = Bar(
        open_time=current.open_time,
        close_time=current.close_time,
        open=current.open,
        high=current.high if high is None else high,
        low=current.low if low is None else low,
        close=current.close if close is None else close,
        volume=current.volume if volume is None else volume,
    )
    return (*series[:index], edited, *series[index + 1 :])


def walk(steps: Sequence[int]) -> tuple[Bar, ...]:
    """A random walk in tenths, as ``Decimal`` all the way — never a float."""
    out: list[Bar] = []
    price = Decimal("1000")
    previous_close = price
    for index, step in enumerate(steps):
        price = price + Decimal(step) / Decimal(10)
        half = Decimal(1 + index % 5) / Decimal(2)
        out.append(
            Bar(
                open_time=ORIGIN + index * STEP,
                close_time=ORIGIN + (index + 1) * STEP,
                open=previous_close,
                high=max(price, previous_close) + half,
                low=min(price, previous_close) - half,
                close=price,
                volume=Decimal("10"),
            )
        )
        previous_close = price
    return tuple(out)
