"""R68 — os cinco preditores fixos do pré-registo (E1.5). Todas as leituras passam
por `Bars.take`, que levanta `LookAheadError` se a fonte fechar depois da decisão."""

from __future__ import annotations

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from load68 import Bars

Z_LOOKBACK = 20
TC_LOOKBACK = 60
BREAKOUT_LOOKBACK = 20
WARMUP = TC_LOOKBACK + 1  # a maior janela + 1

PREDICTORS = ("P1_mom_prev", "P2_revert_z", "P3_vol_surge", "P4_taker_imb", "P6_breakout20")


def _back_ok(bs: np.ndarray, h: int, lag: int) -> np.ndarray:
    """True em i se as barras i-lag..i forem contíguas na grelha."""
    ok = np.zeros(bs.size, dtype=bool)
    if bs.size > lag:
        ok[lag:] = (bs[lag:] - bs[:-lag]) == lag * h
    return ok


def _roll(x: np.ndarray, win: int, fn) -> np.ndarray:
    """fn sobre [i-win, i-1]; NaN antes do warm-up."""
    out = np.full(x.size, np.nan)
    if x.size > win:
        out[win:] = fn(sliding_window_view(x[:-1], win), axis=-1)
    return out


def compute(bars: Bars) -> dict[str, np.ndarray]:
    """Devolve máscaras booleanas de entrada por índice de decisão, mais diagnósticos.

    O índice `i` é a barra que acabou de fechar; a decisão acontece em
    `bars.close_time[i]`; nenhuma feature lê índice > i.
    """
    n = len(bars)
    i = np.arange(n)
    if n <= WARMUP + 2:
        return {p: np.zeros(n, dtype=bool) for p in PREDICTORS} | {"eligible": np.zeros(n, dtype=bool)}

    close = bars.take(bars.close, i, i)
    prev_close = np.full(n, np.nan)
    prev_close[1:] = bars.take(bars.close, i[:-1], i[1:])
    r_prev = close / prev_close - 1.0
    r_prev[~_back_ok(bars.bucket_start, bars.h, 1)] = np.nan

    mu = _roll(r_prev, Z_LOOKBACK, np.nanmean)
    sd = _roll(r_prev, Z_LOOKBACK, np.nanstd)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (r_prev - mu) / sd
    z[~np.isfinite(z)] = np.nan

    tc = bars.take(bars.trade_count, i, i)
    tc_med = _roll(tc, TC_LOOKBACK, np.nanmedian)
    with np.errstate(invalid="ignore", divide="ignore"):
        surge = tc / tc_med
    surge[~np.isfinite(surge)] = np.nan

    vol = bars.take(bars.volume, i, i)
    tb = bars.take(bars.taker_buy, i, i)
    with np.errstate(invalid="ignore", divide="ignore"):
        imb = tb / vol
    imb[~np.isfinite(imb)] = np.nan

    hmax = _roll(bars.take(bars.high, i, i), BREAKOUT_LOOKBACK, np.nanmax)

    # elegível = warm-up cumprido E a corrida de 61 barras é contígua
    eligible = _back_ok(bars.bucket_start, bars.h, WARMUP) & np.isfinite(r_prev)
    return {
        "eligible": eligible,
        "P1_mom_prev": eligible & (r_prev > 0.0),
        "P2_revert_z": eligible & np.isfinite(z) & (z < -2.0),
        "P3_vol_surge": eligible & np.isfinite(surge) & (surge > 2.0),
        "P4_taker_imb": eligible & np.isfinite(imb) & (imb > 0.55),
        "P6_breakout20": eligible & np.isfinite(hmax) & (close > hmax),
        "_r_prev": r_prev,
        "_z": z,
        "_surge": surge,
        "_imb": imb,
    }
