"""h036 — desenho sequencial em grupo da H-036: gasto de alfa Lan-DeMets tipo O'Brien-Fleming, unilateral.

* ``obf_spent(t, α)`` = 2·(1 − Φ(z_{1−α/2} / √t)): alfa acumulado gasto até a fração de informação ``t``;
* ``boundaries``: as fronteiras de eficácia em z para as frações dadas, por Monte Carlo do movimento browniano
  (Z_k = W(t_k)/√t_k; correlação √(t_j/t_k)), resolvidas em sequência para que a probabilidade de cruzar pela
  primeira vez na consulta k seja o alfa gasto entre k−1 e k;
* ``cluster_mean_se``: média por trade (razão Σr/Σn) e EP agrupado por dia (CR1), a estatística da H-036.

Sem scipy: Φ e Φ⁻¹ vêm de ``statistics.NormalDist``. Estatística em float.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import NormalDist

import numpy as np

N = NormalDist()


def obf_spent(t: float, alpha: float) -> float:
    if t <= 0:
        return 0.0
    z = N.inv_cdf(1 - alpha / 2)
    return 2.0 * (1.0 - N.cdf(z / np.sqrt(min(t, 1.0))))


def brownian_z(ts: Sequence[float], *, drift: float, n_sim: int, seed: int) -> np.ndarray:
    """Z_k = (drift·t_k + W(t_k)) / √t_k para ``n_sim`` caminhos; ``drift`` = θ·√I_max (z esperado no fim)."""
    rng = np.random.default_rng(seed)
    t = np.asarray(ts, dtype=float)
    inc = rng.standard_normal((n_sim, len(t))) * np.sqrt(np.diff(np.concatenate([[0.0], t])))
    w = np.cumsum(inc, axis=1)
    return (drift * t + w) / np.sqrt(t)


def boundaries(ts: Sequence[float], *, alpha: float, n_sim: int, seed: int) -> list[float]:
    z = brownian_z(ts, drift=0.0, n_sim=n_sim, seed=seed)
    alive = np.ones(n_sim, dtype=bool)
    out: list[float] = []
    prev = 0.0
    for k, t in enumerate(ts):
        spend = obf_spent(t, alpha) - prev
        prev = obf_spent(t, alpha)
        need = int(round(spend * n_sim))  # caminhos que devem cruzar aqui pela primeira vez
        zk = np.sort(z[alive, k])[::-1]
        b = float(zk[need - 1]) if need >= 1 else float(zk[0] + 1e-9)
        if k == 0 and need < 50:  # cauda rara demais para a simulação: a primeira fronteira é exata
            b = N.inv_cdf(1 - spend)
        out.append(b)
        alive &= z[:, k] < b
    return out


def cluster_mean_se(r: np.ndarray, day: np.ndarray) -> tuple[float, float]:
    """Média por trade e EP agrupado por dia (CR1: fator G/(G−1)); exige ≥ 2 dias."""
    labels, inv = np.unique(day, return_inverse=True)
    g = len(labels)
    sums = np.bincount(inv, weights=r, minlength=g)
    cnt = np.bincount(inv, minlength=g).astype(float)
    m = float(sums.sum() / cnt.sum())
    res = sums - m * cnt
    se = float(np.sqrt(g / (g - 1) * np.sum(res**2)) / cnt.sum())
    return m, se


def _betacf(a: float, b: float, x: float) -> float:
    """Fração contínua da beta incompleta (Lentz modificado; Numerical Recipes §6.4)."""
    tiny, qab, qap, qam = 1e-300, a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c; c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c; c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    """Beta incompleta regularizada I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x)
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(ln) * _betacf(a, b, x) / a
    return 1.0 - math.exp(ln) * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, df: int) -> float:
    """CDF exata da t de Student: 1 − ½·I_{ν/(ν+t²)}(ν/2, ½) para t ≥ 0."""
    v = float(df)
    tail = 0.5 * _betai(v / 2.0, 0.5, v / (v + t * t))
    return 1.0 - tail if t >= 0 else tail


def t_quantile(p: float, df: int) -> float:
    """Quantil EXATO da t (bisseção sobre ``t_cdf``; erro < 1e-9). Substitui a expansão de Cornish-Fisher, que na
    cauda 0,9995 com 4 gl dava 8,187 em vez de 8,610 (Astra, rodada 2 da H-036)."""
    if p == 0.5:
        return 0.0
    if p < 0.5:
        return -t_quantile(1.0 - p, df)
    lo, hi = 0.0, 1.0
    while t_cdf(hi, df) < p:
        hi *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


def t_boundary(b_z: float, df: int) -> float:
    """A fronteira z convertida para t(gl) com a mesma probabilidade de cauda (correção de amostra pequena)."""
    return t_quantile(N.cdf(b_z), df)
