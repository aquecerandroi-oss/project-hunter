"""What the daily close renders from — the rows already folded (T4.15). Pure
dataclasses plus the two formatting helpers every renderer shares."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from meme_close_lessons import ClosedBet, Lesson, TopOut
from meme_close_stats import fmt
from meme_diary_render import SAO_PAULO, WalletTradeLine


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the gate could see in the day, and what the loop wrote per tick."""

    rows: int
    with_progress: int
    with_tape: int
    with_line: int
    with_hype: int
    mints: int
    minutes: int
    ticks: int
    first_tick: datetime | None
    last_tick: datetime | None
    gaps: int
    """Pairs of consecutive ticks more than 3 minutes apart."""
    rows_evaluated: int
    refusals: Mapping[str, Mapping[str, int]]


@dataclass(frozen=True, slots=True)
class OperatorDay:
    proposed: int
    approved: int
    rejected: int
    expired: int
    filled: int
    unfilled: int
    manual: int
    latency_s: Sequence[int]
    r_approved: Sequence[Decimal]


@dataclass(frozen=True, slots=True)
class ExpAllTime:
    """One active rule set, all its closed bets up to the day's end."""

    rule_set: str
    exp_ref: str | None
    kind: str
    n: int
    days: int
    mean: Decimal | None
    ci95: tuple[Decimal, Decimal] | None
    total: Decimal
    target_share: Decimal | None
    dead_or_time_share: Decimal | None
    best_r: Decimal | None
    without_best: Decimal | None
    today_n: int
    today_total: Decimal
    today_reasons: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class CloseInputs:
    day: date
    generated_at: datetime
    bets: Sequence[ClosedBet]
    lessons: Sequence[Lesson]
    top_out: Sequence[TopOut]
    coverage: Coverage
    operator: OperatorDay
    reals: Sequence[WalletTradeLine]
    all_time: Sequence[ExpAllTime]
    predictions: Mapping[str, str | None]
    """``exp_ref -> the frozen prediction quoted from its page`` (``None`` = not found)."""


def brt(at: datetime | None, pattern: str = "%H:%M:%S") -> str:
    return "—" if at is None else at.astimezone(SAO_PAULO).strftime(pattern)


def pct(part: int, whole: int) -> str:
    return "—" if whole <= 0 else f"{part * 100 / whole:.0f} %"


def ci_pair(pair: tuple[Decimal, Decimal] | None, *, missing: str) -> str:
    return missing if pair is None else f"[{fmt(pair[0])}, {fmt(pair[1])}]"
