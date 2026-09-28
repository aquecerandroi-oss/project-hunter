"""R85 — painel diário do R84 com máxima e mínima, e o universo ponto-no-tempo na abertura e = d + 1.

Reaproveita sem editar: `r84/config.py` (exclusões, continuidades, as_of), `r84/gaps.py` (lacunas classificadas) e
`r84/panel.py` (séries, deslistagem, fecho carregado). Acrescenta só `high`/`low` alinhados às mesmas séries.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

R84 = Path(__file__).resolve().parent.parent / "r84"
sys.path.insert(0, str(R84))

from config import AS_OF_DAY, CACHE, EXCLUDED, LINKS, trading_symbols  # noqa: E402
from engine import TOP, VOL_WINDOW, listed  # noqa: E402
from gaps import KEEP_TOGETHER  # noqa: E402
from panel import DAY_MS, Panel, build_panel  # noqa: E402

Row = tuple[str, int, float, float, float, float, float]  # símbolo, dia, open, high, low, close, quote_volume


@dataclass
class HLPanel:
    p: Panel
    high: np.ndarray  # (S, D), NaN = sem vela
    low: np.ndarray


def load_rows_hl(path: Path = CACHE / "candles_1d.csv", as_of_day: int = AS_OF_DAY) -> list[Row]:
    seen: dict[tuple[str, int], Row] = {}
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            day = int(r["open_ms"]) // DAY_MS
            if day < as_of_day:
                seen.setdefault((r["symbol"], day), (r["symbol"], day, float(r["open"]), float(r["high"]),
                                                     float(r["low"]), float(r["close"]), float(r["quote_volume"])))
    return list(seen.values())


def apply_links_hl(rows: list[Row], trading: set[str], links=LINKS) -> tuple[list[Row], set[str]]:
    """Como `r84.config.apply_links`, levando máxima e mínima (preços ÷ razão, volume em USDT igual)."""
    trading = set(trading)
    by: dict[str, list[Row]] = {}
    for r in rows:
        by.setdefault(r[0], []).append(r)
    for old, new, ratio in links:
        if old not in by or new not in by:
            continue
        last_old = max(r[1] for r in by[old])
        by[old] = by[old] + [(old, d, o / ratio, h / ratio, lo / ratio, c / ratio, v)
                             for _, d, o, h, lo, c, v in by[new] if d > last_old]
        del by[new]
        if new in trading:
            trading.add(old)
    return [r for rs in by.values() for r in rs], trading


def build_hl_panel(rows: list[Row], trading: set[str], excluded: set[str] = EXCLUDED, today: int = AS_OF_DAY,
                   day0: int | None = None, day_end: int | None = None,
                   keep_together=KEEP_TOGETHER) -> HLPanel:
    p = build_panel([(s, d, o, c, v) for s, d, o, _, _, c, v in rows], trading, excluded, today, day0=day0,
                    day_end=day_end, keep_together=keep_together)
    hi = np.full(p.close.shape, np.nan)
    lo = np.full(p.close.shape, np.nan)
    by_sym: dict[str, list[int]] = {}
    for i, sid in enumerate(p.ids):
        by_sym.setdefault(sid.split("#")[0], []).append(i)
    for s, d, _, h, low, _, _ in rows:
        col = d - p.day0
        if d >= today or s not in by_sym or not 0 <= col < hi.shape[1]:
            continue
        for i in by_sym[s]:
            if p.first[i] <= col <= p.last[i]:
                hi[i, col], lo[i, col] = h, low
                break
    return HLPanel(p, hi, lo)


def load_real() -> HLPanel:
    rows, trading = apply_links_hl(load_rows_hl(), set(trading_symbols()))
    return build_hl_panel(rows, trading)


def universe(p: Panel, e: int, top: int = TOP) -> np.ndarray:
    """Os `top` pares de maior quote_volume em [e − 30, e − 1] entre os listados (regra do R84, só datas e volume)."""
    cand = np.flatnonzero(listed(p, e))
    vol = np.nansum(p.qvol[cand, max(e - VOL_WINDOW, 0) : e], axis=1)
    order = sorted(range(cand.size), key=lambda k: (-vol[k], p.ids[cand[k]]))[:top]
    return cand[order]
