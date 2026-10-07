"""R88 (H-031) — contraste ajustado por conjunto, bootstraps de mint e de dia, planalto e veredito.

Emenda de 07/10 00:36Z (revisão da Astra): o D decisório é
D_adj = Σ_s w_s · (média de r no braço baixo − média no braço alto) dentro do conjunto s,
w_s ∝ unidades do conjunto, só conjuntos com suporte nos dois braços (medido pela variável).
Os pesos ficam fixos nas réplicas; réplica que esvazia um braço de um conjunto suportado é
inválida e contada. p = P[D* − D̂ ≥ D̂] (bootstrap centrado, unilateral).
Estatística em float (docs/RESEARCH.md, Numerário).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

LIMITE = "LIMITE"
CONFIRMA = "CONFIRMA"
REFUTA = "REFUTA"
NAO = "NÃO CONFIRMA"


@dataclass(frozen=True)
class Units:
    y: np.ndarray
    low: np.ndarray
    s: np.ndarray
    mint: np.ndarray
    day: np.ndarray

    def take(self, mask: np.ndarray) -> Units:
        return Units(self.y[mask], self.low[mask], self.s[mask], self.mint[mask], self.day[mask])


@dataclass(frozen=True)
class Boot:
    d: float
    lo: float
    hi: float
    p: float
    invalid: float


def supported_sets(u: Units, *, min_per_arm: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in sorted(set(u.s.tolist())):
        m = u.s == s
        n_low, n_high = int((u.low & m).sum()), int((~u.low & m).sum())
        if n_low >= min_per_arm and n_high >= min_per_arm:
            out[str(s)] = n_low + n_high
    return out


def _weights(w: Mapping[str, int]) -> tuple[list[str], np.ndarray]:
    names = sorted(w)
    raw = np.array([w[k] for k in names], float)
    return names, raw / raw.sum()


def _group_index(u: Units, names: Sequence[str]) -> np.ndarray:
    """Índice conjunto*2 + braço (0 = baixo, 1 = alto); −1 fora dos conjuntos suportados."""
    pos = {k: i for i, k in enumerate(names)}
    si = np.array([pos.get(str(s), -1) for s in u.s], int)
    g = si * 2 + (~u.low).astype(int)
    g[si < 0] = -1
    return g


def _d_from(g: np.ndarray, y: np.ndarray, wt: np.ndarray, ws: np.ndarray) -> tuple[float, float] | None:
    k = len(ws) * 2
    keep = g >= 0
    num = np.bincount(g[keep], weights=(wt * y)[keep], minlength=k)
    den = np.bincount(g[keep], weights=wt[keep], minlength=k)
    if np.any(den <= 0):
        return None
    means = (num / den).reshape(-1, 2)
    return float(ws @ (means[:, 0] - means[:, 1])), float(ws @ means[:, 0])


def adjusted(u: Units, w: Mapping[str, int]) -> tuple[float, float]:
    """(D_adj, nível ajustado do braço baixo). NaN quando não há conjunto suportado."""
    if not w:
        return math.nan, math.nan
    names, ws = _weights(w)
    res = _d_from(_group_index(u, names), u.y, np.ones(len(u.y)), ws)
    return (math.nan, math.nan) if res is None else res


def bootstrap(u: Units, w: Mapping[str, int], *, by: str, reps: int, seed: int) -> Boot:
    d_hat, _ = adjusted(u, w)
    if not w or not math.isfinite(d_hat):
        return Boot(math.nan, math.nan, math.nan, math.nan, 1.0)
    names, ws = _weights(w)
    g = _group_index(u, names)
    keys = u.mint if by == "mint" else u.day
    uniq, inv = np.unique(keys.astype(str), return_inverse=True)
    rng = np.random.default_rng(seed)
    out = np.empty(reps)
    bad = 0
    for i in range(reps):
        cnt = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))
        res = _d_from(g, u.y, cnt[inv].astype(float), ws)
        if res is None:
            out[i] = np.nan
            bad += 1
        else:
            out[i] = res[0]
    ok = out[np.isfinite(out)]
    if len(ok) == 0:
        return Boot(d_hat, math.nan, math.nan, math.nan, 1.0)
    lo, hi = np.percentile(ok, [2.5, 97.5])
    p = float(np.mean(ok - d_hat >= d_hat))
    return Boot(d_hat, float(lo), float(hi), p, bad / reps)


def plateau(points: Sequence[tuple[float, float, bool]], *, min_run: int = 4, min_clear: int = 2) -> str:
    """points = (D, IC inferior, avaliável) na ordem da grade."""
    ev = [(d, lo) for d, lo, ok in points if ok and math.isfinite(d)]
    if len(ev) < min_run:
        return "não avaliável"
    run = clear = 0
    for d, lo in ev:
        if d > 0:
            run += 1
            clear += lo > 0
            if run >= min_run and clear >= min_clear:
                return "planalto"
        else:
            run = clear = 0
    return "pico" if any(d > 0 for d, _ in ev) else "ausente"


def halves(days: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ks = sorted(set(days.astype(str).tolist()))
    first = set(ks[: math.ceil(len(ks) / 2)])
    m = np.array([str(d) in first for d in days], bool)
    return m, ~m


def holm(ps: Mapping[str, float]) -> dict[str, float]:
    order = sorted(ps, key=lambda k: ps[k])
    m = len(order)
    out: dict[str, float] = {}
    run = 0.0
    for i, k in enumerate(order):
        run = max(run, min(1.0, (m - i) * ps[k]))
        out[k] = run
    return out


def verdict(
    *,
    limit: str | None,
    invalid: float,
    d: float,
    lo_m: float,
    hi_m: float,
    lo_d: float,
    hi_d: float,
    p_holm: float,
    level: float,
    shape: str,
    halves_pos: bool,
    days_each_arm_ok: bool,
    mre: float,
) -> str:
    if limit is not None:
        return LIMITE
    if invalid > 0.01 or not all(math.isfinite(x) for x in (d, lo_m, hi_m, lo_d, hi_d)):
        return NAO
    if (
        d >= mre and d > 0 and lo_m > 0 and lo_d > 0 and p_holm < 0.05 and level > 0
        and shape == "planalto" and halves_pos
    ):
        return CONFIRMA
    if max(hi_m, hi_d) < mre and days_each_arm_ok:
        return REFUTA
    return NAO
