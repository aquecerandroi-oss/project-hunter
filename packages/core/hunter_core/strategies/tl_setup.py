"""Trend-line primitives, part 5: which event opens a door, and what it evidences.

The four modules below this one (:mod:`~hunter_core.strategies.tl_pivots`,
``tl_lines``, ``tl_events``, ``tl_scan``) are a port of
``hunter_indicators.patterns`` and are kept numerically identical to it by
``test_tl_parity.py``. **This module is not part of that port**: it is the
strategy-facing layer — the policy that turns a scan into a setup a version can
act on, and the evidence that setup must carry into the envelope.

It is a flat sibling rather than a section of ``trendline_breakout_v1.py`` for
one reason only, and it is a budget, not taste: the 350-line file limit
(``infra/scripts/check_file_size.py``). Being a sibling it is *inside* the
``code_ref`` closure of every version that imports it, which is the point — the
digest still covers every line of code that produced a decision. The cost, stated
so nobody discovers it later: a future ``trendline_*_v2`` that needed a different
trigger policy could **not** edit this file, because editing it would re-freeze
``trendline_breakout_v1``. It would add its own module, exactly as the strategy
versions do.

The two policies that live here, and why they are policies and not geometry:

- **a resistance that is not descending, and a support that is not ascending, are
  not this hypothesis.** A rising resistance broken upward is a continuation of
  something already going up; trading it is a different experiment with a
  different prior, so it is excluded by rule rather than by hope;
- **breakout is looked for first.** The two doors are mutually exclusive on the
  same bar, and a market that broke a resistance and bounced off a support in the
  same fifteen minutes is telling us about the break.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Any, Final

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.base import (
    StrategyContext,
    assumed_costs,
    canonical_number,
    param_decimal,
    param_int,
)
from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.envelope import AtrEvidence, FeatureEvidence, SupportingFeatures
from hunter_core.strategies.indicators import Atr, median
from hunter_core.strategies.numeric import CONTEXT
from hunter_core.strategies.tl_events import EventKind, LineEvent
from hunter_core.strategies.tl_lines import LineKind, TrendLine
from hunter_core.strategies.tl_pivots import Pivot, PivotKind
from hunter_core.strategies.tl_scan import Channel, TlParams, TlScan

__all__ = [
    "MODE_BOTH",
    "MODE_BOUNCE",
    "MODE_BREAKOUT",
    "MODE_PARAM",
    "AtrReading",
    "TlSetup",
    "channel_of",
    "decision_reason",
    "decision_envelope",
    "find_trigger",
    "last_pivot_low",
    "pattern_params",
]

_PERCENT: Final = Decimal("100")
_DISPLAY: Final = Decimal("0.01")


def _display(value: Decimal, scale: Decimal = Decimal(1)) -> str:
    """Two decimals under the declared context, for the sentence only.

    ``scale`` is applied **inside** the context: multiplying at the call site
    would let a caller with ``getcontext().prec = 2`` turn 2.1518 % into 2.20 %,
    which is a frozen version reading differently in two processes.
    """
    with localcontext(CONTEXT):
        return f"{(value * scale).quantize(_DISPLAY):f}"


MODE_BREAKOUT: Final = "breakout"
MODE_BOUNCE: Final = "bounce"
MODE_BOTH: Final = "both"

MODE_PARAM: Final[Mapping[str, Any]] = {
    "type": "string",
    "enum": [MODE_BREAKOUT, MODE_BOUNCE, MODE_BOTH],
}
"""Declared **here**, not in ``schema.py``: that module is inside the frozen
closure of ``momentum_v1`` and ``volume_anomaly_v1``, and one line added to it
would re-freeze both live versions and silence the Lab behind a green ``/ready``.
Same reason ``retire_after_break`` travels as an integer 0/1 — a boolean fragment
does not exist yet and cannot be added there."""


@dataclass(frozen=True, slots=True)
class AtrReading:
    """The ATR every threshold of a trend-line decision is measured in.

    One object rather than four parameters passed side by side: the value, the
    percentage, the timeframe and the end of the window are only meaningful
    together, and a signature that lets three of them be reordered is a bug
    waiting for a refactor.
    """

    value: Atr
    percent: Decimal
    timeframe: Timeframe
    window_end: datetime


@dataclass(frozen=True, slots=True)
class TlSetup:
    """A trigger resolved against one scan: the line, the event and the levels."""

    scan: TlScan
    line: TrendLine
    event: LineEvent
    pivot_low: Pivot
    channel: Channel | None
    level: Decimal
    """Where the line sits at the decision bar — the structural invalidation."""

    @property
    def is_breakout(self) -> bool:
        return self.event.kind is EventKind.BREAKOUT


def pattern_params(params: Mapping[str, Any]) -> TlParams:
    """The frozen geometry record, built from a version's own parameters.

    ``rvol_min`` is deliberately left ``None``: the volume gate is a step of the
    *entry rule*, applied by the strategy, so a quiet break is reported as
    ``rvol_low`` — an observed false condition — instead of vanishing from the
    event list as if the market had done nothing.
    """
    return TlParams(
        pivot_k=param_int(params, "pivot_k"),
        min_swing_atr=param_decimal(params, "min_swing_atr"),
        atr_period=param_int(params, "atr_period"),
        min_touches=param_int(params, "min_touches"),
        tolerance_atr=param_decimal(params, "tolerance_atr"),
        break_atr=param_decimal(params, "break_atr"),
        bounce_atr=param_decimal(params, "bounce_atr"),
        retest_bars=param_int(params, "retest_bars"),
        bounce_bars=param_int(params, "bounce_bars"),
        parallel_tol=param_decimal(params, "parallel_tol"),
        angle_bucket_atr=param_decimal(params, "angle_bucket_atr"),
        level_bucket_atr=param_decimal(params, "level_bucket_atr"),
        max_anchors=param_int(params, "max_anchors"),
        max_lines=param_int(params, "max_lines"),
        max_channels=param_int(params, "max_channels"),
        rvol_min=None,
        retire_after_break=bool(param_int(params, "retire_after_break")),
    )


def find_trigger(scan: TlScan, mode: str) -> tuple[LineEvent, TrendLine] | None:
    """The event of **this** bar that opens a door, breakout first."""
    by_id = {line.line_id: line for line in scan.lines}
    doors = (
        (EventKind.BREAKOUT, LineKind.RESISTANCE, True),
        (EventKind.BOUNCE, LineKind.SUPPORT, False),
    )
    for kind, side, descending in doors:
        if mode not in (MODE_BOTH, kind.value):
            continue
        for event in scan.events:
            line = by_id.get(event.line_id)
            if event.index != scan.as_of or event.kind is not kind or line is None:
                continue
            if line.kind is side and ((line.slope_per_bar < 0) is descending):
                return event, line
    return None


def last_pivot_low(pivots: Sequence[Pivot]) -> Pivot | None:
    """The most recent confirmed swing low — where the structural stop goes."""
    for pivot in reversed(pivots):
        if pivot.kind is PivotKind.LOW:
            return pivot
    return None


def channel_of(scan: TlScan, line: TrendLine) -> Channel | None:
    """The best-ranked channel ``line`` is a side of, or ``None``.

    Not "any channel on the chart": the target is the width of *this* line's
    channel, and taking a stranger's width would be a number without a claim.
    """
    for channel in scan.channels:
        if line.line_id in (channel.upper.line_id, channel.lower.line_id):
            return channel
    return None


def decision_reason(
    setup: TlSetup,
    close: Decimal,
    atr_pct: Decimal,
    rvol: Decimal | None,
    channel_target: bool,
) -> str:
    """The human sentence, in Portuguese, naming every number that decided.

    Two decimals here and only here: the envelope keeps the full precision, and a
    rounded number must never reach a comparison (``notes-S1.md``).
    """
    line, event = setup.line, setup.event
    volume = f", volume relativo {_display(rvol)}x" if setup.is_breakout and rvol else ""
    width = (
        f", alvo pela largura do canal ({_display(setup.channel.width_atr)} ATR)"
        if channel_target and setup.channel is not None
        else ""
    )
    return (
        f"Linha de tendencia 15m: {event.kind.value} de uma {line.kind.value} com "
        f"{line.touches} toques e {line.violations} violacoes (inclinacao "
        f"{canonical_number(line.slope_per_bar)}/barra, linha em "
        f"{canonical_number(setup.level)}); fechamento {canonical_number(close)} a "
        f"{_display(event.distance_atr)} ATR da linha{volume}{width}, "
        f"ATR% {_display(atr_pct, _PERCENT)}%"
    )


def _line_features(setup: TlSetup) -> tuple[FeatureEvidence, ...]:
    """The drawing, field by field, for ``agent_signals.supporting_features``.

    ``line_id`` is what lets two signals that fired on the **same line** be joined
    months later; ``pattern_params`` is the whole geometry record, because a line
    drawn with other thresholds is a different claim about the same tape; the
    three ``pattern_*`` counts are what the first replay needs to report how much
    geometry a bar actually saw.
    """
    line, event, scan = setup.line, setup.event, setup.scan
    plain: tuple[tuple[str, Decimal | int | str], ...] = (
        ("line_kind", line.kind.value),
        ("line_id", line.line_id),
        ("line_slope_per_bar", line.slope_per_bar),
        ("line_touches", line.touches),
        ("line_violations", line.violations),
        ("line_first_idx", line.first_idx),
        ("line_last_idx", line.last_idx),
        ("line_valid_from_idx", line.valid_from_idx),
        ("line_price_at_decision", setup.level),
        ("event_kind", event.kind.value),
        ("event_distance_atr", event.distance_atr),
        ("pivot_low_price", setup.pivot_low.price),
        ("pivot_low_idx", setup.pivot_low.index),
        ("pattern_bars", scan.as_of + 1),
        ("pattern_pivots", len(scan.pivots)),
        ("pattern_lines", len(scan.lines)),
        ("pattern_retired_lines", len(scan.retired)),
        ("pattern_params", canonical_json(setup.scan.params.as_wire()).decode("utf-8")),
    )
    channel = FeatureEvidence(
        name="channel_width_atr",
        value=None if setup.channel is None else setup.channel.width_atr,
        available=setup.channel is not None,
        unavailable_reason=None if setup.channel is not None else "no_channel",
    )
    return (*(FeatureEvidence(name=name, value=value) for name, value in plain), channel)


def decision_envelope(
    ctx: StrategyContext,
    params: Mapping[str, Any],
    bars: Sequence[Bar],
    reading: AtrReading,
    rvol: Decimal | None,
    setup: TlSetup,
    *,
    key: str,
    version: str,
    timeframe: Timeframe,
) -> SupportingFeatures:
    """Everything the decision used, so it can be re-checked once the 1-minute
    candles have left retention (SHADOW-LAB.md §7)."""
    atr, atr_pct = reading.value, reading.percent
    rvol_window = param_int(params, "rvol_window")
    volume_median = median([bar.volume for bar in bars[-rvol_window - 1 : -1]])
    last = bars[-1]
    return SupportingFeatures(
        observation_ts=ctx.source_bar_close,
        timeframe=timeframe.value,
        strategy_key=key,
        strategy_version=version,
        features=(
            FeatureEvidence(name="open_15m", value=last.open, source_ts=last.open_time),
            FeatureEvidence(name="high_15m", value=last.high),
            FeatureEvidence(name="low_15m", value=last.low),
            FeatureEvidence(name="volume_15m", value=last.volume),
            FeatureEvidence(name="close_15m", value=last.close, source_ts=last.close_time),
            FeatureEvidence(
                name="relative_volume_15m",
                value=rvol,
                available=rvol is not None,
                unavailable_reason=None if rvol is not None else "rvol_unavailable",
                window=rvol_window,
            ),
            FeatureEvidence(name="volume_median_15m", value=volume_median, window=rvol_window),
            FeatureEvidence(
                name="atr_pct_15m", value=atr_pct, window=param_int(params, "atr_bars")
            ),
            *_line_features(setup),
        ),
        atr=AtrEvidence(
            method=atr.method,
            origin=atr.origin,
            timeframe=reading.timeframe.value,
            period=atr.period,
            value=atr.value,
            percent=atr_pct,
            seed=atr.seed,
            seed_anchor=atr.seed_anchor,
            bars_used=atr.bars_used,
            window_start=atr.window_start,
            window_end=reading.window_end,
        ),
        assumed_costs=assumed_costs(params),
        eligible=ctx.eligible,
        eligibility_reason=ctx.eligibility_reason,
    )
