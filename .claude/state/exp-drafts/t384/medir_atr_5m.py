"""T3.84 / EXP-0028 P1-P3 — ATR%(5m) medido, contra os 0,30 % previstos.

Le `barras.csv` (produzido por
infra/scripts/sql/research/2026-09-11-t384-q01-barras-5m-15m.sql) e roda o
`hunter_core.strategies.indicators.wilder_atr` **congelado** sobre janelas
rolantes de `atr_bars = 97` barras — exatamente o que `mean_reversion_m5_v1`
pede, em cada grade. Nenhuma reimplementacao de Wilder em lugar nenhum.

O 15 m sai junto como CONTROLE DE METODO: a T3.54 mediu 0,5585 % na mesma
janela e nos mesmos 16 mercados, e se esta conta nao reproduzir aquele numero
o valor de 5 m tambem nao vale. A cobertura mudou entre as duas medicoes (o
backfill da T3.76 fechou os buracos), entao a reproducao e aproximada por
construcao e a diferenca e reportada, nao escondida.

Identidade de pedagio (KB-0076, corrigida por notes-T3.40 §8b):
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
STEP = {"5m": timedelta(minutes=5), "15m": timedelta(minutes=15)}
GRIDS = ("5m", "15m")

# Os tres numeros do `paper_v1` e do contrato da mae que este script julga.
ATR_PCT_MIN = Decimal("0.006")  # mean_reversion_m5_v1, herdado byte a byte
ATR_PCT_MAX = Decimal("0.05")
STOP_FLOOR = Decimal("0.003")  # paper_v1 min_stop_distance_pct
STOP_CAP = Decimal("0.03")  # paper_v1 max_stop_distance_pct


def load(path: str) -> dict[tuple[str, str], list[Bar]]:
    series: dict[tuple[str, str], list[Bar]] = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            tf = row["tf"]
            if tf not in STEP:
                continue
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
    """Um ATR% por barra cujos 97 baldes anteriores sao contiguos e completos."""
    out: list[Decimal] = []
    for end in range(ATR_BARS - 1, len(bars)):
        window = bars[end - ATR_BARS + 1 : end + 1]
        if window[-1].open_time - window[0].open_time != step * (ATR_BARS - 1):
            continue  # buraco: `aggregate()` responderia `unavailable`, e nos tambem
        atr = wilder_atr(window, ATR_PERIOD)
        if atr is None:
            continue
        pct = atr_percent(atr, window[-1].close)
        if pct is not None:
            out.append(pct)
    return out


def share(values: list[Decimal], predicate) -> Decimal:
    if not values:
        return Decimal(0)
    return Decimal(sum(1 for v in values if predicate(v))) * 100 / Decimal(len(values))


def main() -> None:
    base = "C:/Users/evert/AppData/Local/Temp/claude/scratch/t384/barras_clean.csv"
    series = load(sys.argv[1] if len(sys.argv) > 1 else base)
    symbols = sorted({symbol for symbol, _ in series})
    per_tf: dict[str, list[Decimal]] = {tf: [] for tf in GRIDS}
    todas: dict[str, list[Decimal]] = {tf: [] for tf in GRIDS}
    rows: list[tuple[str, ...]] = []
    for symbol in symbols:
        cells: dict[str, Decimal] = {}
        counts: dict[str, int] = {}
        for tf in GRIDS:
            values = readings(series.get((symbol, tf), []), STEP[tf])
            counts[tf] = len(values)
            todas[tf].extend(values)
            mid = median(values)
            if mid is not None:
                cells[tf] = mid
                per_tf[tf].append(mid)
        if len(cells) < len(GRIDS):
            continue
        toll = {tf: COST_NUMERATOR / (STOP_ATR * cells[tf]) for tf in cells}
        leituras5 = readings(series[(symbol, "5m")], STEP["5m"])
        rows.append(
            (
                symbol,
                f"{counts['5m']}/{counts['15m']}",
                f"{cells['5m'] * 100:.4f}",
                f"{cells['15m'] * 100:.4f}",
                f"{cells['5m'] / cells['15m']:.3f}",
                f"{toll['5m']:.4f}",
                f"{toll['15m']:.4f}",
                f"{share(leituras5, lambda v: v >= ATR_PCT_MIN):.2f}",
                f"{share(leituras5, lambda v: v <= STOP_FLOOR):.2f}",
                f"{share(leituras5, lambda v: v > STOP_CAP):.2f}",
            )
        )

    header = (
        "mercado",
        "n(5m/15m)",
        "ATR%5m",
        "ATR%15m",
        "5m/15m",
        "custoR5m",
        "custoR15m",
        "%>=0,6%",
        "%<=0,3%",
        "%>3%",
    )
    widths = [max(len(header[i]), max((len(r[i]) for r in rows), default=0)) for i in range(len(header))]
    line = "  ".join(header[i].ljust(widths[i]) for i in range(len(header)))
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(header))))

    print()
    print(f"mediana das medianas ({len(rows)} mercados):")
    mids = {tf: median(per_tf[tf]) for tf in GRIDS}
    for tf in GRIDS:
        toll = COST_NUMERATOR / (STOP_ATR * mids[tf])
        print(f"  ATR%({tf}) p50 = {mids[tf] * 100:.4f} %   custo_R(stop_atr=1) = {toll:.4f} R")
    ratio = mids["5m"] / mids["15m"]
    print(f"  razao 5m/15m = {ratio:.4f}   (previsto 3^-0,571 = 0,534)")
    razoes = sorted(
        (median(readings(series[(s, "5m")], STEP["5m"]))
         / median(readings(series[(s, "15m")], STEP["15m"])))
        for s in symbols
    )
    print(f"  razao 5m/15m por mercado: min {razoes[0]:.3f} p50 {razoes[len(razoes) // 2]:.3f} max {razoes[-1]:.3f}")

    print()
    print("P2 -- o piso de ATR% como definidor da versao (todas as leituras dos 16 mercados):")
    for tf in GRIDS:
        v = todas[tf]
        elegiveis = sorted(x for x in v if ATR_PCT_MIN <= x <= ATR_PCT_MAX)
        cond = median(elegiveis)
        print(
            f"  {tf}: n={len(v)}  fracao em [0,6 %; 5 %] = {share(v, lambda x: ATR_PCT_MIN <= x <= ATR_PCT_MAX):.2f} %"
            f"  ATR% p50 CONDICIONAL ao portao = {cond * 100:.4f} %"
            f"  pedagio p50 condicional = {COST_NUMERATOR / (STOP_ATR * cond):.4f} R"
        )

    print()
    print("C5 -- a banda de stop do paper_v1 [0,3 %; 3 %] com stop_atr = 1 (leituras agregadas):")
    for tf in GRIDS:
        v = todas[tf]
        el = [x for x in v if ATR_PCT_MIN <= x <= ATR_PCT_MAX]
        print(
            f"  {tf}: incondicional <= 0,3 % = {share(v, lambda x: x <= STOP_FLOOR):.2f} %"
            f"  > 3 % = {share(v, lambda x: x > STOP_CAP):.2f} %"
            f"  || condicional ao portao <= 0,3 % = {share(el, lambda x: x <= STOP_FLOOR):.2f} %"
            f"  > 3 % = {share(el, lambda x: x > STOP_CAP):.2f} %"
        )
    print()
    print("mercados cuja MEDIANA de 5 m cai sob o piso de risco de 0,3 %:")
    baixos = [s for s in symbols if median(readings(series[(s, "5m")], STEP["5m"])) <= STOP_FLOOR]
    print(f"  {len(baixos)}/16: {' '.join(baixos) if baixos else '(nenhum)'}")


if __name__ == "__main__":
    main()
