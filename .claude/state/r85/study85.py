"""R85 — eventos e controles do mesmo dia no universo ponto-no-tempo, saídas executáveis e contraste x_e.

Sinal no fechamento da vela d (final em d + 1 00:00 UTC); compra na abertura REAL de e = d + 1; venda na primeira
abertura real em ou depois de e + H (emenda 2). Fim de série antes disso → dois limites (último fecho / perda total).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from data85 import HLPanel, universe
from geom85 import BANDS, fib_scan, lta_scan, wilder_atr
from panel import Panel

COST = 0.0015
TOLS = (0.15, 0.25, 0.35)
CAP = 60
STOP_ATR = 0.5
EXT = 1.618


@dataclass(frozen=True)
class Exit:
    opt: float
    pes: float
    delay: int = 0  # dias além de e + H até a primeira abertura real
    m: int = 0  # (estrutural) o controle sai na abertura de e + m
    gone: bool = False


def _net(ratio: float) -> float:
    return ratio * (1 - COST) ** 2 - 1


def exit_fixed(p: Panel, i: int, e: int, hold: int) -> Exit | None:
    """None = sem abertura real em e (não compra) ou dado acabou com a série ainda viva (censura, contada fora)."""
    if e >= p.open.shape[1] or np.isnan(p.open[i, e]):
        return None
    p0 = p.open[i, e]
    last = int(p.last[i])
    for col in range(e + hold, last + 1):
        if not np.isnan(p.open[i, col]):
            r = _net(p.open[i, col] / p0)
            return Exit(r, r, col - e - hold)
    if p.ended[i]:
        return Exit(_net(p.close[i, last] / p0), -1.0, gone=True)
    return None


def exit_struct(hp: HLPanel, i: int, e: int, stop: float, tgt: float, cap: int = CAP) -> Exit | None:
    p = hp.p
    if e >= p.open.shape[1] or np.isnan(p.open[i, e]):
        return None
    p0 = p.open[i, e]
    last = int(p.last[i])
    for col in range(e, last + 1):
        o = p.open[i, col]
        if np.isnan(o):
            continue
        j = col - e
        if j >= cap:
            return Exit(_net(o / p0), _net(o / p0), m=j)
        if o <= stop or o >= tgt:  # a abertura decide antes dos extremos da vela (Astra, resultado #2)
            px, m = o, j
        elif hp.low[i, col] <= stop:  # stop e alvo na mesma vela: stop primeiro
            px, m = stop, j + 1
        elif hp.high[i, col] >= tgt:
            px, m = tgt, j + 1
        else:
            continue
        return Exit(_net(px / p0), _net(px / p0), m=m)
    if p.ended[i]:
        return Exit(_net(p.close[i, last] / p0), -1.0, m=last - e + 1, gone=True)
    return None


@dataclass
class Contrast:
    days: np.ndarray
    opt: np.ndarray
    pes: np.ndarray
    lvl_opt: np.ndarray  # r do evento (nível)
    lvl_pes: np.ndarray
    coins: list[str]
    dropped_no_control: int


def contrast(events: list[tuple], controls: dict[int, list[tuple[float, float]]], coins: list[str] | None = None) -> Contrast:
    """events = [(dia, r_opt, r_pes)]; controls[dia] = [(r_opt, r_pes)]. x = r − média dos controles do dia."""
    days, xo, xp, lo_, lp_, cs = [], [], [], [], [], []
    dropped = 0
    for k, (d, ro, rp) in enumerate(events):
        ctl = controls.get(d, [])
        if not ctl:
            dropped += 1
            continue
        co = float(np.mean([c[0] for c in ctl]))
        cp = float(np.mean([c[1] for c in ctl]))
        days.append(d)
        xo.append(ro - co)
        xp.append(rp - cp)
        lo_.append(ro)
        lp_.append(rp)
        cs.append(coins[k] if coins else "")
    return Contrast(np.array(days, dtype=np.int64), np.array(xo), np.array(xp), np.array(lo_), np.array(lp_), cs, dropped)


# ------------------------------------------------------------------------------ varredura por série


@dataclass
class SeriesFlags:
    fib_ev: np.ndarray  # (bandas, D) no calendário
    fib_ctrl: np.ndarray
    sw_h: np.ndarray
    sw_l: np.ndarray
    atr: np.ndarray
    lta: dict[float, np.ndarray]  # tol → (3, D): A, B, controle


def scan_series(hp: HLPanel, i: int) -> SeriesFlags:
    p = hp.p
    cols = np.flatnonzero(~np.isnan(p.close[i]))
    h, lo, c = hp.high[i, cols], hp.low[i, cols], p.close[i, cols]
    atr = wilder_atr(h, lo, c)
    d = p.close.shape[1]
    fs = fib_scan(h, lo, c, atr)
    fib_ev = np.zeros((len(BANDS), d), dtype=bool)
    fib_ev[:, cols] = np.vstack(fs.events)
    fib_ctrl = np.zeros(d, dtype=bool)
    fib_ctrl[cols] = fs.ctrl
    sw_h, sw_l, atr_c = (np.full(d, np.nan) for _ in range(3))
    sw_h[cols], sw_l[cols], atr_c[cols] = fs.swing_h, fs.swing_l, atr
    lta = {}
    for tol in TOLS:
        arr = np.zeros((3, d), dtype=bool)
        arr[:, cols] = lta_scan(h, lo, c, atr, tol=tol).flags()
        lta[tol] = arr
    return SeriesFlags(fib_ev, fib_ctrl, sw_h, sw_l, atr_c, lta)


def signal_days(p: Panel, d_first: int, d_last: int) -> range:
    return range(d_first - p.day0, d_last - p.day0 + 1)


def members(hp: HLPanel, cols: range) -> dict[int, np.ndarray]:
    """Universo na abertura e = d + 1 para cada coluna de sinal d."""
    return {d: universe(hp.p, d + 1) for d in cols}
