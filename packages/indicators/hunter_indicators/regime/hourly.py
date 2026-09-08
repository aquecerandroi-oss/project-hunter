"""``regime_hourly_v1``: one snapshot of market context per closed hour.

Pure functions over ``Decimal`` series the caller already holds. Nothing here
reads a clock, a database or an exchange — the scanner job resolves the inputs
(``hunter_scanner_worker.regime_repo``) and persists the verdict.

The estimators, written down because "trend" and "volatility" alone are not
reproducible:

- **trend** is *structure plus movement*, and needs both: the last close above
  (below) the slow average, the fast average above (below) the slow one, and the
  fast average itself moving by at least ``trend_slope_min`` over
  ``slope_lookback_hours``. Two out of three is ``flat``. A market that has
  drifted 3 % in a week under a stacked average is not trending, and a market
  whose averages are crossed but whose price is on the wrong side of the slow one
  is a market in the middle of changing its mind;
- **volatility** is the mean absolute hourly return of the last day, ranked
  against the same reading taken every hour over the previous thirty days. The
  mean absolute return rather than a standard deviation for the reason
  ``series.py`` already gives: it is exact in ``Decimal`` and claims no
  normality. The rank is a **mid-rank** — ties split — so a perfectly constant
  tape ranks at 50 (``normal``) instead of at 100 (``high``);
- **drawdown** is how far the last close sits below the 30-day high.

The weighing of these into ``score_0_100`` is
:mod:`hunter_indicators.regime.hourly_score`; nothing here knows about weights.

**No look-ahead, by construction.** Every function takes closes keyed by the hour
they *close*, and :func:`contiguous_closes` stops at ``ts``: the bar
``[ts, ts + 1h)`` cannot enter a snapshot cut at ``ts`` even when the caller hands
it over. The caller's own query filters ``is_final`` and demands sixty minutes
per hour, so an hour that is still printing does not exist on either side.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.regime.hourly_model import (
    HOUR,
    RATIO_QUANTUM,
    REASON_TREND_WARMUP,
    REASON_VOL_WARMUP,
    SCORE_QUANTUM,
    HourlyThresholds,
    HourlyTrend,
    VolRegime,
)
from hunter_indicators.regime.model import VOLATILITY_QUANTUM

HUNDRED = Decimal(100)
HALF = Decimal("0.5")


def contiguous_closes(
    closes: Mapping[datetime, Decimal], *, ts: datetime, limit: int
) -> tuple[Decimal, ...]:
    """The unbroken run of hourly closes ending at the bar that closed at ``ts``.

    Keys are **hour starts**; the newest usable bar is the one starting at
    ``ts - 1h``, because that is the last hour entirely behind the cut. Walking
    backwards and stopping at the first hole is deliberate: an average over a
    gapped window is an average over a window nobody can name.
    """
    ts = ensure_utc(ts)
    run: list[Decimal] = []
    hour = ts - HOUR
    while len(run) < limit:
        close = closes.get(hour)
        if close is None:
            break
        run.append(close)
        hour -= HOUR
    run.reverse()
    return tuple(run)


def sma(values: Sequence[Decimal], length: int) -> Decimal | None:
    """The mean of the last ``length`` values, or ``None`` if there are fewer."""
    if length <= 0 or len(values) < length:
        return None
    with localcontext(CONTEXT):
        return sum(values[-length:], Decimal(0)) / Decimal(length)


def absolute_returns(closes: Sequence[Decimal]) -> tuple[Decimal, ...]:
    """``|close_i / close_{i-1} - 1|``. A zero price ends the series there."""
    out: list[Decimal] = []
    with localcontext(CONTEXT):
        for previous, current in zip(closes, closes[1:], strict=False):
            if previous == 0:
                return ()
            out.append(abs((current - previous) / previous))
    return tuple(out)


def realised_vol(returns: Sequence[Decimal]) -> Decimal | None:
    """The mean absolute return of a window, quantised to the stored resolution."""
    if not returns:
        return None
    with localcontext(CONTEXT):
        return (sum(returns, Decimal(0)) / Decimal(len(returns))).quantize(VOLATILITY_QUANTUM)


def vol_readings(closes: Sequence[Decimal], *, window: int) -> tuple[Decimal, ...]:
    """One realised-volatility reading per hour, oldest first, last = current."""
    returns = absolute_returns(closes)
    if len(returns) < window or window <= 0:
        return ()
    out: list[Decimal] = []
    for end in range(window, len(returns) + 1):
        value = realised_vol(returns[end - window : end])
        if value is None:  # pragma: no cover - a non-empty slice always averages
            continue
        out.append(value)
    return tuple(out)


def percentile_rank(distribution: Sequence[Decimal], current: Decimal) -> Decimal:
    """Mid-rank of ``current`` in ``distribution``, in percent.

    Ties count half, so an unchanging distribution puts its own value at 50
    instead of at 100 — the difference between "as usual" and "the most volatile
    day of the month", which is the whole point of the reading.
    """
    if not distribution:
        return Decimal(0)
    below = sum(1 for value in distribution if value < current)
    equal = sum(1 for value in distribution if value == current)
    with localcontext(CONTEXT):
        rank = (Decimal(below) + HALF * Decimal(equal)) / Decimal(len(distribution))
        return (rank * HUNDRED).quantize(SCORE_QUANTUM)


@dataclass(frozen=True, slots=True)
class TrendVerdict:
    """The trend and the three statistics that produced it."""

    trend: HourlyTrend
    sma_fast: Decimal | None = None
    sma_slow: Decimal | None = None
    slope: Decimal | None = None
    reason: str | None = None


def classify_trend(closes: Sequence[Decimal], thresholds: HourlyThresholds) -> TrendVerdict:
    """Structure **and** movement, or ``flat``; not enough history, ``unknown``."""
    needed = thresholds.sma_slow_hours + thresholds.slope_lookback_hours
    if len(closes) < needed:
        return TrendVerdict(trend=HourlyTrend.UNKNOWN, reason=REASON_TREND_WARMUP)
    fast = sma(closes, thresholds.sma_fast_hours)
    slow = sma(closes, thresholds.sma_slow_hours)
    earlier = sma(
        closes[: len(closes) - thresholds.slope_lookback_hours], thresholds.sma_fast_hours
    )
    if fast is None or slow is None or earlier is None or earlier == 0:
        return TrendVerdict(trend=HourlyTrend.UNKNOWN, reason=REASON_TREND_WARMUP)
    with localcontext(CONTEXT):
        slope = ((fast - earlier) / earlier).quantize(RATIO_QUANTUM)
    last = closes[-1]
    minimum = thresholds.trend_slope_min
    if last > slow and fast > slow and slope >= minimum:
        trend = HourlyTrend.UP
    elif last < slow and fast < slow and slope <= -minimum:
        trend = HourlyTrend.DOWN
    else:
        trend = HourlyTrend.FLAT
    return TrendVerdict(trend=trend, sma_fast=fast, sma_slow=slow, slope=slope)


@dataclass(frozen=True, slots=True)
class VolVerdict:
    """The volatility bucket, the current reading and where it ranked."""

    vol_regime: VolRegime
    current: Decimal | None = None
    percentile: Decimal | None = None
    samples: int = 0
    reason: str | None = None


def classify_volatility(closes: Sequence[Decimal], thresholds: HourlyThresholds) -> VolVerdict:
    """Rank today's realised volatility against the last thirty days of it."""
    span = thresholds.vol_reference_hours + thresholds.vol_window_hours + 1
    readings = vol_readings(closes[-span:], window=thresholds.vol_window_hours)
    if not readings:
        return VolVerdict(vol_regime=VolRegime.UNKNOWN, reason=REASON_VOL_WARMUP)
    current = readings[-1]
    distribution = readings[:-1][-thresholds.vol_reference_hours :]
    if len(distribution) < thresholds.vol_min_samples:
        return VolVerdict(
            vol_regime=VolRegime.UNKNOWN,
            current=current,
            samples=len(distribution),
            reason=REASON_VOL_WARMUP,
        )
    percentile = percentile_rank(distribution, current)
    if percentile >= thresholds.vol_high_percentile:
        bucket = VolRegime.HIGH
    elif percentile <= thresholds.vol_low_percentile:
        bucket = VolRegime.LOW
    else:
        bucket = VolRegime.NORMAL
    return VolVerdict(
        vol_regime=bucket, current=current, percentile=percentile, samples=len(distribution)
    )


def drawdown_from_high(
    closes: Sequence[Decimal], thresholds: HourlyThresholds
) -> tuple[Decimal | None, Decimal | None]:
    """``(drawdown %, the high it is measured from)`` over the 30-day window."""
    window = closes[-thresholds.drawdown_window_hours :]
    if len(window) < thresholds.drawdown_min_hours:
        return None, None
    high = max(window)
    if high <= 0:
        return None, None
    with localcontext(CONTEXT):
        return (((high - window[-1]) / high) * HUNDRED).quantize(SCORE_QUANTUM), high


__all__ = [
    "TrendVerdict",
    "VolVerdict",
    "absolute_returns",
    "classify_trend",
    "classify_volatility",
    "contiguous_closes",
    "drawdown_from_high",
    "percentile_rank",
    "realised_vol",
    "sma",
    "vol_readings",
]
