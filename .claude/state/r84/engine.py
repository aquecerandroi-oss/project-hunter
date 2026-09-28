"""R84 — universo ponto-no-tempo, sinal de série temporal, alvos dos braços e a carteira semanal com custo.

Tudo o que decide a semana T lê só colunas < T (volume) e ≤ T−2 (preço do sinal); a vela de domingo (T−1) entra no
volume, nunca no preço do sinal (uma barra de folga, bloco H-024). Os desfechos (abertura de T e de T+7, fim de série)
só entram em `simulate`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from panel import Panel

TOP = 20
MIN_N = 15
MIN_AGE = 35  # dias listados em T−1 d
VOL_WINDOW = 30
ALIVE_LOOKBACK = 14  # "listado em T−1 d" = teve vela real em [T−14, T−1] (coerente com a quebra de 14 d)
COST = 0.0015


@dataclass(frozen=True)
class Week:
    t: int
    idx: np.ndarray  # séries elegíveis (no top-N e com as duas velas do sinal)
    m: np.ndarray  # retorno de `lookback` dias até o fecho de sábado
    vol: np.ndarray  # soma do quote_volume em [T−30, T−1]
    n: int
    top_ids: tuple[int, ...]  # o top-N antes da elegibilidade (auditoria)


def listed(p: Panel, t: int) -> np.ndarray:
    """Listado há ≥ 35 d em T−1 d e não excluído — só datas, sem preço."""
    lo = max(t - ALIVE_LOOKBACK, 0)
    alive = np.any(~np.isnan(p.close[:, lo:t]), axis=1)
    return (~p.excluded) & (p.first <= t - 1 - MIN_AGE) & alive


def week(p: Panel, t: int, lookback: int = 14, top: int = TOP) -> Week:
    cand = np.flatnonzero(listed(p, t))
    vol = np.nansum(p.qvol[cand, max(t - VOL_WINDOW, 0) : t], axis=1)
    order = sorted(range(cand.size), key=lambda k: (-vol[k], p.ids[cand[k]]))[:top]
    top_ids = cand[order]
    d = t - 2  # vela de sábado: fecha em T − 1 d
    c_d = p.close[top_ids, d]
    c_b = p.close[top_ids, d - lookback]
    ok = ~np.isnan(c_d) & ~np.isnan(c_b)
    idx = top_ids[ok]
    m = c_d[ok] / c_b[ok] - 1.0
    return Week(t, idx, m, vol[order][ok], int(idx.size), tuple(int(i) for i in top_ids))


def targets(wk: Week, arm: str, min_n: int = MIN_N) -> dict[int, float]:
    if wk.n < min_n:
        return {}
    if arm == "ew":
        return {int(i): 1.0 / wk.n for i in wk.idx}
    if arm == "ts":
        return {int(i): 1.0 / wk.n for i, m in zip(wk.idx, wk.m, strict=True) if m > 0}
    if arm == "cs":
        k = math.ceil(wk.n / 3)
        order = sorted(range(wk.n), key=lambda j: (-wk.m[j], -wk.vol[j]))[:k]
        return {int(wk.idx[j]): 1.0 / k for j in order}
    raise ValueError(arm)


def coin_week(p: Panel, i: int, t: int, bound: str, cost: float) -> tuple[float, bool]:
    """Retorno da moeda i de abertura de T até abertura de T+7; (r, saiu por fim de série)."""
    t1 = t + 7
    last = int(p.last[i])
    if p.ended[i] and last < t1:
        if bound == "pes":
            return -1.0, True
        p0 = p.open_ff[i, t] if last >= t else p.close[i, last]
        return (p.close[i, last] / p0) * (1 - cost) - 1.0, True
    return p.open_ff[i, t1] / p.open_ff[i, t] - 1.0, False


def simulate(
    p: Panel, ts: list[int], plan: list[dict[int, float]], bound: str, cost: float = COST
) -> tuple[np.ndarray, dict[str, float]]:
    """Retorno líquido semanal: (1 − custo·Σ|w_novo − w_efetivo|)·(1 + Σ w·r) − 1; caixa rende 0."""
    w_eff: dict[int, float] = {}
    out = np.empty(len(ts))
    events = 0
    turnover = 0.0
    frozen = 0
    for k, (t, plan_t) in enumerate(zip(ts, plan, strict=True)):
        # sem vela real em T: não se negocia (Astra R84 #3) — posição fica pela marca carregada, compra nova vira caixa
        stuck = {i: w for i, w in w_eff.items() if np.isnan(p.open[i, t])}
        frozen += len(stuck)
        tgt = {i: w for i, w in plan_t.items() if not np.isnan(p.open[i, t]) and i not in stuck}
        room = 1.0 - sum(stuck.values())
        tot = sum(tgt.values())
        if tot > room > 0:
            tgt = {i: w * room / tot for i, w in tgt.items()}
        tgt.update(stuck)
        keys = set(tgt) | set(w_eff)
        tv = sum(abs(tgt.get(i, 0.0) - w_eff.get(i, 0.0)) for i in keys)
        turnover += tv
        gross = 0.0
        grown: dict[int, float] = {}
        for i, w in tgt.items():
            r, gone = coin_week(p, i, t, bound, cost)
            if not math.isfinite(r):
                raise ValueError(f"retorno não finito: {p.ids[i]} em col {t}")
            gross += w * r
            if gone:
                events += 1
            else:
                grown[i] = w * (1.0 + r)
        value = 1.0 + gross
        out[k] = (1.0 - cost * tv) * value - 1.0
        w_eff = {i: v / value for i, v in grown.items()} if value > 0 else {}
    return out, {"delist_events": events, "turnover": turnover, "frozen": frozen}
