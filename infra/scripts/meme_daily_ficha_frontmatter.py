"""Machine-readable Dataview fields for the daily/weekly ficha's frontmatter
(T4.92 follow-up) — pure, no IO, no clock.

Everton uses Obsidian's Dataview plugin; the loss-class pages roll up every
daily/weekly sheet, so besides the Portuguese Markdown body each sheet also
needs plain-decimal totals in its YAML. A class — or a whole day/week — with
zero losses is a real, provable zero: ``meme_daily_ficha_classify.loss_class``
always resolves a closed loser to one of :data:`LOSS_CLASSES` (it falls
through to ``saida_normal``), so counting zero occurrences of a class is a
fact, not a guess. ``null`` is reserved for what genuinely cannot be named —
the biggest leak on a day/week with no closed loss at all, or the calendar
window when there are no positions to bound it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from meme_daily_ficha_classify import LOSS_CLASSES, loss_class
from meme_daily_ficha_types import DayFicha, RealPosition

__all__ = ["Totals", "day_dataview_lines", "totals_for", "week_dataview_lines"]


@dataclass(frozen=True, slots=True)
class Totals:
    """The Dataview totals over one or more positions."""

    operacoes: int
    ganhos: int
    pnl_sol: Decimal
    by_class_n: dict[str, int]
    by_class_sol: dict[str, Decimal]
    maior_vazamento: str | None


def totals_for(positions: Sequence[RealPosition]) -> Totals:
    closed = [p for p in positions if p.pnl_sol is not None]
    wins = [p for p in closed if p.pnl_sol is not None and p.pnl_sol > 0]
    net = sum((p.pnl_sol for p in closed if p.pnl_sol is not None), Decimal(0))
    by_class: dict[str, list[Decimal]] = {klass: [] for klass in LOSS_CLASSES}
    for position in positions:
        klass = loss_class(position)
        if klass is not None:
            by_class[klass].append(position.pnl_sol or Decimal(0))
    non_empty = {klass: values for klass, values in by_class.items() if values}
    worst = None if not non_empty else min(non_empty, key=lambda klass: sum(non_empty[klass]))
    return Totals(
        operacoes=len(positions),
        ganhos=len(wins),
        pnl_sol=net,
        by_class_n={klass: len(values) for klass, values in by_class.items()},
        by_class_sol={klass: sum(values, Decimal(0)) for klass, values in by_class.items()},
        maior_vazamento=worst,
    )


def _decimal(value: Decimal) -> str:
    return f"{value:.4f}"


def _totals_lines(totals: Totals) -> list[str]:
    lines = [
        f"operacoes: {totals.operacoes}",
        f"ganhos: {totals.ganhos}",
        f"pnl_sol: {_decimal(totals.pnl_sol)}",
    ]
    for klass in LOSS_CLASSES:
        lines.append(f"perdas_{klass}_n: {totals.by_class_n[klass]}")
        lines.append(f"perdas_{klass}_sol: {_decimal(totals.by_class_sol[klass])}")
    lines.append(f"maior_vazamento: {totals.maior_vazamento or 'null'}")
    return lines


def day_dataview_lines(data: DayFicha) -> list[str]:
    """``dia`` plus the day's Dataview totals, in frontmatter order."""
    return [f"dia: {data.day.isoformat()}", *_totals_lines(totals_for(data.positions))]


def week_dataview_lines(by_day: dict[str, list[RealPosition]]) -> list[str]:
    """``semana_inicio``/``semana_fim`` — the earliest/latest day this window
    actually saw a position (the same days ``render_week``'s own title
    already uses) — plus the week's Dataview totals. ``null`` only when the
    window has no position at all."""
    days = sorted(by_day)
    start = days[0] if days else "null"
    end = days[-1] if days else "null"
    positions = [position for day_positions in by_day.values() for position in day_positions]
    return [
        f"semana_inicio: {start}",
        f"semana_fim: {end}",
        *_totals_lines(totals_for(positions)),
    ]
