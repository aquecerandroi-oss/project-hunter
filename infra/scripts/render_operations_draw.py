"""T3.50 — o PNG de uma operação: velas de 15 m, linhas do corte, níveis, saída.

O **único** módulo desta trinca que importa matplotlib, e o único onde
``Decimal`` vira ``float`` (na borda dos pixels, como em
``.claude/state/design/trendlines/plot_trendlines.py``, de onde o estilo de vela
e de linha vem). ``render_operations.py`` só o importa quando o subcomando
``render`` roda, de modo que ``export`` e a escrita das notas funcionam num
ambiente sem matplotlib.

O que o desenho afirma, e o que ele **não** afirma:

- as linhas são as de ``tl_scan`` no corte da barra da decisão — o traço sólido
  vai do primeiro pivô da linha até essa barra, e a linha que a estratégia
  **usou** (quando há ``line_id`` no envelope) ganha destaque e a projeção
  tracejada para a frente, que é onde a invalidação estrutural mora;
- entrada, stop e alvo são segmentos horizontais que começam no instante da
  entrada e terminam no da saída — não são linhas de gráfico, são o contrato da
  operação;
- as velas **depois** da barra da decisão são consequência, não entrada: elas
  não podem mover nenhuma linha (``tl_scan`` corta antes).
"""

# matplotlib não está (e não pode estar) no `pyproject.toml` desta árvore
# compartilhada — roda-se com `uv run --with matplotlib`, como na T3.34. O
# pyright do repositório resolve imports contra `.venv`, onde ele não existe.
# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportMissingParameterType=false
# pyright: reportUnknownParameterType=false
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from render_operations_chart import Operation, geometry

from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.tl_lines import LineKind, TrendLine
from hunter_core.strategies.tl_scan import TlScan

UP, DOWN = "#0e9f6e", "#d94f4f"
SUPPORT, RESISTANCE, USED = "#1f77b4", "#b8860b", "#7c3aed"
ENTRY_C, STOP_C, TARGET_C, EXIT_C = "#047857", "#b91c1c", "#1d4ed8", "#111827"
DECISION_C, PIVOT_C = "#6b7280", "#334155"

FIGSIZE = (12.8, 6.6)
DPI = 96
"""1229 x 634 px. Medido nesta task: um gráfico de ~110 velas com seis linhas sai
entre 70 e 110 KB, dentro do teto de 120 KB do brief. Subir para dpi 110 passa de
120 KB em mercados com muita vela verde/vermelha alternada."""

RESULT_PT = {
    "target": "alvo",
    "stop": "stop",
    "expired": "horizonte",
    "invalidated": "invalidação",
    "open": "aberta",
}


def _num(value: datetime) -> float:
    return float(mdates.date2num(value))


def _price(value: Decimal) -> str:
    """Preço legível sem mentir: zeros à direita só caem se houver ponto decimal.

    ``"1000".rstrip("0")`` é ``"1"``, e um rótulo de alvo que diz 1 onde o alvo é
    1000 é pior do que um rótulo comprido.
    """
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _draw_candles(axis, bars: tuple[Bar, ...]) -> None:
    width = 15 * 60 / 86400 * 0.68
    for bar in bars:
        colour = UP if bar.close >= bar.open else DOWN
        stamp = _num(bar.open_time)
        axis.plot(
            [stamp, stamp], [float(bar.low), float(bar.high)], color=colour, linewidth=0.6, zorder=2
        )
        bottom = float(min(bar.open, bar.close))
        height = float(abs(bar.close - bar.open)) or 1e-9
        axis.add_patch(
            plt.Rectangle(
                (stamp - width / 2, bottom), width, height, color=colour, zorder=2, linewidth=0
            )
        )


def _line_points(
    line: TrendLine, bars: tuple[Bar, ...], scan: TlScan, offset: int
) -> tuple[list[float], list[float]]:
    first, last = line.first_idx, scan.as_of
    return (
        [_num(bars[offset + first].open_time), _num(bars[offset + last].open_time)],
        [float(line.projected(first)), float(line.projected(last))],
    )


def _draw_lines(axis, op: Operation, bars: tuple[Bar, ...], scan: TlScan, offset: int) -> None:
    used = op.used_line_id
    for rank, line in enumerate(scan.lines):
        highlight = used is not None and line.line_id == used
        colour = USED if highlight else (SUPPORT if line.kind is LineKind.SUPPORT else RESISTANCE)
        xs, ys = _line_points(line, bars, scan, offset)
        axis.plot(
            xs, ys, color=colour, linewidth=2.1 if highlight else 1.2, zorder=4 if highlight else 3
        )
        # Escada de 8 pt por linha: seis linhas terminam na mesma barra e várias
        # delas em preços próximos, então rótulos no mesmo y viram um borrão.
        axis.annotate(
            f"{line.kind.value[:3]} t={line.touches} v={line.violations}"
            + (" ← usada" if highlight else ""),
            (xs[1], ys[1]),
            textcoords="offset points",
            xytext=(-6, 4 + 8 * rank if line.kind is LineKind.RESISTANCE else -10 - 8 * rank),
            ha="right",
            fontsize=6.5,
            color=colour,
            zorder=6,
        )
        if highlight and offset + scan.as_of + 1 < len(bars):
            tail = len(bars) - 1 - offset
            axis.plot(
                [xs[1], _num(bars[-1].open_time)],
                [ys[1], float(line.projected(tail))],
                color=colour,
                linewidth=1.2,
                linestyle=(0, (4, 3)),
                zorder=4,
            )


