"""OHLC 1-minute trade simulator of the WIN family (contract items f and g of H-039).

An **approximation**, labelled as such — never an observed execution. Entry at the open of
the first bar starting in [decided_at, +5 min]; 1 tick of slippage per leg by side (every
buy +tick, every sell −tick, every leg); B3 fee per leg. Bars checked: the entry bar and
every later bar that starts before the exit instant. Precedence in each bar: (1) a later
bar opening beyond the stop exits at that open; (2) a touch of the stop exits at the stop;
(3) a touch of the target exits at the target (no price improvement); stop and target in
one bar → stop; (4) time exit at the open of the first bar starting in [exit_at, +5 min].
A stop on the wrong side of the fill (equality included) exits at the entry bar's raw open.

Censoring is decided by timestamps only, identically for both sides: a missing 1-minute
bar in [entry bar, exit_at) or no exit bar within 5 minutes censors the trade even if the
stop was hit before the hole. Its **stress** value (an assumed scenario, not a bound) exits
at the worse of the stop and the most adverse observed price before the exit instant.
``flip`` simulates the opposite side with the **rule side's** stop mirrored around the raw
entry open (also for a fraction stop, computed from the rule side's fill) and the target
from that mirrored geometry (the permutation's counterfactual).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.calendar_2026 import WIN_SPEC
from hunter_indicators.b3.contract import InstrumentSpec, Side, stop_level
from hunter_indicators.b3.intraday_plan import TradePlan

TOLERANCE = timedelta(minutes=5)
_MINUTE = timedelta(minutes=1)
_BP = Decimal(10000)


@dataclass(frozen=True, slots=True)
class Costs:
    fee_points_per_leg: Decimal
    slippage_ticks: int


WIN_COSTS = Costs(fee_points_per_leg=Decimal("1.28"), slippage_ticks=1)
"""B3 R$ 0,256 per leg per contract at R$ 0,20/pt (table read 17/10/2026); brokerage 0 (RLP)."""


class Status(StrEnum):
    OK = "ok"
    NO_ENTRY = "no_entry_bar"
    CENSORED = "censored"


class ExitReason(StrEnum):
    STOP_AT_ENTRY = "stop_at_entry"
    STOP_GAP = "stop_gap"
    STOP = "stop"
    TARGET = "target"
    TIME = "time"


@dataclass(frozen=True, slots=True)
class Outcome:
    plan: TradePlan
    side: Side
    status: Status
    entry_time: datetime | None = None
    raw_entry: Decimal | None = None
    entry_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    exit_price: Decimal | None = None
    exit_reason: ExitReason | None = None
    net_points: Decimal | None = None
    net_bp: Decimal | None = None
    gross_raw_points: Decimal | None = None
    stress_bp: Decimal | None = None


def _round_away(raw: Decimal, side: Side, tick: Decimal) -> Decimal:
    rounding = ROUND_CEILING if side is Side.BUY else ROUND_FLOOR
    return (raw / tick).to_integral_value(rounding=rounding) * tick


def _complete(bars: Sequence[Bar], start: datetime, end: datetime) -> bool:
    starts = {b.start for b in bars}
    t = start
    while t < end:
        if t not in starts:
            return False
        t += _MINUTE
    return True


def _walk(
    held: Sequence[Bar], side: Side, stop: Decimal, target: Decimal | None
) -> tuple[Decimal, ExitReason] | None:
    """(exit level before slippage, reason), or ``None`` if nothing was hit."""
    buy = side is Side.BUY
    for i, bar in enumerate(held):
        if i and (bar.open <= stop if buy else bar.open >= stop):
            return bar.open, ExitReason.STOP_GAP
        if bar.low <= stop if buy else bar.high >= stop:
            return stop, ExitReason.STOP
        if target is not None and (bar.high >= target if buy else bar.low <= target):
            return target, ExitReason.TARGET
    return None


def simulate(
    plan: TradePlan,
    bars: Sequence[Bar],
    spec: InstrumentSpec = WIN_SPEC,
    costs: Costs = WIN_COSTS,
    *,
    flip: bool = False,
) -> Outcome:
    side = (Side.SELL if plan.side is Side.BUY else Side.BUY) if flip else plan.side
    entry_bar = next((x for x in bars if x.start >= plan.decided_at), None)
    if entry_bar is None or entry_bar.start > plan.decided_at + TOLERANCE:
        return Outcome(plan, side, Status.NO_ENTRY)
    sign = Decimal(1) if side is Side.BUY else Decimal(-1)
    slip = spec.tick_size * costs.slippage_ticks
    raw_open = entry_bar.open
    entry = raw_open + sign * slip
    if plan.stop_level is not None:
        rule_stop = plan.stop_level
    else:
        assert plan.stop_fraction is not None
        rule_sign = Decimal(1) if plan.side is Side.BUY else Decimal(-1)
        rule_stop = stop_level(raw_open + rule_sign * slip, plan.side, plan.stop_fraction, spec)
    # the counterfactual side keeps the rule's geometry, mirrored around the raw open
    stop = 2 * raw_open - rule_stop if flip else rule_stop
    held = [x for x in bars if entry_bar.start <= x.start < plan.exit_at]
    exit_bar = next((x for x in bars if x.start >= plan.exit_at), None)
    censored = (
        exit_bar is None
        or exit_bar.start > plan.exit_at + TOLERANCE
        or not _complete(bars, entry_bar.start, plan.exit_at)
    )
    fee = 2 * costs.fee_points_per_leg
    target: Decimal | None = None
    if sign * (entry - stop) <= 0:
        found: tuple[Decimal, ExitReason] | None = (raw_open, ExitReason.STOP_AT_ENTRY)
    else:
        if plan.target_r is not None:
            risk = abs(entry - stop)
            target = _round_away(entry + sign * plan.target_r * risk, side, spec.tick_size)
        found = _walk(held, side, stop, target)
    if found is None and exit_bar is not None and not censored:
        found = (exit_bar.open, ExitReason.TIME)
    lows, highs = [x.low for x in held] or [stop], [x.high for x in held] or [stop]
    worst_seen = min(lows) if side is Side.BUY else max(highs)
    worst = min(stop, worst_seen) if side is Side.BUY else max(stop, worst_seen)
    stress_points = sign * ((worst - sign * slip) - entry) - fee
    censored_outcome = Outcome(
        plan,
        side,
        Status.CENSORED,
        entry_time=entry_bar.start,
        raw_entry=raw_open,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        stress_bp=stress_points / entry * _BP,
    )
    if censored or found is None:
        return censored_outcome
    level, reason = found
    exit_price = level - sign * slip
    net = sign * (exit_price - entry) - fee
    return replace(
        censored_outcome,
        status=Status.OK,
        exit_price=exit_price,
        exit_reason=reason,
        net_points=net,
        net_bp=net / entry * _BP,
        gross_raw_points=sign * (level - raw_open),
        stress_bp=net / entry * _BP,
    )
