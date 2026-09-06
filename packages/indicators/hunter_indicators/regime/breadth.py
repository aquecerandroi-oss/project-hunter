"""The trend of one market, and the breadth of the universe made of them.

Two things live here because they are the same question at two scales, and both
are **evidence for the global regime**, never rows of their own:
``market_regimes`` holds ``global``/``btc`` scopes (``RegimeScope``), so a
per-market verdict is a :class:`MarketTrendReading` and stays in the envelope
(Astra, T2.4 design review, 9g).

The breadth follows ``docs/PIPELINE.md`` §4 — the fraction of monitored markets
whose 4-hour return is positive *and* whose relative volume is above 1.5 — with
one rule the joint decision adds: **below 80% coverage the confirmation is
unavailable, not bearish.** Reporting 0.1 because only twenty markets could be
read would say "the market is falling" when the truth is "we could not look", and
the composition (who was counted, who was excluded and why) is recorded so the
number can be audited afterwards.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.regime.model import (
    RATIO_QUANTUM,
    REASON_ATR_WARMUP,
    REASON_BREADTH_COVERAGE,
    REASON_NO_TREND_INPUT,
    Breadth,
    BreadthObservation,
    MarketTrendReading,
    RegimeThresholds,
    RegimeTrend,
)

REASON_MISSING_RETURN = "missing_return_4h"
REASON_MISSING_VOLUME = "missing_relative_volume_1h"


def trend_of(
    *,
    return_4h: Decimal | None,
    return_1d: Decimal | None,
    atr_pct: Decimal | None,
    thresholds: RegimeThresholds,
) -> tuple[RegimeTrend, str | None, Decimal | None, Decimal | None]:
    """``(trend, reason, r_4h, r_1d)`` for one market, in ATR units.

    Both horizons must **agree on the side** and at least one must clear its
    multiple. Requiring both to clear would call a slow, one-directional grind
    sideways; requiring neither to agree would call a four-hour bounce inside a
    falling day a bull market.
    """
    if return_4h is None or return_1d is None or atr_pct is None:
        return RegimeTrend.UNKNOWN, REASON_NO_TREND_INPUT, None, None
    if atr_pct <= 0:
        return RegimeTrend.UNKNOWN, REASON_ATR_WARMUP, None, None
    with localcontext(CONTEXT):
        r_4h = (return_4h / atr_pct).quantize(RATIO_QUANTUM)
        r_1d = (return_1d / atr_pct).quantize(RATIO_QUANTUM)
        up = (
            return_4h > 0
            and return_1d > 0
            and (
                r_4h >= thresholds.trend_4h_atr_multiple or r_1d >= thresholds.trend_1d_atr_multiple
            )
        )
        down = (
            return_4h < 0
            and return_1d < 0
            and (
                -r_4h >= thresholds.trend_4h_atr_multiple
                or -r_1d >= thresholds.trend_1d_atr_multiple
            )
        )
    if up:
        return RegimeTrend.BULL, None, r_4h, r_1d
    if down:
        return RegimeTrend.BEAR, None, r_4h, r_1d
    return RegimeTrend.SIDEWAYS, None, r_4h, r_1d


def classify_market_trend(
    market: str,
    *,
    return_4h: Decimal | None,
    return_1d: Decimal | None,
    atr_pct: Decimal | None,
    thresholds: RegimeThresholds,
) -> MarketTrendReading:
    """:func:`trend_of` for one named market, as evidence."""
    trend, reason, r_4h, r_1d = trend_of(
        return_4h=return_4h,
        return_1d=return_1d,
        atr_pct=atr_pct,
        thresholds=thresholds,
    )
    return MarketTrendReading(market=market, trend=trend, reason=reason, r_4h=r_4h, r_1d=r_1d)


def compute_breadth(
    observations: Sequence[BreadthObservation],
    *,
    universe_size: int,
    thresholds: RegimeThresholds,
) -> Breadth:
    """How much of ``universe_size`` is advancing with volume, and who was counted.

    ``coverage`` is measured against the **declared universe**, not against the
    observations that happened to arrive: a batch that lost half the markets on
    the way would otherwise report full coverage of itself.
    """
    advancing: list[str] = []
    excluded: dict[str, str] = {}
    usable_markets = 0
    for observation in observations:
        if observation.return_4h is None:
            excluded[observation.market] = REASON_MISSING_RETURN
            continue
        if observation.relative_volume_1h is None:
            excluded[observation.market] = REASON_MISSING_VOLUME
            continue
        usable_markets += 1
        if (
            observation.return_4h > 0
            and observation.relative_volume_1h > thresholds.breadth_relative_volume_min
        ):
            advancing.append(observation.market)
    with localcontext(CONTEXT):
        coverage = (
            Decimal(0)
            if universe_size <= 0
            else (Decimal(usable_markets) / Decimal(universe_size)).quantize(RATIO_QUANTUM)
        )
        usable = usable_markets > 0 and coverage >= thresholds.breadth_min_coverage
        fraction = (
            (Decimal(len(advancing)) / Decimal(usable_markets)).quantize(RATIO_QUANTUM)
            if usable
            else None
        )
    return Breadth(
        fraction=fraction,
        coverage=coverage,
        universe_size=universe_size,
        usable_markets=usable_markets,
        advancing=len(advancing),
        members=tuple(sorted(advancing)),
        excluded=dict(sorted(excluded.items())),
        usable=usable,
        reason=None if usable else REASON_BREADTH_COVERAGE,
    )


__all__ = [
    "REASON_MISSING_RETURN",
    "REASON_MISSING_VOLUME",
    "classify_market_trend",
    "compute_breadth",
    "trend_of",
]
