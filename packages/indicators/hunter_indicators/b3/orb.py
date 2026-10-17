"""H-039 — opening-range breakout on the WIN (``orb_win/1``), as one pure scan.

Frozen in the Fila de Hipóteses (H-039). The opening range is the high and low of the WIN
1-minute bars that **start** in ``[O, O + range_minutes)``, O = 10:00 BRT; at least 5/6 of
them must exist (25 of 30). Then, bar by bar, the first 1-minute bar that **ends** in
``(O + range_minutes, O + last_decision]`` with a close above the range high buys, below
the range low sells — one trade per session, no re-entry, no reversal. Stop on the other
side of the range, no target, time exit at the window's ``exit_at`` (16:30 BRT).

No look-ahead: the decision at a bar uses only bars that ended by that bar's end
(:func:`~hunter_indicators.b3.bars.closed_prefix`); the plan's ``decided_at`` is that end,
and the entry is whatever comes after it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.b3.bars import Bar, closed_prefix, session_bars
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import IntradayWindow, NoPlan, TradePlan
from hunter_indicators.features.definitions import FeatureDefinition

_MIN_RANGE_SHARE = (5, 6)
"""25 of 30 bars, and the same share for the plateau neighbours (13 of 15, 50 of 60)."""


@dataclass(frozen=True, slots=True)
class OrbParams:
    """Frozen with ``version``; a changed number is a new version, never an edit."""

    version: str
    range_minutes: int
    last_decision: timedelta

    def __post_init__(self) -> None:
        if not 0 < self.range_minutes < self.last_decision.total_seconds() / 60:
            raise ValueError("need 0 < range_minutes < last_decision")

    @property
    def min_range_bars(self) -> int:
        num, den = _MIN_RANGE_SHARE
        return math.ceil(self.range_minutes * num / den)


ORB_V1 = OrbParams(version="orb_win/1", range_minutes=30, last_decision=timedelta(hours=4))
"""H-039 as frozen: 30-minute range, last decision bar ending at 14:00 BRT (O + 4 h)."""

OPENING_RANGE_DEFINITION = FeatureDefinition(
    key="win_opening_range",
    version=1,
    category=FeatureCategory.PRICE,
    inputs=("win:bar_1m:high", "win:bar_1m:low"),
    params={"range_minutes": 30, "min_bars": 25, "anchor": "cash_open_10h_brt"},
    description=(
        "high and low of the WIN 1-minute bars starting in the first 30 minutes after the "
        "cash-market open (H-039)"
    ),
)


def opening_range(
    bars: Sequence[Bar], window: IntradayWindow, params: OrbParams
) -> tuple[Decimal, Decimal] | None:
    """(high, low) of the range bars, or ``None`` with fewer than ``min_range_bars``."""
    end = window.open_at + timedelta(minutes=params.range_minutes)
    members = [b for b in closed_prefix(session_bars(bars, window), end)]
    if len(members) < params.min_range_bars:
        return None
    return max(b.high for b in members), min(b.low for b in members)


def _breakout(bar: Bar, high: Decimal, low: Decimal) -> Side | None:
    if bar.close > high:
        return Side.BUY
    if bar.close < low:
        return Side.SELL
    return None


def scan_orb(bars: Sequence[Bar], window: IntradayWindow, params: OrbParams) -> TradePlan | NoPlan:
    """The session's single plan, or why there is none."""
    day = window.trading_date
    rng = opening_range(bars, window, params)
    if rng is None:
        return NoPlan(day, "range_insufficient")
    high, low = rng
    if high == low:
        return NoPlan(day, "range_degenerate")
    first = window.open_at + timedelta(minutes=params.range_minutes)
    last = window.open_at + params.last_decision
    for bar in session_bars(bars, window):
        if not first < bar.end <= last:
            continue
        side = _breakout(bar, high, low)  # the bar that just ended at t, and the closed range
        if side is None:
            continue
        return TradePlan(
            strategy=params.version,
            trading_date=day,
            side=side,
            decided_at=bar.end,
            exit_at=window.exit_at,
            stop_level=low if side is Side.BUY else high,
            stop_fraction=None,
            target_r=None,
            reason=f"1-minute close {bar.close} {'above' if side is Side.BUY else 'below'} "
            f"the {params.range_minutes}-minute opening range",
            supporting_features={
                "range_high": format(high, "f"),
                "range_low": format(low, "f"),
                "breakout_close": format(bar.close, "f"),
            },
            invalidations=("stop at the other side of the opening range",),
        )
    return NoPlan(day, "no_breakout")
