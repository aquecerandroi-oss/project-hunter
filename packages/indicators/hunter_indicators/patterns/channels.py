"""Channels: two lines the market is travelling between.

A channel is not a third kind of geometry — it is a **relation** between a
support and a resistance that :mod:`trendlines` already validated separately.
That is the whole family the classical material draws (canal, cunha, triângulo,
bandeira): two lines and the relation between their slopes. This module carries
the parallel one, which is the only relation a strategy needs today: the width
is what makes "the target is the width of the channel" a number instead of a
phrase, and it is expressed in ATRs so it means the same thing in BTC and in a
memecoin.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_indicators.patterns.trendlines import LineKind, TrendLine

__all__ = [
    "DEFAULT_MAX_CHANNELS",
    "DEFAULT_PARALLEL_TOL",
    "Channel",
    "find_channels",
]

DEFAULT_PARALLEL_TOL = Decimal("0.05")
"""Slope difference, in ATR per bar, that still counts as parallel."""
DEFAULT_MAX_CHANNELS = 3


@dataclass(frozen=True, slots=True)
class Channel:
    """Two parallel lines with price between them, at bar ``at_idx``."""

    upper: TrendLine
    lower: TrendLine
    at_idx: int
    width_atr: Decimal


def find_channels(
    lines: Sequence[TrendLine],
    atr: Sequence[Decimal | None],
    *,
    parallel_tol: Decimal = DEFAULT_PARALLEL_TOL,
    max_channels: int = DEFAULT_MAX_CHANNELS,
    as_of: int | None = None,
) -> tuple[Channel, ...]:
    """Support/resistance pairs whose slopes agree to ``parallel_tol`` ATR per bar.

    A channel is only as knowable as the later of its two lines: both come from
    :func:`~hunter_indicators.patterns.trendlines.find_lines` at the same cut,
    so each already carries its own ``valid_from_idx`` and no new claim about
    the past is made here.
    """
    cut = len(atr) - 1 if as_of is None else as_of
    scale = atr[cut] if 0 <= cut < len(atr) else None
    if scale is None or scale <= 0:
        return ()
    uppers = [line for line in lines if line.kind is LineKind.RESISTANCE]
    lowers = [line for line in lines if line.kind is LineKind.SUPPORT]
    found: list[Channel] = []
    with localcontext(CONTEXT):
        for upper in uppers:
            for lower in lowers:
                if abs(upper.slope_per_bar - lower.slope_per_bar) > parallel_tol * scale:
                    continue
                width = upper.projected(cut) - lower.projected(cut)
                if width <= 0:
                    continue
                found.append(Channel(upper=upper, lower=lower, at_idx=cut, width_atr=width / scale))
    found.sort(key=lambda ch: (-(ch.upper.score + ch.lower.score), ch.width_atr))
    return tuple(found[:max_channels])
