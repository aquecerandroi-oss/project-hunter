"""The statistics the regime needs and the T2.2 feature set does not publish.

``return_1d`` and a realised-volatility estimator are not registered features, so
they are computed here, from the **persisted 1-minute candles the caller hands
over** — never from a REST call (``docs/plans/M2.md`` §REST) and never from the
candle still forming: every function below filters ``is_final`` first, which is
what makes the regime immune to the tick that is still moving.

They are declared as *internal versioned statistics* of ``regime_v0``, not as
features: nothing here goes into ``feature_snapshots`` or into the feature-set
hash, and calling them features would put two definitions of the same name in the
system (Astra, T2.4 design review, 9b).

The estimator, in full, because "median of 30 days" alone is not reproducible
(Astra, 9b):

- **one sample = one complete UTC hour**: the sixty contiguous final 1-minute
  candles of that hour **plus the close that precedes them**, giving sixty
  close-to-close returns. A missing minute — or a missing anchor — rejects the
  hour rather than thinning it. The anchor is not decoration: without it every
  hourly sample would systematically drop the return *across* the hour boundary,
  and a market that jumps at the top of the hour would show a reference of zero
  while the trailing window measured the jump (Astra, T2.4 diff review). The cost
  is declared: the first hour of a history has no predecessor and is never
  sampled;
- **the estimate is the mean absolute 1-minute return** of the window. Chosen
  over a standard deviation because it is exact in ``Decimal`` (no square root,
  no ambient-precision dependence) and because it does not claim the normality a
  sigma implies. Quantised to ten decimals, the resolution Postgres holds;
- **the reference is the median** of the hourly samples over the last
  ``volatility_window_days``, and it is only usable with enough samples over
  enough distinct days; a zero median is refused (there is no scale), never
  replaced by a floor;
- **the current reading is the trailing window of the same length**, measured with
  the same estimator over the same number of returns, so the two are comparable.
  Only the alignment differs (the reference buckets are hour-aligned, the current
  window ends at ``as_of``), and that is a declared assumption of ``regime_v0``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.regime.model import (
    REASON_NO_DISPERSION,
    REASON_VOLATILITY_WARMUP,
    VOLATILITY_QUANTUM,
    HourlySample,
    RegimeThresholds,
    VolatilityReference,
)

MINUTE = timedelta(minutes=1)
HOUR = timedelta(hours=1)


def final_candles(candles: Iterable[NormalizedCandle]) -> tuple[NormalizedCandle, ...]:
    """``candles`` that are closed, oldest first — the only ones anything reads."""
    closed = [candle for candle in candles if candle.is_final]
    closed.sort(key=lambda candle: candle.open_time)
    return tuple(closed)


def _by_close(candles: Sequence[NormalizedCandle]) -> dict[datetime, NormalizedCandle]:
    return {ensure_utc(candle.close_time): candle for candle in candles}


def return_over(
    candles: Sequence[NormalizedCandle],
    *,
    minutes: int,
    as_of: datetime,
) -> Decimal | None:
    """``(last close - close ``minutes`` earlier) / that close``, or ``None``.

    The reference bar must exist **exactly** at ``last_close - minutes``: sliding
    onto the nearest older bar would silently measure another window and make the
    number irreproducible.
    """
    as_of = ensure_utc(as_of)
    closed = [candle for candle in final_candles(candles) if candle.close_time <= as_of]
    if not closed:
        return None
    last = closed[-1]
    reference = _by_close(closed).get(ensure_utc(last.close_time) - minutes * MINUTE)
    if reference is None or reference.close == 0:
        return None
    with localcontext(CONTEXT):
        return (last.close - reference.close) / reference.close


def _mean_absolute_return(window: Sequence[NormalizedCandle]) -> Decimal | None:
    """Mean ``|close_i / close_{i-1} - 1|`` over a contiguous minute window."""
    if len(window) < 2:
        return None
    with localcontext(CONTEXT):
        total = Decimal(0)
        for previous, current in zip(window, window[1:], strict=False):
            if previous.close == 0:
                return None
            total += abs((current.close - previous.close) / previous.close)
        return (total / Decimal(len(window) - 1)).quantize(VOLATILITY_QUANTUM)


def _contiguous(window: Sequence[NormalizedCandle]) -> bool:
    """Every minute of the window is present, with no hole and no repetition."""
    return all(
        ensure_utc(nxt.open_time) - ensure_utc(cur.open_time) == MINUTE
        for cur, nxt in zip(window, window[1:], strict=False)
    )


def trailing_volatility(
    candles: Sequence[NormalizedCandle],
    *,
    as_of: datetime,
    thresholds: RegimeThresholds,
) -> Decimal | None:
    """The estimator over the last ``volatility_window_minutes`` closed returns.

    ``volatility_window_minutes + 1`` closes, because *n* returns need *n + 1*
    prices — the same count the hourly samples use, which is what makes the ratio
    between them mean anything.

    ``None`` — never a number — when the window is short, gapped or priced at
    zero: a volatility invented out of forty minutes would be compared against a
    reference built from sixty.
    """
    as_of = ensure_utc(as_of)
    closed = [candle for candle in final_candles(candles) if candle.close_time <= as_of]
    size = thresholds.volatility_window_minutes + 1
    if len(closed) < size:
        return None
    window = closed[-size:]
    if not _contiguous(window):
        return None
    return _mean_absolute_return(window)


def _floor_hour(value: datetime) -> datetime:
    return ensure_utc(value).replace(minute=0, second=0, microsecond=0)


def hourly_samples(
    candles: Sequence[NormalizedCandle],
    *,
    until: datetime,
    thresholds: RegimeThresholds,
    days: int | None = None,
) -> tuple[HourlySample, ...]:
    """One sample per **complete** UTC hour that ended at or before ``until``.

    The causal cut is the baseline's (``docs/DATABASE.md`` §17.2): a reference may
    not contain the observation it is used to judge, so an hour is only sampled
    once it is closed and behind ``until``.
    """
    until = ensure_utc(until)
    span = thresholds.volatility_window_days if days is None else days
    earliest = until - timedelta(days=span)
    closed = final_candles(candles)
    by_open = {ensure_utc(candle.open_time): candle for candle in closed}
    buckets: dict[datetime, list[NormalizedCandle]] = {}
    for candle in closed:
        hour = _floor_hour(candle.open_time)
        if hour < earliest or hour + HOUR > until:
            continue
        buckets.setdefault(hour, []).append(candle)
    samples: list[HourlySample] = []
    for hour in sorted(buckets):
        window = buckets[hour]
        if len(window) < thresholds.volatility_hour_min_minutes:
            continue
        anchor = by_open.get(hour - MINUTE)  # the close the hour starts from
        if anchor is None:
            continue
        window = [anchor, *window]
        if not _contiguous(window):
            continue
        value = _mean_absolute_return(window)
        if value is None:
            continue
        samples.append(HourlySample(hour_start=hour, value=value, minutes_used=len(window) - 1))
    return tuple(samples)


def _median(values: Sequence[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    with localcontext(CONTEXT):
        if len(ordered) % 2 == 1:
            return ordered[middle]
        return ((ordered[middle - 1] + ordered[middle]) / Decimal(2)).quantize(VOLATILITY_QUANTUM)


def volatility_reference(
    samples: Sequence[HourlySample],
    thresholds: RegimeThresholds,
) -> VolatilityReference:
    """The median of ``samples`` and whether it may be used as a scale."""
    distinct_days = len({sample.hour_start.date() for sample in samples})
    window_end = max((sample.hour_start + HOUR for sample in samples), default=None)
    if (
        len(samples) < thresholds.volatility_min_samples
        or distinct_days < thresholds.volatility_min_distinct_days
    ):
        return VolatilityReference(
            median=None,
            samples=len(samples),
            distinct_days=distinct_days,
            window_days=thresholds.volatility_window_days,
            usable=False,
            reason=REASON_VOLATILITY_WARMUP,
            window_end=window_end,
        )
    median = _median([sample.value for sample in samples])
    return VolatilityReference(
        median=median,
        samples=len(samples),
        distinct_days=distinct_days,
        window_days=thresholds.volatility_window_days,
        usable=median > 0,
        reason=None if median > 0 else REASON_NO_DISPERSION,
        window_end=window_end,
    )


__all__ = [
    "final_candles",
    "hourly_samples",
    "return_over",
    "trailing_volatility",
    "volatility_reference",
]