def _draw_pivots(axis, op: Operation, bars: tuple[Bar, ...], scan: TlScan, offset: int) -> None:
    for pivot in scan.pivots:
        axis.plot(
            _num(bars[offset + pivot.index].open_time),
            float(pivot.price),
            marker=".",
            color=PIVOT_C,
            markersize=3,
            linestyle="none",
            zorder=3,
        )
    idx, price = op.features.get("pivot_low_idx"), op.features.get("pivot_low_price")
    if idx is not None and price is not None and 0 <= offset + int(idx) < len(bars):
        axis.plot(
            _num(bars[offset + int(idx)].open_time),
            float(Decimal(price)),
            marker="v",
            color=STOP_C,
            markersize=8,
            linestyle="none",
            zorder=7,
            label="pivô do stop",
        )


def _draw_levels(axis, op: Operation, bars: tuple[Bar, ...]) -> None:
    start = _num(op.entry_ts or op.decision_bar_close)
    end = _num(op.exit_ts or bars[-1].close_time)
    levels = [
        (op.entry, ENTRY_C, "entrada", 4),
        (op.stop, STOP_C, "stop", -9),
        *[(t, TARGET_C, f"alvo {i}", 4) for i, t in enumerate(op.targets, start=1)],
    ]
    for value, colour, label, dy in levels:
        if value is None:
            continue
        axis.hlines(float(value), start, end, color=colour, linewidth=1.5, zorder=5, label=label)
        # À direita do fim do segmento: à esquerda estão a barra da decisão e os
        # rótulos das linhas de tendência, e os dois conjuntos se sobrepunham.
        axis.annotate(
            f"{label} {_price(value)}",
            (end, float(value)),
            textcoords="offset points",
            xytext=(5, dy),
            fontsize=6.5,
            color=colour,
            zorder=7,
        )
    axis.axvline(
        _num(op.decision_bar_close),
        color=DECISION_C,
        linewidth=1.0,
        linestyle=(0, (2, 3)),
        zorder=3,
        label="barra da decisão",
    )
    if op.exit_ts is not None and op.exit_price is not None:
        axis.plot(
            _num(op.exit_ts),
            float(op.exit_price),
            marker="X",
            color=EXIT_C,
            markersize=9,
            linestyle="none",
            zorder=8,
            label=f"saída: {RESULT_PT.get(op.result, op.result)}",
        )


def chart_title(op: Operation, scan: TlScan | None) -> str:
    r = "R indefinido" if op.r_multiple is None else f"{op.r_multiple:+.2f} R"
    lines = "sem geometria" if scan is None else f"{len(scan.lines)} linha(s) no corte"
    return (
        f"{op.symbol} · {op.label} · {op.brt:%d/%m/%Y %H:%M} BRT "
        f"({op.decision_bar_close.astimezone(UTC):%H:%M}Z) · {r}\n"
        f"{op.coorte} · saída por {RESULT_PT.get(op.result, op.result)} · {lines}"
    )


def figure(op: Operation, path: Path) -> Path:
    """Desenha ``op`` em ``path``. Levanta se a operação não tem velas."""
    bars = op.bars
    if not bars:
        raise ValueError(f"operação {op.signal_id} sem velas exportadas")
    scan, offset = geometry(op)
    fig, axis = plt.subplots(figsize=FIGSIZE)
    _draw_candles(axis, bars)
    if scan is not None:
        _draw_pivots(axis, op, bars, scan, offset)
        _draw_lines(axis, op, bars, scan, offset)
    _draw_levels(axis, op, bars)
    axis.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, 3)))
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    axis.set_xlim(_num(bars[0].open_time) - 0.006, _num(bars[-1].close_time) + 0.075)
    lows = [float(b.low) for b in bars] + [float(v) for v in (op.stop,) if v is not None]
    highs = [float(b.high) for b in bars] + [float(v) for v in op.targets]
    pad = (max(highs) - min(lows)) * 0.05
    axis.set_ylim(min(lows) - pad, max(highs) + pad)
    axis.set_title(chart_title(op, scan), fontsize=9)
    axis.grid(alpha=0.15)
    axis.legend(loc="upper left", fontsize=6.5, ncols=3, framealpha=0.85)
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def render(op: Operation, out_dir: Path, *, force: bool = False) -> tuple[Path, bool]:
    """``(caminho, escreveu?)`` — idempotente: PNG existente não é redesenhado."""
    path = out_dir / op.filename()
    if path.exists() and not force:
        return path, False
    return figure(op, path), True
