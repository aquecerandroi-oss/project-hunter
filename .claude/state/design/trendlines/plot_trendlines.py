"""Draw what the detector sees, on real candles — T3.34 item 5.

Development tool, not production code: it lives next to the PNGs it produces
and is run by hand.

    uv run --with matplotlib python .claude/state/design/trendlines/plot_trendlines.py \
        --csv <export.csv> --out .claude/state/design/trendlines

The CSV is the read-only export from the VPS (1-minute final candles folded in
SQL into complete 15m/1h buckets; a bucket with a missing minute is not
exported at all). ``Decimal`` all the way into :func:`scan`; ``float`` only at
the matplotlib boundary, where the pixels are.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_indicators.patterns.events import EventKind
from hunter_indicators.patterns.pivots import PivotKind
from hunter_indicators.patterns.scan import PatternScan, scan
from hunter_indicators.patterns.trendlines import LineKind

TIMEFRAMES = {"15m": Timeframe.M15, "1h": Timeframe.H1}
VISIBLE = {"15m": 384, "1h": 336}
RVOL_WINDOW = 96
UP = "#0e9f6e"
DOWN = "#d94f4f"
SUPPORT = "#1f77b4"
RESISTANCE = "#b8860b"


@dataclass(frozen=True, slots=True)
class Series:
    symbol: str
    tf: str
    bars: tuple[Bar, ...]
    rvol: tuple[Decimal | None, ...]


def _read(path: Path) -> list[Series]:
    grouped: dict[tuple[str, str], list[Bar]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            symbol, tf, bucket, open_, high, low, close, volume, _minutes = row
            start = datetime.fromisoformat(bucket)
            step = timedelta(minutes=15 if tf == "15m" else 60)
            grouped[(symbol, tf)].append(
                Bar(
                    open_time=start,
                    close_time=start + step,
                    open=Decimal(open_),
                    high=Decimal(high),
                    low=Decimal(low),
                    close=Decimal(close),
                    volume=Decimal(volume),
                )
            )
    out: list[Series] = []
    for (symbol, tf), bars in sorted(grouped.items()):
        ordered = tuple(sorted(bars, key=lambda bar: bar.open_time))
        out.append(Series(symbol=symbol, tf=tf, bars=ordered, rvol=_rvol(ordered)))
    return out


def _rvol(bars: tuple[Bar, ...]) -> tuple[Decimal | None, ...]:
    """Volume over the median of the previous ``RVOL_WINDOW`` bars — past only."""
    values: list[Decimal | None] = []
    for index, bar in enumerate(bars):
        if index < RVOL_WINDOW:
            values.append(None)
            continue
        window = [b.volume for b in bars[index - RVOL_WINDOW : index]]
        median = statistics.median(window)
        values.append(bar.volume / median if median > 0 else None)
    return tuple(values)


def _draw_candles(axis: plt.Axes, bars: tuple[Bar, ...], first: int) -> None:
    width = (bars[1].open_time - bars[0].open_time).total_seconds() / 86400 * 0.7
    for bar in bars[first:]:
        colour = UP if bar.close >= bar.open else DOWN
        stamp = mdates.date2num(bar.open_time)
        axis.plot(
            [stamp, stamp], [float(bar.low), float(bar.high)], color=colour, linewidth=0.5, zorder=2
        )
        bottom = float(min(bar.open, bar.close))
        height = float(abs(bar.close - bar.open)) or 1e-9
        axis.add_patch(
            plt.Rectangle(
                (stamp - width / 2, bottom), width, height, color=colour, zorder=2, linewidth=0
            )
        )


def _draw_lines(axis: plt.Axes, bars: tuple[Bar, ...], result: PatternScan, first: int) -> None:
    for line in result.lines:
        colour = SUPPORT if line.kind is LineKind.SUPPORT else RESISTANCE
        start = max(line.first_idx, first)
        stops = [start, result.as_of]
        axis.plot(
            [mdates.date2num(bars[index].open_time) for index in stops],
            [float(line.projected(index)) for index in stops],
            color=colour,
            linewidth=1.4,
            linestyle="-",
            zorder=3,
        )
        for number, (index, price) in enumerate(line.anchors, start=1):
            if index < first:
                continue
            axis.annotate(
                str(number),
                (mdates.date2num(bars[index].open_time), float(price)),
                textcoords="offset points",
                xytext=(0, -12 if line.kind is LineKind.SUPPORT else 8),
                ha="center",
                fontsize=7,
                color=colour,
                zorder=5,
            )
        axis.annotate(
            f"{line.kind.value[:3]} t={line.touches} v={line.violations}",
            (mdates.date2num(bars[result.as_of].open_time), float(line.projected(result.as_of))),
            textcoords="offset points",
            xytext=(4, 0),
            fontsize=6,
            color=colour,
            zorder=5,
        )


MARKERS = {
    EventKind.BREAKOUT: ("^", "#c026d3", "rompimento"),
    EventKind.RETEST: ("s", "#0891b2", "reteste"),
    EventKind.BOUNCE: ("o", "#65a30d", "toque/repique"),
}


def _draw_events(axis: plt.Axes, bars: tuple[Bar, ...], result: PatternScan, first: int) -> None:
    seen: set[EventKind] = set()
    for event in result.events:
        if event.index < first:
            continue
        marker, colour, label = MARKERS[event.kind]
        axis.plot(
            mdates.date2num(bars[event.index].open_time),
            float(event.close),
            marker=marker,
            color=colour,
            markersize=6,
            linestyle="none",
            zorder=6,
            label=label if event.kind not in seen else None,
        )
        seen.add(event.kind)


def _draw_pivots(axis: plt.Axes, bars: tuple[Bar, ...], result: PatternScan, first: int) -> None:
    for pivot in result.pivots:
        if pivot.index < first:
            continue
        axis.plot(
            mdates.date2num(bars[pivot.index].open_time),
            float(pivot.price),
            marker=".",
            color="#64748b",
            markersize=4,
            linestyle="none",
            zorder=4,
        )


def _figure(series: Series, result: PatternScan, out: Path) -> Path:
    bars = series.bars
    first = max(0, len(bars) - VISIBLE[series.tf])
    figure, axis = plt.subplots(figsize=(16, 8))
    _draw_candles(axis, bars, first)
    _draw_pivots(axis, bars, result, first)
    _draw_lines(axis, bars, result, first)
    _draw_events(axis, bars, result, first)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m %H:%M"))
    axis.set_xlim(
        mdates.date2num(bars[first].open_time) - 0.01,
        mdates.date2num(bars[-1].open_time) + 0.02,
    )
    lows = [float(bar.low) for bar in bars[first:]]
    highs = [float(bar.high) for bar in bars[first:]]
    pad = (max(highs) - min(lows)) * 0.06
    axis.set_ylim(min(lows) - pad, max(highs) + pad)
    highs_count = sum(1 for p in result.pivots if p.kind is PivotKind.HIGH)
    axis.set_title(
        f"{series.symbol} {series.tf} — {len(result.lines)} linhas válidas, "
        f"{len(result.channels)} canal(is), {len(result.events)} eventos · "
        f"pivôs {highs_count}/{len(result.pivots) - highs_count} (alta/baixa) · "
        f"corte {bars[result.as_of].close_time:%Y-%m-%d %H:%M}Z",
        fontsize=10,
    )
    axis.grid(alpha=0.15)
    if result.events:
        axis.legend(loc="upper left", fontsize=7)
    figure.autofmt_xdate()
    figure.tight_layout()
    path = out / f"{series.symbol.lower()}-{series.tf}.png"
    figure.savefig(path, dpi=110)
    plt.close(figure)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for series in _read(args.csv):
        result = scan(
            series.bars,
            timeframe=TIMEFRAMES[series.tf],
            rvol=series.rvol,
        )
        path = _figure(series, result, args.out)
        print(  # noqa: T201
            f"{series.symbol:8s} {series.tf:3s} bars={len(series.bars):5d} "
            f"pivots={len(result.pivots):3d} lines={len(result.lines)} "
            f"channels={len(result.channels)} events={len(result.events)} -> {path.name}"
        )
        for line in result.lines:
            print(  # noqa: T201
                f"    {line.kind.value:10s} touches={line.touches} span="
                f"{line.last_idx - line.first_idx:4d} violations={line.violations} "
                f"slope/bar={float(line.slope_per_bar):+.4f} valid_from={line.valid_from_idx}"
            )
        for event in result.events:
            print(  # noqa: T201
                f"    {event.kind.value:8s} bar={event.index:4d} "
                f"({event.direction.value}) {float(event.distance_atr):.2f} ATR"
            )


if __name__ == "__main__":
    main()
