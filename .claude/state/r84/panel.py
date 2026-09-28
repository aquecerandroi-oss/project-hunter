"""R84 — painel diário por SÉRIE (símbolo partido em lacunas ≥ 14 d), só velas finais.

Regras de notes-R84.md §1.3: cada símbolo é uma série; lacuna de ≥ 14 dias sem vela parte o símbolo; fim de série =
última vela de série que não continua (símbolo não TRADING hoje ou 1.ª parte de uma quebra). Velas com abertura no dia
UTC corrente ou depois (em formação) são descartadas no carregamento.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

DAY_MS = 86_400_000
SPLIT_GAP = 14  # dias consecutivos sem vela que partem um símbolo


@dataclass
class Panel:
    ids: list[str]
    base: list[str]
    day0: int  # dia UTC (época) da coluna 0
    open: np.ndarray  # (S, D) abertura real, NaN = sem vela
    close: np.ndarray
    qvol: np.ndarray
    first: np.ndarray  # índice de coluna da 1.ª vela real
    last: np.ndarray  # índice da última vela real
    ended: np.ndarray  # a série termina em `last` (deslistagem/quebra)
    excluded: np.ndarray  # fora por desenho (E1/E2/E3)
    close_ff: np.ndarray  # fecho carregado dentro de [first, last]
    open_ff: np.ndarray  # abertura real, ou o fecho anterior carregado
    long_gaps: list[tuple[str, int, int, int]]  # (símbolo, último dia antes, dia da volta, dias ausentes) — p/ revisão

    def col(self, epoch_day: int) -> int:
        return epoch_day - self.day0


def _ffill(a: np.ndarray) -> np.ndarray:
    out = a.copy()
    for j in range(1, out.shape[1]):
        m = np.isnan(out[:, j])
        out[m, j] = out[m, j - 1]
    return out


def build_panel(
    rows: list[tuple[str, int, float, float, float]],
    trading: set[str],
    excluded_bases: set[str],
    today_epoch_day: int,
    day0: int | None = None,
    day_end: int | None = None,
    keep_together: set[tuple[str, int]] | frozenset[tuple[str, int]] = frozenset(),
) -> Panel:
    """rows = (símbolo, dia UTC da abertura, open, close, quote_volume). Descarta dia ≥ hoje (não final).

    Lacuna ≥ 14 d é listada em `long_gaps` e parte o símbolo, exceto quando (símbolo, dia da volta) está em
    `keep_together` — classificação manual "o mesmo ativo voltou" (Astra R84 #3: lacuna longa é alerta, não prova).
    """
    by: dict[str, dict[int, tuple[float, float, float]]] = defaultdict(dict)
    for sym, day, o, c, v in rows:
        if day >= today_epoch_day:
            continue
        by[sym][day] = (o, c, v)
    d0 = min(min(d) for d in by.values()) if day0 is None else day0
    d1 = (today_epoch_day - 1) if day_end is None else day_end
    n_days = d1 - d0 + 1
    ids, bases, parts = [], [], []
    long_gaps: list[tuple[str, int, int, int]] = []
    for sym in sorted(by):
        days = sorted(by[sym])
        gaps = [k for k in range(1, len(days)) if days[k] - days[k - 1] - 1 >= SPLIT_GAP]
        long_gaps += [(sym, days[k - 1], days[k], days[k] - days[k - 1] - 1) for k in gaps]  # dias UTC (época)
        cuts = [0] + [k for k in gaps if (sym, days[k]) not in keep_together] + [len(days)]
        for p in range(len(cuts) - 1):
            seg = days[cuts[p] : cuts[p + 1]]
            ids.append(f"{sym}#{p}" if len(cuts) > 2 else sym)
            bases.append(sym[:-4])
            is_last_part = p == len(cuts) - 2
            parts.append((sym, seg, (not is_last_part) or (sym not in trading)))
    s = len(ids)
    op = np.full((s, n_days), np.nan)
    cl = np.full((s, n_days), np.nan)
    qv = np.full((s, n_days), np.nan)
    first = np.zeros(s, dtype=np.int64)
    last = np.zeros(s, dtype=np.int64)
    ended = np.zeros(s, dtype=bool)
    for i, (sym, seg, end) in enumerate(parts):
        for day in seg:
            o, c, v = by[sym][day]
            op[i, day - d0], cl[i, day - d0], qv[i, day - d0] = o, c, v
        first[i], last[i], ended[i] = seg[0] - d0, seg[-1] - d0, end
    cff = _ffill(cl)
    prev = np.concatenate([np.full((s, 1), np.nan), cff[:, :-1]], axis=1)
    off = np.where(np.isnan(op), prev, op)
    cols = np.arange(n_days)[None, :]
    outside = (cols < first[:, None]) | (cols > last[:, None])
    cff[outside] = np.nan
    off[outside] = np.nan
    excl = np.array([b in excluded_bases for b in bases], dtype=bool)
    return Panel(ids, bases, d0, op, cl, qv, first, last, ended, excl, cff, off, long_gaps)


def load_csv(path: Path) -> list[tuple[str, int, float, float, float]]:
    out = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append((r["symbol"], int(r["open_ms"]) // DAY_MS, float(r["open"]), float(r["close"]), float(r["quote_volume"])))
    return out
