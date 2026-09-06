"""Hourly returns out of the 1-minute candles the collector persisted.

Three rules, and they are the whole module:

- **a bar is complete or it does not exist.** Sixty final 1-minute candles inside
  the UTC hour, or the hour yields no close. The unit of a hole is the missing
  1-minute candle — exactly the unit ``ingestion_gaps`` records (one row spans
  ``[gap_start, gap_end]`` in minutes) — so "contiguous" here means *the same
  thing the gap table means*, propagated upwards: a missing minute kills its
  hour, and killing an hour kills two returns (its own and its successor's);
- **only final candles.** The minute still printing never reaches the
  arithmetic, which is what makes a beta computed at 12:00:30 identical to the
  same beta recomputed from history a month later;
- **no sliding.** The predecessor must sit *exactly* one bar earlier. This is the
  defect KB-0060 found in its own SQL (``lag`` crossing a hole paired a 30-minute
  return with a 15-minute one) and the correction is structural here rather than
  a clause in a query.

Prices are ``Decimal`` from end to end; the division that turns two closes into a
return runs under ``hunter_core.strategies.numeric.CONTEXT``, so the answer never
depends on the ambient decimal context of whichever process asked.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

from hunter_core.domain.enums import Timeframe
from hunter_core.domain.market import NormalizedCandle
from hunter_core.domain.types import ensure_utc
from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.beta.model import DEFAULT_SPEC, BetaSpec, HourlyReturn

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MINUTE = timedelta(minutes=1)


def floor_bar(value: datetime, spec: BetaSpec = DEFAULT_SPEC) -> datetime:
    """``value`` rounded down to the bar boundary that opened at or before it."""
    minutes = (ensure_utc(value) - _EPOCH) // _MINUTE
    return _EPOCH + (minutes - minutes % spec.bar_minutes) * _MINUTE


def window_bounds(as_of: datetime, spec: BetaSpec = DEFAULT_SPEC) -> tuple[datetime, datetime]:
    """``[start, end]`` of the rolling window, ``end`` being the last closed bar.

    ``as_of`` is floored: a call at 12:37 measures the window that ended at
    12:00, because 12:00-13:00 has not happened yet. Only ``valid_until`` uses
    the raw ``as_of`` — that is a clock statement, not a data statement.
    """
    end = floor_bar(as_of, spec)
    return end - spec.window, end


def hourly_closes(
    candles: Iterable[NormalizedCandle],
    *,
    as_of: datetime,
    spec: BetaSpec = DEFAULT_SPEC,
) -> dict[datetime, Decimal]:
    """Bar start -> close, for every **complete** bar inside the window.

    One extra bar before ``window_start`` is admitted, because the first return
    of the window needs the close that precedes it — the same anchor
    ``regime/series.py`` requires for its hourly samples, for the same reason: a
    window that drops the return across its own left edge measures a different
    thing than the one it claims to measure.
    """
    as_of = ensure_utc(as_of)
    start, end = window_bounds(as_of, spec)
    earliest = start - spec.bar
    buckets: dict[datetime, dict[datetime, Decimal]] = {}
    for item in candles:
        if item.timeframe is not Timeframe.M1:
            raise ValueError(f"beta reads 1-minute candles only, got {item.timeframe.value}")
        if not item.is_final or ensure_utc(item.close_time) > as_of:
            continue
        open_time = ensure_utc(item.open_time)
        bucket = floor_bar(open_time, spec)
        if bucket < earliest or bucket + spec.bar > end:
            continue
        minutes = buckets.setdefault(bucket, {})
        if open_time in minutes:
            raise ValueError(f"{open_time.isoformat()} was supplied twice")
        minutes[open_time] = item.close
    return {
        bucket: minutes[bucket + (spec.bar_minutes - 1) * _MINUTE]
        for bucket, minutes in buckets.items()
        if len(minutes) == spec.bar_minutes
    }


def hourly_returns(
    candles: Iterable[NormalizedCandle],
    *,
    as_of: datetime,
    spec: BetaSpec = DEFAULT_SPEC,
) -> tuple[HourlyReturn, ...]:
    """One simple return per complete bar whose predecessor is also complete.

    Oldest first. ``hour_start`` labels the bar the return happened *in*: the
    move from the close of ``hour_start - 1h`` to the close of ``hour_start``.
    """
    closes = hourly_closes(candles, as_of=as_of, spec=spec)
    start, _ = window_bounds(as_of, spec)
    out: list[HourlyReturn] = []
    with localcontext(CONTEXT):
        for bucket in sorted(closes):
            if bucket < start:
                continue  # the anchor, never a sample of the window itself
            previous = closes.get(bucket - spec.bar)
            if previous is None or previous == 0:
                continue
            out.append(
                HourlyReturn(hour_start=bucket, value=(closes[bucket] - previous) / previous)
            )
    return tuple(out)


__all__ = ["floor_bar", "hourly_closes", "hourly_returns", "window_bounds"]
