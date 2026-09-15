"""T4.25 — one meme bet drawn: the curve in SOL, the lines, the entry and the exit.

The **only** module of this set that imports matplotlib, and the only one where
``Decimal`` becomes ``float`` (at the pixels, like ``render_operations_draw.py``).
``meme_render_bets.py`` imports it only when ``render`` runs, so ``export`` and
``notes`` work in an environment without matplotlib — it is not in the lock and
must not be (``uv run --with matplotlib``).

What the picture claims, and what it does not:

- the curve is the **theoretical** market cap in SOL (T4-MEME-RADAR §4:
  marginal price × supply, never what a full sell would realise), from
  ``meme_features_15s`` when the fast clock saw the coin and from
  ``meme_features_1m`` otherwise, with the raw ``meme_curve_snapshots`` as dots;
- the support line and the 15-minute high are the fold's numbers with the
  screen's geometry (``meme_render_bets_model.support_segment``), read from the
  **minute of the entry** — the last closed minute at or before the fill, which
  is the row the gate judged. A later minute never moves them;
- the target, the floor, the arm and the trailing are drawn with ``≈`` because
  the rules measure the **mark in SOL** (what a full sell would net, fees in),
  not the market cap: here the multiples are applied to the market cap at the
  entry, and the difference is the curve's slip against its own order plus
  1,75 % per side. The R in the title is the row's, never one read off the chart.
"""

# matplotlib is not (and cannot be) in this shared tree's `pyproject.toml`.
# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingParameterType=false
# pyright: reportUnknownParameterType=false, reportAttributeAccessIssue=false
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from textwrap import fill
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from meme_render_bets_model import Bet, Segment, minute_at, previous_high, support_segment

CURVE, SNAP = "#1f2937", "#9ca3af"
SUPPORT, HIGH, BREAK = "#1f77b4", "#b8860b", "#7c3aed"
ENTRY_C, EXIT_C, CREATOR_C = "#047857", "#b91c1c", "#be185d"
TARGET_C, FLOOR_C, TRAIL_C, PEAK_C = "#1d4ed8", "#b91c1c", "#ea580c", "#0f766e"

FIGSIZE = (12.0, 6.4)
DPI = 110
"""1320 x 704 px. The brief's ceiling is 200 KB; a 40-minute bet with the two
lines and the bands measures 90–140 KB at this dpi on a white background."""

REASON_PT = {
    "target": "alvo",
    "trailing": "trailing",
    "time_stop": "tempo",
    "migrated": "migração",
    "creator_dump": "dump do criador",
    "sell_now": "ordem da mesa",
    "rug_no_snapshot": "rug sem fotografia para vender",
    "max_loss": "piso de perda",
    "line_broken": "linha rompida",
    "dead": "mercado morto",
}
LEG_PT = {"probe": "sonda", "scale": "perna 2", "single": "perna única"}


def _num(value: datetime) -> float:
    return float(mdates.date2num(value))


def _sol(value: Decimal | float) -> str:
    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")


def _param(params: Any, key: str) -> Decimal | None:
    value = params.get(key) if hasattr(params, "get") else None
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


def _draw_series(axis, bet: Bet) -> tuple[str, list[float]]:
    values: list[float] = []
    dots = [(s.at, s.mcap_sol) for s in bet.snapshots if s.mcap_sol is not None]
    if dots:
        axis.plot(
            [_num(at) for at, _ in dots],
            [float(v) for _, v in dots],
            linestyle="none",
            marker=".",
            markersize=3.2,
            color=SNAP,
            zorder=2,
            label=f"fotografias da curva ({len(dots)})",
        )
        values += [float(v) for _, v in dots]
    clock, points = bet.series()
    if points:
        axis.plot(
            [_num(p.at) for p in points],
            [float(p.mcap_sol) for p in points if p.mcap_sol is not None],
            color=CURVE,
            linewidth=1.4,
            zorder=3,
            label=f"mcap em SOL ({clock})",
        )
        values += [float(p.mcap_sol) for p in points if p.mcap_sol is not None]
    return clock, values


def _plot_segment(axis, segment: Segment, colour: str, label: str, dashed: bool) -> None:
    axis.plot(
        [_num(segment.x1), _num(segment.x2)],
        [float(segment.y1), float(segment.y2)],
        color=colour,
        linewidth=1.6,
        linestyle=(0, (5, 3)) if dashed else "solid",
        zorder=4,
        label=label,
    )


