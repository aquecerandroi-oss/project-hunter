"""T4.25 — what one closed meme bet is, and where its lines go.

The model of the JSONL that ``meme_render_bets.py export`` writes and that
``render``/``notes`` read back: no database, no matplotlib, ``Decimal`` all the
way through (``float`` exists only in ``meme_render_bets_draw.py``, at the
pixels). Sibling of ``meme_render_bets_query.py`` by file budget (350 lines,
``infra/scripts/check_file_size.py``), not by taste.

The geometry here is the screen's, digit for digit
(``apps/web/components/meme/meme-lines.ts``): the support is
``support_line_sol`` at ``end_time`` projected by ``support_line_slope``
(SOL/min) from the edge of its own 15-minute window, and the 15-minute high is
``high_15m_sol`` of the **previous** minute — the level ``breakout_15m``
compares against, which by contract excludes the current minute. Nothing here
draws a line the fold did not compute, and the minute read is the one **at the
entry** (:func:`minute_at`), never a later one.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from meme_diary_render import SAO_PAULO

PAD = timedelta(minutes=10)
"""How much tape travels around a bet. Ten minutes before the entry shows the
window the line was fitted over; ten after the exit shows what the exit gave up."""

LINE_WINDOW = timedelta(minutes=15)
"""W of the contract (T4.10): the window the lows, the high and the slope are
measured over, repeated here so the drawing cannot drift from the screen."""


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def jsonable(value: Any) -> Any:
    """``Decimal`` -> exact string, ``datetime`` -> ISO; never a float.

    The one place a number crosses into the JSONL, so the round trip
    ``NUMERIC(28,10)`` -> file -> ``Decimal`` loses nothing.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        return {str(k): jsonable(v) for k, v in mapping.items()}
    if isinstance(value, list | tuple):
        items = cast("list[Any] | tuple[Any, ...]", value)
        return [jsonable(v) for v in items]
    return value


@dataclass(frozen=True, slots=True)
class Point:
    """One instant of one series: 15 s (``as_of``) or 1 min (``end_time``)."""

    at: datetime
    mcap_sol: Decimal | None


@dataclass(frozen=True, slots=True)
class Snapshot:
    at: datetime
    source: str
    mcap_sol: Decimal | None
    complete: bool


@dataclass(frozen=True, slots=True)
class Minute:
    """One ``meme_features_1m`` row, with the line columns of ``meme_features_v3``."""

    end_time: datetime
    mcap_sol: Decimal | None
    support_line_sol: Decimal | None
    support_line_slope: Decimal | None
    high_15m_sol: Decimal | None
    low_15m_sol: Decimal | None
    breakout_15m: bool | None
    higher_lows: bool | None
    line_reason: str | None


@dataclass(frozen=True, slots=True)
class Segment:
    """A straight line in data space — instants on x, mcap in SOL on y."""

    x1: datetime
    y1: Decimal
    x2: datetime
    y2: Decimal


@dataclass(frozen=True, slots=True)
class Bet:
    """One closed paper bet and the tape around it, as the JSONL carries them."""

    bet_id: str
    day: date
    rule_set: str
    kind: str
    exp_ref: str | None
    code_ref: str
    rule_set_params: Mapping[str, Any]
    mint: str
    symbol: str | None
    leg: str
    outcome_quality: str
    outcome_quality_reason: str | None
    entry_at: datetime
    exit_at: datetime
    entry_mcap_sol: Decimal | None
    exit_mcap_sol: Decimal | None
    exit_reason: str
    r_multiple: Decimal
    pnl_sol: Decimal | None
    initial_risk_sol: Decimal | None
    high_water_x: Decimal | None
    creator_sold_seen_at: datetime | None
    creator_sold_fraction: Decimal | None
    params: Mapping[str, Any]
    manual_plan: str | None
    fast: tuple[Point, ...]
    minutes: tuple[Minute, ...]
    snapshots: tuple[Snapshot, ...]

    @property
    def entry_brt(self) -> datetime:
        return self.entry_at.astimezone(SAO_PAULO)

    @property
    def exit_brt(self) -> datetime:
        return self.exit_at.astimezone(SAO_PAULO)

    @property
    def ticker(self) -> str:
        """The token's symbol when it is known, else the head of the mint."""
        raw = "".join(c for c in (self.symbol or "") if c.isalnum())[:12]
        return raw.upper() if raw else self.mint[:6]

    @property
    def r_text(self) -> str:
        """R with sign, trailing zeros trimmed but never below two decimals.

        ``-1`` on a page of ``-0.0403`` reads like a rounding; ``-1.00`` reads
        like the whole stake, which is what it is.
        """
        text = f"{self.r_multiple:+.4f}"
        while text.endswith("0") and len(text.split(".")[1]) > 2:
            text = text[:-1]
        return text

    @property
    def measured(self) -> bool:
        return self.outcome_quality == "measured"

    @property
    def span(self) -> tuple[datetime, datetime]:
        """The drawn time range: ten minutes of tape on each side of the bet."""
        return self.entry_at - PAD, self.exit_at + PAD

    @property
    def line_span(self) -> tuple[datetime, datetime]:
        """Where a line may be **projected**: never past the exit.

        The screen projects to "now" because the coin is still live there; a
        closed bet has an end, and a line drawn ten minutes past its own exit
        would be a claim about a position that no longer existed.
        """
        return self.entry_at - PAD, self.exit_at

    def series(self) -> tuple[str, tuple[Point, ...]]:
        """``("15s", points)`` when the fast clock saw it, else ``("1m", points)``."""
        fast = tuple(p for p in self.fast if p.mcap_sol is not None)
        if len(fast) >= 2:
            return "15s", fast
        return "1m", tuple(Point(m.end_time, m.mcap_sol) for m in self.minutes if m.mcap_sol)

    def filename(self) -> str:
        return f"{self.entry_brt:%H%M}-{self.ticker}-{self.r_multiple:+.2f}.png"


