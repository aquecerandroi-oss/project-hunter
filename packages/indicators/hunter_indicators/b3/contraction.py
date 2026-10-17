"""H-041 — breakout after range contraction on the WIN (``contraction_win/1``), one pure scan.

Frozen in the Fila de Hipóteses (H-041), the formalisable piece of KB-0053 named for what
it measures (a range-contraction ratio, **not** "VCP"). 5-minute bars aligned on O = 10:00
BRT. For decision bar j the **window** is the k bars j−k … j−1 (it ends at t−1: the
breakout bar is outside), all non-empty; ``A_j`` = mean of (high − low) ÷ close × 10 000
over the window (bp, no price level, so the WIN roll cannot move it). The baseline ``B_j``
is the median of ``A_j`` (same j, same k) over the 20 previous eligible sessions, needing
≥ 15 values and never reaching further back. ``c_j = A_j ÷ B_j``; with ``c_j ≤ θ`` a
close of bar j above the window high buys, below the window low sells; first one wins,
one trade per session. Stop on the other side of the window, target ± r·R from the
entry fill, time exit at the window's ``exit_at``.

No look-ahead: at bar j only bars that ended by the end of bar j are read; past sessions
enter only through their finished profiles, passed in by the caller.

Exact arithmetic: ``A``, ``B`` and ``c`` are :class:`~fractions.Fraction` built from the
``Decimal`` prices, so ``c ≤ θ`` is decided exactly — no rounding, no tolerance band.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from fractions import Fraction

from hunter_core.domain.enums import FeatureCategory
from hunter_indicators.b3.bars import Bar, aggregate, bucket, closed_prefix, session_bars
from hunter_indicators.b3.contract import Side
from hunter_indicators.b3.intraday_plan import IntradayWindow, NoPlan, TradePlan
from hunter_indicators.features.definitions import FeatureDefinition

_BP = Fraction(10000)


@dataclass(frozen=True, slots=True)
class ContractionParams:
    """Frozen with ``version``; a changed number is a new version, never an edit."""

    version: str
    bar_minutes: int
    window_bars: int
    theta: Decimal
    target_r: Decimal
    baseline_sessions: int
    baseline_min: int
    last_decision: timedelta

    def __post_init__(self) -> None:
        if self.bar_minutes < 1 or self.window_bars < 1:
            raise ValueError("bar_minutes and window_bars must be positive")
        if self.theta <= 0 or self.target_r <= 0:
            raise ValueError("theta and target_r must be positive")
        if not 0 < self.baseline_min <= self.baseline_sessions:
            raise ValueError("need 0 < baseline_min <= baseline_sessions")

    def positions(self) -> range:
        """Decision bars j: k ≤ j and bar j ends by ``last_decision``."""
        last = int(self.last_decision / timedelta(minutes=self.bar_minutes)) - 1
        return range(self.window_bars, last + 1)


CONTRACTION_V1 = ContractionParams(
    version="contraction_win/1",
    bar_minutes=5,
    window_bars=6,
    theta=Decimal("0.6"),
    target_r=Decimal("2"),
    baseline_sessions=20,
    baseline_min=15,
    last_decision=timedelta(hours=4),
)
"""H-041 as frozen: 6 × 5-minute window, θ = 0.6, target 2 R, baseline 20 sessions (≥ 15)."""

CONTRACTION_DEFINITION = FeatureDefinition(
    key="win_range_contraction_5m",
    version=1,
    category=FeatureCategory.VOLATILITY,
    inputs=("win:bar_1m:high", "win:bar_1m:low", "win:bar_1m:close"),
    params={"bar_minutes": 5, "window_bars": 6, "baseline_sessions": 20, "baseline_min": 15},
    description=(
        "mean relative range (bp) of the six 5-minute WIN bars before the decision bar over "
        "its median at the same position in the 20 previous sessions (H-041)"
    ),
)


def _amplitude(window: Sequence[Bar | None]) -> Fraction | None:
    if not window or any(b is None for b in window):
        return None
    total = sum(
        (Fraction(b.high - b.low) / Fraction(b.close) * _BP for b in window if b is not None),
        Fraction(0),
    )
    return total / len(window)


def _median(values: Sequence[Fraction]) -> Fraction:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def as_decimal(value: Fraction, places: int = 12) -> Decimal:
    """A display/storage rendering of an exact ratio (never used to decide)."""
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal(1).scaleb(-places)
    )


def amplitude_profile(
    bars: Sequence[Bar], window: IntradayWindow, params: ContractionParams
) -> dict[int, Fraction]:
    """``A_j`` of a **finished** session at every decision position where it exists."""
    end = window.open_at + params.last_decision
    b5 = aggregate(
        session_bars(bars, window), anchor=window.open_at, minutes=params.bar_minutes, until=end
    )
    out: dict[int, Fraction] = {}
    for j in params.positions():
        a = _amplitude(b5[j - params.window_bars : j])
        if a is not None:
            out[j] = a
    return out


def baseline(
    profiles: Sequence[Mapping[int, Fraction]], j: int, params: ContractionParams
) -> Fraction | None:
    """Median of ``A_j`` over the last ``baseline_sessions`` profiles, or ``None`` if too few."""
    values = [p[j] for p in profiles[-params.baseline_sessions :] if j in p]
    if len(values) < params.baseline_min:
        return None
    return _median(values)


def _breakout(bar: Bar, window: Sequence[Bar]) -> tuple[Side, Decimal] | None:
    high = max(b.high for b in window)
    low = min(b.low for b in window)
    if bar.close > high:
        return Side.BUY, low
    if bar.close < low:
        return Side.SELL, high
    return None


@dataclass(frozen=True, slots=True)
class ContractionStep:
    """One measurable decision bar: the window, the ratio and the bar that may break out."""

    j: int
    decided_at: datetime
    amplitude: Fraction
    base: Fraction
    ratio: Fraction
    decision_bar: Bar
    window: tuple[Bar, ...]


def contraction_steps(
    bars: Sequence[Bar],
    window: IntradayWindow,
    previous_profiles: Sequence[Mapping[int, Fraction]],
    params: ContractionParams,
) -> Iterator[ContractionStep]:
    """Every measurable decision bar, in time order, each built only from bars ended by its end."""
    inside = session_bars(bars, window)
    step = timedelta(minutes=params.bar_minutes)
    b5: list[Bar | None] = []
    for j in params.positions():
        t = window.open_at + step * (j + 1)
        seen = closed_prefix(inside, t)
        while len(b5) <= j:  # bucket i ends by t, so it only reads bars that ended by t
            b5.append(
                bucket(seen, start=window.open_at + step * len(b5), minutes=params.bar_minutes)
            )
        members = b5[j - params.window_bars : j]
        amp = _amplitude(members)
        base = baseline(previous_profiles, j, params)
        decision_bar = b5[j]
        if amp is None or base is None or amp == 0 or base == 0 or decision_bar is None:
            continue
        ratio = amp / base
        full = tuple(b for b in members if b is not None)
        yield ContractionStep(j, t, amp, base, ratio, decision_bar, full)


def scan_contraction(
    bars: Sequence[Bar],
    window: IntradayWindow,
    previous_profiles: Sequence[Mapping[int, Fraction]],
    params: ContractionParams,
) -> TradePlan | NoPlan:
    """The session's single plan, or why there is none (``no_baseline`` / ``no_signal``)."""
    measurable = False
    for s in contraction_steps(bars, window, previous_profiles, params):
        measurable = True
        if s.ratio > Fraction(params.theta):
            continue
        hit = _breakout(s.decision_bar, s.window)
        if hit is None:
            continue
        side, stop = hit
        return TradePlan(
            strategy=params.version,
            trading_date=window.trading_date,
            side=side,
            decided_at=s.decided_at,
            exit_at=window.exit_at,
            stop_level=stop,
            stop_fraction=None,
            target_r=params.target_r,
            reason=f"range contraction {as_decimal(s.ratio, 4)} <= {params.theta} and a 5-minute close "
            f"{'above' if side is Side.BUY else 'below'} the {params.window_bars}-bar window",
            supporting_features={
                "amplitude_bp": format(as_decimal(s.amplitude), "f"),
                "baseline_bp": format(as_decimal(s.base), "f"),
                "contraction": format(as_decimal(s.ratio), "f"),
                "window_high": format(max(b.high for b in s.window), "f"),
                "window_low": format(min(b.low for b in s.window), "f"),
            },
            invalidations=("stop at the other side of the contraction window",),
        )
    return NoPlan(window.trading_date, "no_signal" if measurable else "no_baseline")
