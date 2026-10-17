"""N_hist, its funnel and the 80/20 cut of the WIN family (contract items d and e of H-039).

Only dates and bar **timestamps** decide who enters — never a price, never anything after a
decision instant. O = 10:00 BRT and the time exit 16:30 BRT are the frozen window (O is an
assumption checked by compatibility, not proven). Funnel, in the frozen order, over the
B3 calendar sessions between the first and the last WIN date of the export:
Ash Wednesday → WIN expiry day → grid incompatible (the Ibovespa **and** the WIN both
without a bar starting in [O, O+5 min), as the frozen text reads) → no data (no WIN or
no Ibovespa bar in [O, 16:30)) → N_hist. Primary = the first ⌊0.8·N_hist⌋ sessions by date.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from hunter_indicators.b3.bars import Bar
from hunter_indicators.b3.calendar_2026 import BRT
from hunter_indicators.b3.calendar_history import (
    COVERAGE_END,
    COVERAGE_START,
    SHORTENED_DAYS,
    is_win_expiry,
    sessions_between,
)
from hunter_indicators.b3.intraday_plan import IntradayWindow

OPEN_LOCAL = time(10, 0)
EXIT_LOCAL = time(16, 30)
GRID_TOLERANCE = timedelta(minutes=5)
PRIMARY_SHARE = (4, 5)


@dataclass(frozen=True, slots=True)
class SessionData:
    window: IntradayWindow
    win: list[Bar]
    ibov: list[Bar]


@dataclass(frozen=True, slots=True)
class Population:
    sessions: list[SessionData]
    funnel: OrderedDict[str, int]
    before_coverage: int
    primary: list[SessionData] = field(default_factory=list[SessionData])
    holdout: list[SessionData] = field(default_factory=list[SessionData])
    excluded: list[tuple[date, str]] = field(default_factory=list[tuple[date, str]])
    """Every calendar session left out, with its funnel step — the frozen exclusion list."""


def primary_size(n_hist: int) -> int:
    num, den = PRIMARY_SHARE
    return n_hist * num // den


def brt_date(bar: Bar) -> date:
    return bar.start.astimezone(BRT).date()


def _group(bars: Sequence[Bar]) -> dict[date, list[Bar]]:
    out: dict[date, list[Bar]] = {}
    for b in bars:
        out.setdefault(brt_date(b), []).append(b)
    return out


def window_for(day: date) -> IntradayWindow:
    return IntradayWindow(
        trading_date=day,
        open_at=datetime.combine(day, OPEN_LOCAL, tzinfo=BRT),
        exit_at=datetime.combine(day, EXIT_LOCAL, tzinfo=BRT),
    )


def _starts_at_open(bars: Sequence[Bar], window: IntradayWindow) -> bool:
    return any(window.open_at <= b.start < window.open_at + GRID_TOLERANCE for b in bars)


def _has_data(bars: Sequence[Bar], window: IntradayWindow) -> bool:
    return any(window.open_at <= b.start < window.exit_at for b in bars)


def build_population(win: Sequence[Bar], ibov: Sequence[Bar]) -> Population:
    if not win:
        raise ValueError("the WIN export is empty")
    win_by_day, ibov_by_day = _group(win), _group(ibov)
    first, last = min(win_by_day), max(win_by_day)
    before = sum(1 for d in win_by_day if d < COVERAGE_START)
    if last > COVERAGE_END:
        raise ValueError(
            f"WIN data after the calendar coverage ({last}); extend calendar_history first"
        )
    days = sessions_between(max(first, COVERAGE_START), last) if last >= COVERAGE_START else []
    funnel: OrderedDict[str, int] = OrderedDict(
        (k, 0)
        for k in (
            "calendar_sessions",
            "ash_wednesday",
            "win_expiry",
            "grid_incompatible",
            "no_data",
        )
    )
    funnel["calendar_sessions"] = len(days)
    kept: list[SessionData] = []
    excluded: list[tuple[date, str]] = []
    for day in days:
        window = window_for(day)
        w, i = win_by_day.get(day, []), ibov_by_day.get(day, [])
        if day in SHORTENED_DAYS:
            step = "ash_wednesday"
        elif is_win_expiry(day):
            step = "win_expiry"
        elif not (_starts_at_open(i, window) or _starts_at_open(w, window)):
            step = "grid_incompatible"
        elif not (_has_data(w, window) and _has_data(i, window)):
            # frozen definition (contract item d): availability up to 16:30 — a selection by
            # timestamps after the decision instants, declared in the emenda, never by price
            step = "no_data"
        else:
            kept.append(SessionData(window, w, i))
            continue
        funnel[step] += 1
        excluded.append((day, step))
    funnel["n_hist"] = len(kept)
    cut = primary_size(len(kept))
    return Population(kept, funnel, before, kept[:cut], kept[cut:], excluded)


def overnight_gaps(sessions: Sequence[SessionData]) -> list[tuple[date, Decimal]]:
    """First WIN open of each session over the previous kept session's last close, in bp."""
    out: list[tuple[date, Decimal]] = []
    for prev, cur in zip(sessions, sessions[1:], strict=False):
        if prev.win and cur.win:
            gap = (cur.win[0].open / prev.win[-1].close - 1) * Decimal(10000)
            out.append((cur.window.trading_date, gap.quantize(Decimal("0.01"))))
    return out