def rule_set_slug(rule_set: str) -> str:
    """``flow_v2/2`` -> ``flow_v2-2``: a directory and a note name, not a path."""
    return rule_set.replace("/", "-")


def support_segment(minute: Minute, span: tuple[datetime, datetime]) -> Segment | None:
    """The support line of ``minute``, from its window's edge to the span's end.

    ``y(t) = support + slope × (t − end_time) / 1 min`` — the screen's formula
    (``meme-lines.ts``: ``supportSegment``), so the PNG and ``/meme/{mint}``
    cannot disagree about the same row.
    """
    if minute.support_line_sol is None:
        return None
    slope = minute.support_line_slope or Decimal(0)
    x1, x2 = max(span[0], minute.end_time - LINE_WINDOW), span[1]
    if x1 >= x2:
        return None

    def at(when: datetime) -> Decimal:
        minutes = Decimal(str((when - minute.end_time).total_seconds())) / Decimal(60)
        return minute.support_line_sol + slope * minutes  # type: ignore[operator]

    return Segment(x1, at(x1), x2, at(x2))


def previous_high(
    minutes: Sequence[Minute], minute: Minute, span: tuple[datetime, datetime]
) -> Segment | None:
    """``high_15m_sol`` of the row **before** ``minute`` — the breakout's reference.

    The contract excludes the current minute from its own comparison, so the
    level drawn is the previous row's, from the edge of that row's window to
    the end of ``span`` (``meme-lines.ts``: ``previousHighLine``).
    """
    earlier = [m for m in minutes if m.end_time < minute.end_time and m.high_15m_sol is not None]
    if not earlier:
        return None
    previous = earlier[-1]
    high = previous.high_15m_sol
    assert high is not None
    x1, x2 = max(span[0], previous.end_time - LINE_WINDOW), span[1]
    return None if x1 >= x2 else Segment(x1, high, x2, high)


def minute_at(minutes: Sequence[Minute], when: datetime) -> Minute | None:
    """The last closed minute at or before ``when`` — never a later one."""
    earlier = [m for m in minutes if m.end_time <= when]
    return earlier[-1] if earlier else None


def _minute(raw: Mapping[str, Any]) -> Minute:
    end_time = _ts(raw["end_time"])
    if end_time is None:
        raise ValueError("linha de meme_features_1m sem end_time")
    return Minute(
        end_time=end_time,
        mcap_sol=_dec(raw.get("mcap_sol")),
        support_line_sol=_dec(raw.get("support_line_sol")),
        support_line_slope=_dec(raw.get("support_line_slope")),
        high_15m_sol=_dec(raw.get("high_15m_sol")),
        low_15m_sol=_dec(raw.get("low_15m_sol")),
        breakout_15m=raw.get("breakout_15m"),
        higher_lows=raw.get("higher_lows"),
        line_reason=_text(raw.get("line_reason")),
    )


def parse_bet(raw: Mapping[str, Any]) -> Bet:
    entry_at, exit_at = _ts(raw["entry_at"]), _ts(raw["exit_at"])
    if entry_at is None or exit_at is None:
        raise ValueError(f"aposta {raw.get('bet_id')} sem entrada ou sem saída")
    fast_rows: list[Any] = list(raw.get("features_15s") or [])
    minute_rows: list[Any] = list(raw.get("features_1m") or [])
    snap_rows: list[Any] = list(raw.get("snapshots") or [])
    return Bet(
        bet_id=str(raw["bet_id"]),
        day=date.fromisoformat(str(raw["day"])),
        rule_set=str(raw["rule_set"]),
        kind=str(raw.get("kind") or ""),
        exp_ref=_text(raw.get("exp_ref")),
        code_ref=str(raw.get("code_ref") or ""),
        rule_set_params=raw.get("rule_set_params") or {},
        mint=str(raw["mint"]),
        symbol=_text(raw.get("symbol")),
        leg=str(raw.get("leg") or "single"),
        outcome_quality=str(raw.get("outcome_quality") or "measured"),
        outcome_quality_reason=_text(raw.get("outcome_quality_reason")),
        entry_at=entry_at,
        exit_at=exit_at,
        entry_mcap_sol=_dec(raw.get("entry_mcap_sol")),
        exit_mcap_sol=_dec(raw.get("exit_mcap_sol")),
        exit_reason=str(raw.get("exit_reason") or "desconhecido"),
        r_multiple=_dec(raw.get("r_multiple")) or Decimal(0),
        pnl_sol=_dec(raw.get("pnl_sol")),
        initial_risk_sol=_dec(raw.get("initial_risk_sol")),
        high_water_x=_dec(raw.get("high_water_x")),
        creator_sold_seen_at=_ts(raw.get("creator_sold_seen_at")),
        creator_sold_fraction=_dec(raw.get("creator_sold_fraction")),
        params=raw.get("params") or {},
        manual_plan=_text(raw.get("manual_plan")),
        fast=tuple(Point(_ts(r[0]) or entry_at, _dec(r[1])) for r in fast_rows),
        minutes=tuple(_minute(m) for m in minute_rows),
        snapshots=tuple(
            Snapshot(_ts(s[0]) or entry_at, str(s[1]), _dec(s[2]), bool(s[3])) for s in snap_rows
        ),
    )


def load_bets(path: Path) -> list[Bet]:
    with path.open(encoding="utf-8") as handle:
        return [parse_bet(json.loads(line)) for line in handle if line.strip()]