def _draw_lines(axis, bet: Bet) -> list[str]:
    """The support of the entry minute, the previous high, every breakout."""
    notes: list[str] = []
    minute = minute_at(bet.minutes, bet.entry_at)
    if minute is None:
        return ["sem minuto fechado antes da entrada: nenhuma linha a desenhar"]
    support = support_segment(minute, bet.line_span)
    if support is None:
        notes.append(f"sem linha de suporte no minuto da entrada (`{minute.line_reason or '—'}`)")
    else:
        fundos = {True: "fundos ascendentes", False: "fundos descendentes", None: "fundos: —"}
        _plot_segment(
            axis,
            support,
            SUPPORT,
            f"suporte {_sol(minute.support_line_sol or 0)} SOL · {fundos[minute.higher_lows]}",
            dashed=False,
        )
    high = previous_high(bet.minutes, minute, bet.line_span)
    if high is not None:
        _plot_segment(axis, high, HIGH, f"máxima 15 min anterior {_sol(high.y1)} SOL", dashed=True)
    broken = [m for m in bet.minutes if m.breakout_15m is True]
    if broken:
        axis.plot(
            [_num(m.end_time) for m in broken],
            [float(m.mcap_sol or (high.y1 if high else 0)) for m in broken],
            linestyle="none",
            marker="^",
            markersize=7,
            color=BREAK,
            zorder=6,
            label=f"rompimento de 15 min ({len(broken)})",
        )
    if bet.exit_reason == "line_broken":
        at_exit = minute_at(bet.minutes, bet.exit_at)
        broken_line = None if at_exit is None else support_segment(at_exit, bet.line_span)
        if broken_line is not None and at_exit is not minute:
            _plot_segment(axis, broken_line, SUPPORT, "suporte no minuto da saída", dashed=True)
    return notes


def levels(bet: Bet) -> list[tuple[str, Decimal, str]]:
    """``(rótulo, nível em mcap, cor)`` — the contract's multiples, approximated.

    Applied to the market cap at the entry because that is the only price the
    chart has; the rules themselves read the mark in SOL. Hence every label
    carries ``≈``.
    """
    base = bet.entry_mcap_sol
    if base is None or base <= 0:
        return []
    out: list[tuple[str, Decimal, str]] = []
    target = _param(bet.params, "target_x")
    if target is not None:
        out.append((f"alvo ≈ {target}×", base * target, TARGET_C))
    loss = _param(bet.params, "max_loss_pct")
    if loss is not None:
        out.append((f"piso ≈ −{loss} %", base * (Decimal(100) - loss) / Decimal(100), FLOOR_C))
    arm = _param(bet.params, "trailing_arm_x")
    if arm is not None:
        out.append((f"arma o trailing ≈ {arm}×", base * arm, TRAIL_C))
    peak = bet.high_water_x
    trailing = _param(bet.params, "trailing_pct")
    if peak is not None:
        out.append((f"pico da marca ≈ {peak}×", base * peak, PEAK_C))
        if trailing is not None:
            level = base * peak * (Decimal(100) - trailing) / Decimal(100)
            out.append((f"trailing ≈ −{trailing} % do pico", level, TRAIL_C))
    return out


def _draw_levels(axis, bet: Bet, scale: tuple[float, float]) -> list[str]:
    """Draws every level that fits; the ones that do not come back as one note.

    A 3× target on a coin that never left its entry is thirty screens above the
    tape: forcing it into the y-axis would flatten the only thing worth looking
    at. It is named in the caption instead, with its number, never dropped.
    """
    off: list[str] = []
    start, end = _num(bet.entry_at), _num(bet.exit_at)
    for label, value, colour in levels(bet):
        y = float(value)
        if not scale[0] <= y <= scale[1]:
            off.append(f"{label} = {_sol(y)}")
            continue
        axis.hlines(y, start, end, color=colour, linewidth=1.2, linestyle=(0, (1, 2)), zorder=5)
        axis.annotate(
            f"{label} · {_sol(y)}",
            (end, y),
            textcoords="offset points",
            xytext=(4, 2),
            fontsize=6.5,
            color=colour,
            zorder=7,
        )
    return off


