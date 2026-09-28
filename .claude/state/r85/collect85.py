"""R85 — varre o universo dia a dia e junta eventos, controles e saídas de todos os braços (sem estatística aqui)."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from data85 import HLPanel, build_hl_panel
from geom85 import BANDS
from study85 import (
    EXT,
    STOP_ATR,
    TOLS,
    SeriesFlags,
    exit_fixed,
    exit_struct,
    members,
    scan_series,
)

EPOCH = dt.date(1970, 1, 1)
D_FIRST = (dt.date(2019, 2, 24) - EPOCH).days
D_LAST = (dt.date(2026, 9, 16) - EPOCH).days  # saída de 10 d em vela final
D_STRUCT_LAST = (dt.date(2026, 7, 28) - EPOCH).days
SPLIT = (dt.date(2022, 1, 1) - EPOCH).days
HOLDS = (5, 10, 20)
MAIN = BANDS.index((0.50, 0.618))


@dataclass
class Arm:
    events: dict[int, list[tuple[int, float, float]]] = field(default_factory=lambda: defaultdict(list))  # H → [(dd, opt, pes)]
    coins: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))


@dataclass
class Collected:
    fib: list[Arm]  # por faixa
    fib_ctrl: dict[int, dict[int, list[tuple[float, float]]]]  # H → dd → [(opt, pes)]
    fib_ctrl_ids: dict[int, list[int]]  # dd → séries controle (para o pareamento estrutural)
    struct: list[tuple[int, float, float, int, str]]  # (dd, opt, pes, m, moeda)
    struct_ctrl: dict[int, list[tuple[float, float]]]  # índice do evento estrutural → saídas dos controles
    fixed_same_entry: list[tuple[float, float] | None]  # a fixa de 10 d das mesmas entradas (None = censurada)
    lta: dict[float, dict[str, Arm]]  # tol → {"A","B"}
    lta_ctrl: dict[float, dict[int, dict[int, list[tuple[float, float]]]]]  # tol → H → dd → [...]
    counts: dict[str, int]
    delays: list[int]
    n_days: int
    split_dd: int


def base(sid: str) -> str:
    return sid.split("#")[0]


def structural_row(hp: HLPanel, i: int, e: int, hh: float, ll: float, atr_d: float, ex10):
    """Saída estrutural do evento e, à parte, a fixa de 10 d para o descritivo pareado. A estrutural não depende da
    fixa existir (Astra, resultado #4): censura da fixa só tira o evento do descritivo."""
    s = exit_struct(hp, i, e, ll - STOP_ATR * atr_d, ll + EXT * (hh - ll))
    fixed = (ex10.opt, ex10.pes) if ex10 is not None else None
    return s, fixed


def collect(hp: HLPanel, d_first: int = D_FIRST, d_last: int = D_LAST, d_struct_last: int = D_STRUCT_LAST,
            counts_only: bool = False) -> Collected:
    p = hp.p
    cols = range(d_first - p.day0, d_last - p.day0 + 1)
    mem = members(hp, cols)
    flags: dict[int, SeriesFlags] = {}
    fib = [Arm() for _ in BANDS]
    fib_ctrl: dict = {h: defaultdict(list) for h in HOLDS}
    fib_ctrl_ids: dict = defaultdict(list)
    struct, fixed_same, struct_entries = [], [], []
    lta = {t: {"A": Arm(), "B": Arm()} for t in TOLS}
    lta_ctrl: dict = {t: {h: defaultdict(list) for h in HOLDS} for t in TOLS}
    counts: dict[str, int] = defaultdict(int)
    delays: list[int] = []
    for d in cols:
        dd, e = d - cols.start, d + 1
        for i in mem[d]:
            i = int(i)
            if i not in flags:
                flags[i] = scan_series(hp, i)
            f = flags[i]
            bands_ev = f.fib_ev[:, d]
            ctrl = bool(f.fib_ctrl[d])
            lt = {t: f.lta[t][:, d] for t in TOLS}
            if not (bands_ev.any() or ctrl or any(v.any() for v in lt.values())):
                continue
            for b in np.flatnonzero(bands_ev):
                counts[f"fib_band{b}_raw"] += 1
            for t in TOLS:
                counts[f"lta{t}_A_raw"] += int(lt[t][0])
                counts[f"lta{t}_B_raw"] += int(lt[t][1])
            if np.isnan(p.open[i, e]):
                counts["no_entry_open"] += 1
                continue
            if counts_only:
                continue
            ex = {h: exit_fixed(p, i, e, h) for h in HOLDS}
            if ex[10] is not None:
                delays.append(ex[10].delay)
            elif bands_ev.any() or ctrl or any(v.any() for v in lt.values()):
                counts["censored_h10"] += 1
            coin = base(p.ids[i])
            for h in HOLDS:
                r = ex[h]
                if r is None:
                    continue
                for b in np.flatnonzero(bands_ev):
                    fib[b].events[h].append((dd, r.opt, r.pes))
                    fib[b].coins[h].append(coin)
                if ctrl:
                    fib_ctrl[h][dd].append((r.opt, r.pes))
                for t in TOLS:
                    a_ev, b_ev, c_ev = lt[t]
                    for key, flag in (("A", a_ev), ("B", b_ev)):
                        if flag:
                            lta[t][key].events[h].append((dd, r.opt, r.pes))
                            lta[t][key].coins[h].append(coin)
                    if c_ev:
                        lta_ctrl[t][h][dd].append((r.opt, r.pes))
            if ctrl:
                fib_ctrl_ids[dd].append(i)
            if bands_ev[MAIN] and d + p.day0 <= d_struct_last:
                s, fixed = structural_row(hp, i, e, f.sw_h[d], f.sw_l[d], f.atr[d], ex[10])
                if s is not None:
                    struct.append((dd, s.opt, s.pes, s.m, coin))
                    fixed_same.append(fixed)
                    struct_entries.append(e)
                else:
                    counts["struct_censored"] += 1
    struct_ctrl: dict[int, list[tuple[float, float]]] = {}
    for k, (dd, _, _, m, _) in enumerate(struct):
        outs = [exit_fixed(p, j, struct_entries[k], m) for j in fib_ctrl_ids.get(dd, [])]
        struct_ctrl[k] = [(o.opt, o.pes) for o in outs if o is not None]
    counts["series_scanned"] = len(flags)
    return Collected(fib, fib_ctrl, fib_ctrl_ids, struct, struct_ctrl, fixed_same, lta, lta_ctrl, dict(counts),
                     delays, len(cols), SPLIT - d_first)


def lookahead_real(rows, trading, hp: HLPanel, sample_cols: list[int]) -> list[str]:
    """Para colunas de sinal d sorteadas: painel só com velas de abertura ≤ d → mesmo universo e mesmas bandeiras em d."""
    p = hp.p
    bad = []
    for d in sample_cols:
        cut = build_hl_panel([r for r in rows if r[1] <= p.day0 + d], trading, today=p.day0 + d + 1, day0=p.day0,
                             day_end=p.day0 + p.close.shape[1] - 1)
        u_full = members(hp, range(d, d + 1))[d]
        u_cut = members(cut, range(d, d + 1))[d]
        if [base(p.ids[i]) for i in u_full] != [base(cut.p.ids[i]) for i in u_cut]:
            bad.append(f"{d}: universo")
            continue
        for i_f, i_c in zip(u_full, u_cut, strict=True):
            a, b = scan_series(hp, int(i_f)), scan_series(cut, int(i_c))
            same = np.array_equal(a.fib_ev[:, d], b.fib_ev[:, d]) and a.fib_ctrl[d] == b.fib_ctrl[d]
            same = same and all(np.array_equal(a.lta[t][:, d], b.lta[t][:, d]) for t in TOLS)
            if not same:
                bad.append(f"{d}: {base(p.ids[int(i_f)])}")
    return bad
