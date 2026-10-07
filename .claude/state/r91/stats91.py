"""R91 (H-034) — contraste ajustado por estrato com pesos de sobreposição, bootstraps de mint e de dia, veredito.

Pré-registro + emenda 1 (Fila de Hipóteses, H-034):
D_adj = Σ_s w_s · (média r | true − média r | false) / Σ w_s,  w_s = n_true·n_false/n_s,
só estratos com os dois braços. Na réplica, os clusters sorteados entram com a sua multiplicidade,
os pesos são recalculados com ela e renormalizados nos estratos que ainda têm os dois braços;
réplica sem estrato válido é inválida. p = P[D* − D̂ ≥ D̂] (centrado, unilateral). y NaN = censurado.
Estatística em float (docs/RESEARCH.md, Numerário).
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

CONFIRMA = "CONFIRMA"
REFUTA = "REFUTA"
NAO = "NÃO CONFIRMA"
LIMITE = "LIMITE"
NAO_INSTR = "NÃO CONFIRMA — instrumento"
NAO_LIMITE = "NÃO CONFIRMA — limite de dado"


@dataclass(frozen=True)
class Units:
    y: np.ndarray  # r por SOL; NaN = censurado no cenário
    x: np.ndarray  # True = braço selecionado (variável verdadeira)
    s: np.ndarray  # estrato (conjunto × regime)
    mint: np.ndarray
    day: np.ndarray
    conj: np.ndarray  # conjunto (para o deixa-um-fora)

    def take(self, mask: np.ndarray) -> Units:
        return Units(self.y[mask], self.x[mask], self.s[mask], self.mint[mask], self.day[mask], self.conj[mask])


@dataclass(frozen=True)
class Boot:
    d: float
    lo: float
    hi: float
    basic_lo: float
    basic_hi: float
    p: float
    invalid: float


@dataclass(frozen=True)
class Scenario:
    d: float
    lo_m: float
    hi_m: float
    lo_d: float
    hi_d: float
    inv_m: float
    inv_d: float
    level: float
    halves: tuple[float, ...]
    loo: tuple[float, ...]


def supported_strata(u: Units, *, min_per_arm: int) -> set[str]:
    out: set[str] = set()
    for s in set(u.s.astype(str).tolist()):
        m = u.s.astype(str) == s
        if int((u.x & m).sum()) >= min_per_arm and int((~u.x & m).sum()) >= min_per_arm:
            out.add(s)
    return out


def _prep(u: Units) -> tuple[np.ndarray, np.ndarray, int, np.ndarray]:
    """(máscara dos não censurados, índice de grupo estrato*2+braço, nº de estratos, y limpo)."""
    keep = np.isfinite(u.y)
    _, si = np.unique(u.s.astype(str), return_inverse=True)
    k = int(si.max()) + 1 if len(si) else 0
    g = si * 2 + (~u.x).astype(int)
    return keep, g, k, np.where(keep, u.y, 0.0)


def _d_from(g: np.ndarray, y: np.ndarray, m: np.ndarray, k: int) -> tuple[float, float] | None:
    n = np.bincount(g, weights=m, minlength=2 * k).reshape(-1, 2)
    sy = np.bincount(g, weights=m * y, minlength=2 * k).reshape(-1, 2)
    ok = (n[:, 0] > 0) & (n[:, 1] > 0)
    if not ok.any():
        return None
    nt, nf = n[ok, 0], n[ok, 1]
    mt, mf = sy[ok, 0] / nt, sy[ok, 1] / nf
    w = nt * nf / (nt + nf)
    return float(w @ (mt - mf) / w.sum()), float(w @ mt / w.sum())


def adjusted(u: Units, mult: np.ndarray | None = None) -> tuple[float, float]:
    """(D_adj, nível ajustado do braço verdadeiro); NaN sem estrato com os dois braços."""
    keep, g, k, y = _prep(u)
    m = np.ones(len(y)) if mult is None else np.asarray(mult, float)
    m = np.where(keep, m, 0.0)
    res = _d_from(g, y, m, k) if k else None
    return (math.nan, math.nan) if res is None else res


def bootstrap(u: Units, *, by: str, reps: int, seed: int) -> Boot:
    d_hat, _ = adjusted(u)
    if not math.isfinite(d_hat):
        return Boot(math.nan, math.nan, math.nan, math.nan, math.nan, math.nan, 1.0)
    keep, g, k, y = _prep(u)
    keys = (u.mint if by == "mint" else u.day).astype(str)
    uniq, inv = np.unique(keys, return_inverse=True)
    rng = np.random.default_rng(seed)
    out = np.full(reps, np.nan)
    base = keep.astype(float)
    for i in range(reps):
        cnt = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq)).astype(float)
        res = _d_from(g, y, cnt[inv] * base, k)
        if res is not None:
            out[i] = res[0]
    ok = out[np.isfinite(out)]
    invalid = 1.0 - len(ok) / reps
    if len(ok) == 0:
        return Boot(d_hat, math.nan, math.nan, math.nan, math.nan, math.nan, 1.0)
    lo, hi = (float(v) for v in np.percentile(ok, [2.5, 97.5]))
    p = float(np.mean(ok - d_hat >= d_hat))
    return Boot(d_hat, lo, hi, 2 * d_hat - hi, 2 * d_hat - lo, p, invalid)


def halves_mask(days: np.ndarray, frozen_days: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    ks = sorted(set(frozen_days))
    first = set(ks[: math.ceil(len(ks) / 2)])
    m = np.array([str(d) in first for d in days], bool)
    return m, ~m


def leave_one_out(u: Units) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in sorted(set(u.conj.astype(str).tolist())):
        out[c] = adjusted(u.take(u.conj.astype(str) != c))[0]
    return out


def holm(ps: Mapping[str, float]) -> dict[str, float]:
    order = sorted(ps, key=lambda k: ps[k])
    m = len(order)
    out: dict[str, float] = {}
    run = 0.0
    for i, k in enumerate(order):
        run = max(run, min(1.0, (m - i) * ps[k]))
        out[k] = run
    return out


def _finite(*xs: float) -> bool:
    return all(math.isfinite(x) for x in xs)


def _valid(sc: Scenario) -> bool:
    return _finite(sc.d, sc.lo_m, sc.hi_m, sc.lo_d, sc.hi_d) and sc.inv_m <= 0.01 and sc.inv_d <= 0.01


def _confirms(sc: Scenario, mre: float) -> bool:
    return (
        _valid(sc)
        and sc.d >= mre and sc.d > 0 and sc.lo_m > 0 and sc.lo_d > 0
        and math.isfinite(sc.level) and sc.level > 0
        and len(sc.halves) == 2 and all(math.isfinite(h) and h > 0 for h in sc.halves)
        and len(sc.loo) > 0 and all(math.isfinite(v) and v > 0 for v in sc.loo)
    )


def _refutes(sc: Scenario, mre: float) -> bool:
    return _valid(sc) and max(sc.hi_m, sc.hi_d) < mre


def measure_verdict(
    *, instrument: str | None, limit: str | None, prim: Scenario, s1: Scenario, p_holm: float, mre: float
) -> str:
    if instrument is not None:
        return NAO_INSTR
    if limit is not None:
        return LIMITE
    if p_holm < 0.05 and _confirms(prim, mre) and _confirms(s1, mre):
        return CONFIRMA
    if _refutes(prim, mre) and _refutes(s1, mre):
        return REFUTA
    return NAO


def family_verdict(v: Mapping[str, str]) -> str:
    vals = list(v.values())
    if any(x == CONFIRMA for x in vals):
        return CONFIRMA
    if all(x == REFUTA for x in vals):
        return REFUTA
    if all(x == LIMITE for x in vals):
        return NAO_LIMITE
    return NAO