def _draw_marks(axis, bet: Bet, fallback: float) -> None:
    entry_y = float(bet.entry_mcap_sol) if bet.entry_mcap_sol is not None else fallback
    axis.plot(
        _num(bet.entry_at),
        entry_y,
        marker="^",
        markersize=11,
        color=ENTRY_C,
        linestyle="none",
        zorder=8,
        label=f"entrada {bet.entry_brt:%H:%M:%S} BRT · {_sol(entry_y)} SOL",
    )
    exit_label = REASON_PT.get(bet.exit_reason, bet.exit_reason)
    if bet.exit_mcap_sol is not None:
        axis.plot(
            _num(bet.exit_at),
            float(bet.exit_mcap_sol),
            marker="v",
            markersize=11,
            color=EXIT_C,
            linestyle="none",
            zorder=8,
            label=f"saída {bet.exit_brt:%H:%M:%S} BRT · {exit_label} · {bet.r_text} R",
        )
    else:
        axis.axvline(
            _num(bet.exit_at),
            color=EXIT_C,
            linewidth=1.4,
            linestyle=(0, (4, 2)),
            zorder=6,
            label=f"saída {bet.exit_brt:%H:%M:%S} BRT · {exit_label} · {bet.r_text} R",
        )
    if bet.creator_sold_seen_at is not None:
        fraction = bet.creator_sold_fraction
        share = "" if fraction is None else f" · {fraction * 100:.0f} % do saldo"
        axis.axvline(
            _num(bet.creator_sold_seen_at),
            color=CREATOR_C,
            linewidth=1.6,
            linestyle=(0, (2, 2)),
            zorder=6,
            label=f"venda do criador na cadeia {bet.creator_sold_seen_at.astimezone(bet.entry_brt.tzinfo):%H:%M:%S}{share}",
        )


def chart_title(bet: Bet) -> str:
    quality = "" if bet.measured else " · desfecho INDETERMINADO — não é medição"
    leg = LEG_PT.get(bet.leg, bet.leg)
    return (
        f"{bet.rule_set} · {bet.ticker} · {bet.entry_brt:%d/%m/%Y %H:%M} BRT · {bet.r_text} R\n"
        f"{bet.mint[:8]}… · saída por {REASON_PT.get(bet.exit_reason, bet.exit_reason)} · "
        f"{leg}{quality}"
    )


def caption(bet: Bet, clock: str, notes: list[str], off_scale: list[str]) -> str:
    held = int((bet.exit_at - bet.entry_at).total_seconds())
    base = (
        f"mcap teórico em SOL (T4-MEME-RADAR §4), fotografias `curve`/`pool` "
        f"({len(bet.snapshots)}) · série de {clock} · segurou {held} s · "
        f"faixas ≈: as regras medem a marca em SOL, não o mcap"
    )
    if notes:
        base += " · " + " · ".join(notes)
    if off_scale:
        base += " · fora da escala (SOL): " + " · ".join(off_scale)
    return base


def figure(bet: Bet, path: Path) -> Path:
    """Draw ``bet`` into ``path``. Raises when there is no tape at all to draw."""
    fig, axis = plt.subplots(figsize=FIGSIZE)
    fig.patch.set_facecolor("white")
    axis.set_facecolor("white")
    clock, values = _draw_series(axis, bet)
    if not values:
        plt.close(fig)
        raise ValueError(f"aposta {bet.bet_id} sem nenhuma série nem fotografia no intervalo")
    for value in (bet.entry_mcap_sol, bet.exit_mcap_sol):
        if value is not None:
            values.append(float(value))
    low, high = min(values), max(values)
    pad = (high - low) * 0.12 or max(high * 0.05, 1e-9)
    scale = (low - pad, high + pad)
    notes = _draw_lines(axis, bet)
    off_scale = _draw_levels(axis, bet, scale)
    _draw_marks(axis, bet, low)
    axis.set_xlim(_num(bet.span[0]), _num(bet.span[1]))
    axis.set_ylim(*scale)
    axis.set_ylabel("capitalização teórica (SOL)", fontsize=8)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=bet.entry_brt.tzinfo))
    axis.set_title(chart_title(bet), fontsize=9)
    axis.grid(alpha=0.15)
    # `best` and not a fixed corner: a curve that rises left to right leaves the
    # top-left free, one that dies leaves the bottom-right, and a legend of nine
    # entries sitting on the tape is the fastest way to hide the entry.
    axis.legend(loc="best", fontsize=6.2, ncols=2, framealpha=0.9)
    fig.text(
        0.008,
        0.052,
        fill(caption(bet, clock, notes, off_scale), width=160),
        fontsize=6.2,
        color="#4b5563",
        va="top",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return path


def render(bet: Bet, out_dir: Path, *, force: bool = False) -> tuple[Path, bool]:
    """``(caminho, escreveu?)`` — idempotent: an existing PNG is not redrawn."""
    path = out_dir / bet.filename()
    if path.exists() and not force:
        return path, False
    return figure(bet, path), True
