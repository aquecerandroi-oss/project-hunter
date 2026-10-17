"""H-040 — 15-minute reversal on the WIN (``reversal15_win/1``), as one pure scan.

Frozen in the Fila de Hipóteses (H-040), from Kitron & Wengrowicz (2026) via KB-0082: bet
against the sign of the last closed 15-minute bar, ``sign(close − open)``. Bars of Δ
minutes are aligned on O = 10:00 BRT (open = first 1-minute bar's open, close = last
one's close; partial buckets accepted, empty ones decide nothing). At the end of every Δ
bar ending in ``[O + Δ, exit − Δ]``: up bar → sell 1 WIN, down bar → buy, doji → nothing.
Entry right after the decision bar, time exit Δ later, catastrophic stop 0.5 % of the
entry fill rounded by side (H-038's ``stop_level``), no target. At most
``session_minutes / Δ − 1`` trades per session (25 for Δ = 15).

No look-ahead: the decision bar is built only at its end ``t``, from the 1-minute bars
that ended by ``t`` (:func:`~hunter_indicators.b3.bars.closed_prefix`).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.b3.bars import Bar, bucket, closed_prefix, session_bars
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import IntradayWindow, TradePlan
from hunter_indicators.features.definitions import FeatureDefinition

SESSION_MINUTES = 390
"""10:00 → 16:30 BRT, the frozen window of the family (contract item d)."""


@dataclass(frozen=True, slots=True)
class Reversal15Params:
    """Frozen with ``version``; a changed number is a new version, never an edit."""

    version: str
    bar_minutes: int
    stop_fraction: Decimal

    def __post_init__(self) -> None:
        if self.bar_minutes < 1 or SESSION_MINUTES % self.bar_minutes:
            raise ValueError("bar_minutes must divide the 390-minute window")
        if not Decimal(0) < self.stop_fraction < Decimal(1):
            raise ValueError("stop_fraction must be in (0, 1)")

    @property
    def max_trades(self) -> int:
        return SESSION_MINUTES // self.bar_minutes - 1


REVERSAL15_V1 = Reversal15Params(
    version="reversal15_win/1", bar_minutes=15, stop_fraction=Decimal("0.005")
)
"""H-040 as frozen: 15-minute bars, 0.5 % catastrophic stop."""

BAR_SIGN_DEFINITION = FeatureDefinition(
    key="win_bar_sign_15m",
    version=1,
    category=FeatureCategory.MOMENTUM,
    inputs=("win:bar_1m:open", "win:bar_1m:close"),
    params={"bar_minutes": 15, "anchor": "cash_open_10h_brt"},
    description="sign(close − open) of the last closed 15-minute WIN bar aligned on 10:00 BRT (H-040)",
)


def _contrarian(bar: Bar) -> Side | None:
    if bar.close > bar.open:
        return Side.SELL
    if bar.close < bar.open:
        return Side.BUY
    return None


def reversal_steps(
    bars: Sequence[Bar], window: IntradayWindow, params: Reversal15Params
) -> Iterator[tuple[datetime, Bar | None, Side | None]]:
    """Every decision instant of the grid with its bar (``None`` = empty) and side (``None`` = doji)."""
    step = timedelta(minutes=params.bar_minutes)
    inside = session_bars(bars, window)
    t = window.open_at + step
    while t <= window.exit_at - step:
        last = bucket(closed_prefix(inside, t), start=t - step, minutes=params.bar_minutes)
        yield t, last, None if last is None else _contrarian(last)
        t += step


def scan_reversal(
    bars: Sequence[Bar], window: IntradayWindow, params: Reversal15Params
) -> list[TradePlan]:
    """Every plan of the session, in time order."""
    step = timedelta(minutes=params.bar_minutes)
    plans: list[TradePlan] = []
    for t, last, side in reversal_steps(bars, window, params):
        if last is None or side is None:
            continue
        plans.append(
            TradePlan(
                strategy=params.version,
                trading_date=window.trading_date,
                side=side,
                decided_at=t,
                exit_at=t + step,
                stop_level=None,
                stop_fraction=params.stop_fraction,
                target_r=None,
                reason=f"{params.bar_minutes}-minute bar closed "
                f"{'up' if side is Side.SELL else 'down'}; bet on reversal",
                supporting_features={
                    "bar_open": format(last.open, "f"),
                    "bar_close": format(last.close, "f"),
                },
                invalidations=("catastrophic stop 0.5 % of the entry fill",),
            )
        )
    return plans
