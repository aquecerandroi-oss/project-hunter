"""R85 — geometria causal no diário: ATR de Wilder, pivôs, perna de Fibonacci (H-025) e LTA (H-026).

Tudo opera sobre as velas REAIS de uma série (índice comprimido, sem dias vazios) e é causal por construção: o
resultado na vela t só usa velas ≤ t. Um pivô na vela j só é usado a partir de j + k (as k velas da direita têm de
existir). `prefix_divergences` é a guarda: recalcula em cada prefixo e compara com a série inteira.
Parâmetros congelados no pré-registro (Fila de Hipoteses, H-025/H-026, 28/09/2026 13:05Z).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

K = 5
ATR_N = 14
BANDS: list[tuple[float, float]] = [(0.40, 0.518), (0.45, 0.568), (0.50, 0.618), (0.55, 0.668), (0.70, 0.818)]
CTRL_MAX_R = 0.236
MIN_AMP_ATR = 3.0


def wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = ATR_N) -> np.ndarray:
    tr = high - low
    tr[1:] = np.maximum(tr[1:], np.maximum(np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1])))
    out = np.full(high.size, np.nan)
    if high.size < n:
        return out
    out[n - 1] = tr[:n].mean()
    for t in range(n, high.size):
        out[t] = (out[t - 1] * (n - 1) + tr[t]) / n
    return out


def pivots_high(high: np.ndarray, k: int = K) -> np.ndarray:
    """Máxima estritamente maior que as k anteriores e ≥ que as k seguintes (empate fica com a mais velha)."""
    n = high.size
    out = np.zeros(n, dtype=bool)
    for j in range(k, n - k):
        out[j] = high[j] > high[j - k : j].max() and high[j] >= high[j + 1 : j + k + 1].max()
    return out


def pivots_low(low: np.ndarray, k: int = K) -> np.ndarray:
    return pivots_high(-low, k)


# ------------------------------------------------------------------------------ H-025


@dataclass
class FibScan:
    events: list[np.ndarray]  # um vetor booleano por faixa de BANDS
    ctrl: np.ndarray
    swing_h: np.ndarray  # H e L da perna viva na vela (NaN fora de perna)
    swing_l: np.ndarray

    def flags(self) -> np.ndarray:
        return np.vstack([*self.events, self.ctrl])


def fib_scan(high: np.ndarray, low: np.ndarray, close: np.ndarray, atr: np.ndarray, k: int = K,
             min_amp_atr: float = MIN_AMP_ATR, bands: Sequence[tuple[float, float]] = tuple(BANDS)) -> FibScan:
    n = close.size
    ev = [np.zeros(n, dtype=bool) for _ in bands]
    ctrl = np.zeros(n, dtype=bool)
    sh, sl = np.full(n, np.nan), np.full(n, np.nan)
    prev_ph: int | None = None
    swing: tuple[float, float, int] | None = None  # (H, L, h)
    done = [False] * len(bands)
    for t in range(n):
        j = t - k
        if j >= k and high[j] > high[j - k : j].max() and high[j] >= high[j + 1 : t + 1].max():
            swing = None  # um pivô de alta novo aposenta a perna anterior
            if prev_ph is not None and j - prev_ph >= 2 and not np.isnan(atr[j]):
                seg = low[prev_ph + 1 : j]
                li = prev_ph + 1 + int(np.argmin(seg))
                hh, ll = float(high[j]), float(low[li])
                if hh >= high[li : j + 1].max() and hh - ll >= min_amp_atr * atr[j] and close[j:t].min(initial=np.inf) >= ll:
                    swing = (hh, ll, j)
                    # emenda (1): fechamentos de h (inclusive) até a confirmação (exclusive) consomem a faixa que já passaram
                    r_prev = (hh - close[j:t]) / (hh - ll)
                    done = [bool(np.any(r_prev >= lo_b)) for lo_b, _ in bands]
            prev_ph = j
        if swing is None:
            continue
        hh, ll, _ = swing
        if close[t] < ll:
            swing = None
            continue
        sh[t], sl[t] = hh, ll
        r = (hh - close[t]) / (hh - ll)
        hit = False
        for b, (lo_b, hi_b) in enumerate(bands):
            if not done[b] and r >= lo_b:
                done[b] = True
                if r <= hi_b:
                    ev[b][t] = True
                    hit = True
        if r < CTRL_MAX_R and not hit:
            ctrl[t] = True
    return FibScan(ev, ctrl, sh, sl)


# ------------------------------------------------------------------------------ H-026


@dataclass
class _Line:
    a: int
    la: float
    b: int
    slope: float
    touches: int = 2
    last_touch: int = 0
    away: bool = False
    alive: bool = True
    pending: list[tuple[float, int]] = field(default_factory=list)  # (topo P, prazo)

    def at(self, t: int) -> float:
        return self.la + self.slope * (t - self.a)


@dataclass
class LtaScan:
    a_events: np.ndarray
    b_events: np.ndarray
    ctrl: np.ndarray

    def flags(self) -> np.ndarray:
        return np.vstack([self.a_events, self.b_events, self.ctrl])


def _tol(atr_v: float, tol: float) -> float:
    return 0.0 if np.isnan(atr_v) else tol * atr_v


def lta_scan(high: np.ndarray, low: np.ndarray, close: np.ndarray, atr: np.ndarray, k: int = K, tol: float = 0.25,
             away_atr: float = 1.0, max_age: int = 180, b_window: int = 20) -> LtaScan:
    n = close.size
    a_ev, b_ev, ctrl = (np.zeros(n, dtype=bool) for _ in range(3))
    lines: list[_Line] = []
    prev_pl: int | None = None
    for t in range(n):
        j = t - k
        if j >= k and low[j] < low[j - k : j].min() and low[j] <= low[j + 1 : t + 1].min():
            if prev_pl is not None and low[prev_pl] < low[j]:
                ln = _Line(prev_pl, float(low[prev_pl]), j, (float(low[j]) - float(low[prev_pl])) / (j - prev_pl))
                ok = all(close[u] >= ln.at(u) - _tol(atr[u], tol) for u in range(prev_pl + 1, t + 1))
                if ok:
                    ln.last_touch = j
                    ln.away = any(not np.isnan(atr[u]) and close[u] >= ln.at(u) + away_atr * atr[u] for u in range(j + 1, t))
                    lines.append(ln)
            prev_pl = j
        near_any = False
        for ln in lines:
            if not ln.alive or np.isnan(atr[t]):
                continue
            lv = ln.at(t)
            if close[t] < lv - tol * atr[t] or t - ln.b >= max_age:  # morre em b + max_age (Astra, resultado #1)
                ln.alive, ln.pending = False, []
                continue
            keep = []
            for top, deadline in ln.pending:
                if close[t] > top:
                    b_ev[t] = True
                elif t < deadline:
                    keep.append((top, deadline))
            ln.pending = keep
            near = low[t] <= lv + tol * atr[t] and close[t] >= lv
            near_any |= near
            if near and ln.away:
                ln.touches += 1
                top = float(high[ln.last_touch + 1 : t + 1].max())
                ln.last_touch, ln.away = t, False
                if ln.touches >= 3:
                    a_ev[t] = True
                    ln.pending.append((top, t + b_window))
            elif close[t] >= lv + away_atr * atr[t]:
                ln.away = True
        lines = [ln for ln in lines if ln.alive]  # linha morta não volta (só custo de CPU)
        confirmed = any(ln.touches >= 3 for ln in lines)
        ctrl[t] = confirmed and not near_any and not a_ev[t] and not b_ev[t]
    return LtaScan(a_ev, b_ev, ctrl)


# ------------------------------------------------------------------------------ guarda de antecipação


def prefix_divergences(scan: Callable, ohlc: tuple[np.ndarray, np.ndarray, np.ndarray], ts: list[int]) -> list[int]:
    """Velas t em que o resultado com a série inteira difere do resultado com só as velas ≤ t."""
    h, lo, c = ohlc
    full = scan(h, lo, c, wilder_atr(h, lo, c)).flags()
    bad = []
    for t in ts:
        cut = scan(h[: t + 1], lo[: t + 1], c[: t + 1], wilder_atr(h[: t + 1], lo[: t + 1], c[: t + 1])).flags()
        if not np.array_equal(cut[:, t], full[:, t]):
            bad.append(t)
    return bad
