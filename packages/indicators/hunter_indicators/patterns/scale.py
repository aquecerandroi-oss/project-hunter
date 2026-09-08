"""The ATR the pattern rules are measured in — one value per bar.

Every threshold in this package is expressed in ATRs (a 0.25 % wiggle in BTC
and in a memecoin are not the same event), so the geometry needs a *series*,
not the single reading ``features/atr.py`` publishes. It is the same recursion:
this module folds bars into the very same ``wilder_v1`` checkpoint one at a
time and keeps the reading each bar produced. There is no second ATR formula in
the repo, and there will not be one.

Two refusals, both deliberate:

- **warm-up is ``None``, never a substitute.** The first reading appears one
  smoothing step after the seed (bar ``period + 1``); before that a pivot has
  nothing to be measured against and is simply not a pivot yet;
- **a gap raises.** A trend line drawn across missing bars is a line through a
  hole — the caller must hand a contiguous window (the plotting script takes
  the longest contiguous run; a worker would use the cut window).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.features.atr import ATR_PERIOD, advance, bootstrap
from hunter_indicators.features.vector import Reason

__all__ = ["atr_series"]


def atr_series(
    bars: Sequence[Bar],
    *,
    period: int = ATR_PERIOD,
    timeframe: Timeframe = Timeframe.M15,
) -> tuple[Decimal | None, ...]:
    """Wilder ATR after each bar of ``bars`` (``None`` while warming up)."""
    if not bars:
        return ()
    first = bootstrap(bars[:1], period=period, timeframe=timeframe)
    checkpoint = first.checkpoint
    if checkpoint is None:  # pragma: no cover - bootstrap of one bar always anchors
        raise ValueError("could not anchor the ATR recursion")
    values: list[Decimal | None] = [checkpoint.value]
    for index, bar in enumerate(bars[1:], start=1):
        step = advance(checkpoint, [bar])
        if step.reason is Reason.GAP or step.checkpoint is None:
            raise ValueError(
                f"bars must be contiguous: {bar.open_time.isoformat()} (index {index}) "
                "does not follow the previous bar"
            )
        checkpoint = step.checkpoint
        values.append(checkpoint.value)
    return tuple(values)
