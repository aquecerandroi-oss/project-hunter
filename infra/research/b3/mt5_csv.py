"""Loader for MetaTrader 5 bar exports (Symbols → Bars → Export), the H-039/H-040/H-041 input.

Expected file: a header line ``<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <TICKVOL> <VOL>
<SPREAD>`` separated by tabs, then one bar per line — date ``YYYY.MM.DD``, time
``HH:MM[:SS]``, prices with ``.`` as decimal point, the three volumes/spread as integers,
strictly increasing in time. Encoding follows the byte-order mark (UTF-16 or UTF-8 with
BOM); without one it must be UTF-8. Anything else is refused with the line number.

Time: the file carries the **server's** wall clock, without zone, and the bar time is the
**start** of the period (MQL5 ``MqlRates.time`` = "Period start time"). The offset is
never guessed: the caller declares it (Everton reads it off his terminal),
:func:`detect_server_offset` derives it from the first Ibovespa minute of each session
(10:00 BRT = 13:00 UTC) and :func:`confirm_offset` refuses any disagreement. If the data
cannot show it (pre-opening bars, a DST server, end-of-bar stamps), a written manual
confirmation is the only way through, and it never overrides a contradiction.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from hunter_indicators.b3.bars import Bar

EXPECTED_HEADER = (
    "<DATE>",
    "<TIME>",
    "<OPEN>",
    "<HIGH>",
    "<LOW>",
    "<CLOSE>",
    "<TICKVOL>",
    "<VOL>",
    "<SPREAD>",
)
CASH_OPEN_UTC_MINUTES = 13 * 60
"""10:00 BRT (fixed UTC−3 since 2019) — the first minute of the Ibovespa."""
MIN_MODAL_SHARE = 0.8
"""At least 80 % of sessions must open on the modal minute, or the offset is not visible."""


class Mt5FormatError(ValueError):
    """The file is not an MT5 bar export in the expected shape."""


class OffsetUndetectable(ValueError):
    """The data does not show the server offset unambiguously."""


class TimezoneMismatch(ValueError):
    """The declared server offset disagrees with the data (or nothing confirms it)."""


@dataclass(frozen=True, slots=True)
class RawBar:
    local_start: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    tick_volume: int
    volume: int
    spread: int


def decode_export(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    return raw.decode("utf-8")


def _when(day: str, clock: str, n: int) -> datetime:
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            return datetime.strptime(f"{day} {clock}", fmt)  # noqa: DTZ007 - the server's wall clock, zone applied by to_bars
        except ValueError:
            continue
    raise Mt5FormatError(f"line {n}: date/time {day!r} {clock!r} is not YYYY.MM.DD HH:MM[:SS]")


def _row(fields: list[str], n: int) -> RawBar:
    if len(fields) != len(EXPECTED_HEADER):
        raise Mt5FormatError(f"line {n}: expected 9 fields separated by tabs, got {len(fields)}")
    when = _when(fields[0], fields[1], n)
    try:
        o, h, low, c = (Decimal(x) for x in fields[2:6])
        tick_volume, volume, spread = (int(x) for x in fields[6:9])
    except (InvalidOperation, ValueError) as exc:
        raise Mt5FormatError(f"line {n}: unreadable number ({exc})") from exc
    if not (low <= min(o, c) and max(o, c) <= h and low > 0):
        raise Mt5FormatError(f"line {n}: inconsistent OHLC {o} {h} {low} {c}")
    return RawBar(when, o, h, low, c, tick_volume, volume, spread)


def parse_export(text: str) -> list[RawBar]:
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines or tuple(lines[0].strip().split("\t")) != EXPECTED_HEADER:
        raise Mt5FormatError(f"header must be {' '.join(EXPECTED_HEADER)} separated by tabs")
    bars: list[RawBar] = []
    for n, line in enumerate(lines[1:], start=2):
        bar = _row(line.strip().split("\t"), n)
        if bars and bar.local_start <= bars[-1].local_start:
            raise Mt5FormatError(f"line {n}: time not strictly increasing ({bar.local_start})")
        bars.append(bar)
    if not bars:
        raise Mt5FormatError("no bars after the header")
    return bars


def first_minutes(index_bars: Sequence[RawBar]) -> Counter[str]:
    """How many sessions open at each local ``HH:MM`` (published as a diagnostic)."""
    first: dict[date, datetime] = {}
    for b in index_bars:
        first.setdefault(b.local_start.date(), b.local_start)
    return Counter(t.strftime("%H:%M") for t in first.values())


def detect_server_offset(index_bars: Sequence[RawBar]) -> timedelta:
    """Server offset (local = UTC + offset) from the modal first Ibovespa minute."""
    counts = first_minutes(index_bars)
    ranked = counts.most_common()
    modal, top = ranked[0]
    if len(ranked) > 1 and ranked[1][1] == top:
        raise OffsetUndetectable(f"no single modal first minute: {ranked[:3]}")
    if top / sum(counts.values()) < MIN_MODAL_SHARE:
        raise OffsetUndetectable(f"modal first minute {modal} in only {top} sessions: {ranked[:5]}")
    hh, mm = (int(x) for x in modal.split(":"))
    minutes = hh * 60 + mm - CASH_OPEN_UTC_MINUTES
    if minutes % 60 or not -12 * 60 <= minutes <= 14 * 60:
        raise OffsetUndetectable(
            f"modal first Ibovespa minute {modal} is not 10:00 BRT in any whole-hour zone "
            "(end-of-bar stamps? pre-opening bars?) — confirm the offset by hand"
        )
    return timedelta(minutes=minutes)


def confirm_offset(
    declared: timedelta, detected: timedelta | None, *, manual_reason: str | None
) -> None:
    """Accept ``declared`` only if the data agrees, or the data is silent and a reason is written."""
    if detected is not None:
        if detected != declared:
            raise TimezoneMismatch(f"declared {declared} but the data shows {detected}")
        return
    if not (manual_reason and manual_reason.strip()):
        raise TimezoneMismatch(
            "the data cannot show the offset; a written manual reason is required"
        )


def to_bars(raw: Sequence[RawBar], server_offset: timedelta) -> list[Bar]:
    return [
        Bar(
            start=(b.local_start - server_offset).replace(tzinfo=UTC),
            minutes=1,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
        )
        for b in raw
    ]


def require_tick_grid(bars: Sequence[Bar], tick: Decimal) -> None:
    """Every WIN price on the 5-point grid; otherwise the series is adjusted or not the WIN."""
    for b in bars:
        if any(p % tick for p in (b.open, b.high, b.low, b.close)):
            raise Mt5FormatError(f"price off the {tick}-point tick at {b.start}: adjusted series?")


def load_export(path: Path, server_offset: timedelta) -> list[Bar]:
    return to_bars(parse_export(decode_export(path.read_bytes())), server_offset)
