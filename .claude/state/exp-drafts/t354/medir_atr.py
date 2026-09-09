"""T3.54 deliverable 1 — ATR%(15m) vs ATR%(1h) vs ATR%(4h) per market, and the
implied toll per R at stop_atr = 1.

Reads `barras.csv` (produced by
infra/scripts/sql/research/2026-09-09-t354-q01-barras-por-timeframe.sql) and runs
the frozen `hunter_core.strategies.indicators.wilder_atr` over rolling windows of
`atr_bars = 97` bars — exactly what `mean_reversion_v1` asks for, on each
timeframe. No reimplementation of Wilder anywhere.

Toll identity (KB-0076, corrected by notes-T3.40 §8b):
    risco% = stop_atr x ATR%          custo_R = 0,0020 / risco%
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, "C:/dev/project-hunter/packages/core")

from hunter_core.strategies.aggregate import Bar  # noqa: E402
from hunter_core.strategies.indicators import atr_percent, median, wilder_atr  # noqa: E402

ATR_BARS = 97
ATR_PERIOD = 14
COST_NUMERATOR = Decimal("0.0020")
STOP_ATR = Decimal("1")
STEP = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "4h": timedelta(hours=4)}


def load(path: str) -> dict[tuple[str, str], list[Bar]]:
    series: dict[tuple[str, str], list[Bar]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            tf = row["tf"]
            open_time = datetime.fromisoformat(row["bucket"])
            series.setdefault((row["symbol"], tf), []).append(
                Bar(
                    open_time=open_time,
                    close_time=open_time + STEP[tf],
                    open=Decimal(row["o"]),
                    high=Decimal(row["h"]),
                    low=Decimal(row["l"]),
                    close=Decimal(row["c"]),
                    volume=Decimal(0),
                )
            )
    return series


def readings(bars: list[Bar], step: timedelta) -> list[Decimal]:
    """One ATR% per bar whose 97 preceding buckets are contiguous and complete."""
    out: list[Decimal] = []
    for end in range(ATR_BARS - 1, len(bars)):
        window = bars[end - ATR_BARS + 1 : end + 1]
        if window[-1].open_time - window[0].open_time != step * (ATR_BARS - 1):
            continue  # gap: aggregate() would answer `unavailable`, so do we
        atr = wilder_atr(window, ATR_PERIOD)
        if atr is None:
            continue
        pct = atr_percent(atr, window[-1].close)
        if pct is not None:
            out.append(pct)
    return out


def quantile(values: list[Decimal], q: float) -> Decimal:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main() -> None:
    series = load("C:/dev/project-hunter/.claude/state/exp-drafts/t354/barras.csv")
    symbols = sorted({symbol for symbol, _ in series})
    per_tf: dict[str, list[Decimal]] = {"15m": [], "1h": [], "4h": []}
    rows: list[tuple[str, ...]] = []
    for symbol in symbols:
        cells: dict[str, Decimal] = {}
        counts: dict[str, int] = {}
        for tf in ("15m", "1h", "4h"):
            bars = series.get((symbol, tf), [])
            values = readings(bars, STEP[tf])
            counts[tf] = len(values)
            mid = median(values)
            if mid is not None:
                cells[tf] = mid
                per_tf[tf].append(mid)
        if len(cells) < 3:
            continue
        toll = {tf: COST_NUMERATOR / (STOP_ATR * cells[tf]) for tf in cells}
        rows.append(
            (
                symbol,
                f"{counts['15m']}/{counts['1h']}/{counts['4h']}",
                f"{cells['15m'] * 100:.4f}",
                f"{cells['1h'] * 100:.4f}",
                f"{cells['4h'] * 100:.4f}",
                f"{cells['1h'] / cells['15m']:.3f}",
                f"{cells['4h'] / cells['15m']:.3f}",
                f"{toll['15m']:.4f}",
                f"{toll['1h']:.4f}",
                f"{toll['4h']:.4f}",
            )
        )

    header = (
        "mercado",
        "n(15m/1h/4h)",
        "ATR%15m",
        "ATR%1h",
        "ATR%4h",
        "1h/15m",
        "4h/15m",
        "custoR15m",
        "custoR1h",
        "custoR4h",
    )
    widths = [max(len(header[i]), max((len(r[i]) for r in rows), default=0)) for i in range(10)]
    line = "  ".join(header[i].ljust(widths[i]) for i in range(10))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(10)))

    print()
    print("mediana das medianas (16 mercados) e razoes:")
    mids = {tf: median(per_tf[tf]) for tf in per_tf}
    for tf in ("15m", "1h", "4h"):
        toll = COST_NUMERATOR / (STOP_ATR * mids[tf])
        print(f"  ATR%({tf}) p50 = {mids[tf] * 100:.4f} %   custo_R(stop_atr=1) = {toll:.4f} R")
    print(f"  razao 1h/15m = {mids['1h'] / mids['15m']:.3f}   4h/15m = {mids['4h'] / mids['15m']:.3f}")
    ratios_h1 = sorted(
        median(readings(series[(s, "1h")], STEP["1h"]))
        / median(readings(series[(s, "15m")], STEP["15m"]))
        for s in symbols
        if (s, "1h") in series
    )
    print(
        f"  razao 1h/15m por mercado: min {ratios_h1[0]:.3f} "
        f"p50 {quantile(ratios_h1, 0.5):.3f} max {ratios_h1[-1]:.3f}"
    )
    print()
    print("banda de stop do paper_v1 [0,003; 0,03] com stop_atr = 1:")
    for tf in ("15m", "1h", "4h"):
        under = sum(1 for v in per_tf[tf] if v < Decimal("0.003"))
        over = sum(1 for v in per_tf[tf] if v > Decimal("0.03"))
        print(
            f"  {tf}: {under}/16 mercados com ATR% p50 < 0,3 % ; "
            f"{over}/16 com ATR% p50 > 3 %"
        )


if __name__ == "__main__":
    main()
