"""R83 — o p que respeita a dependência (emenda §2b.2) e a curva de partições distintas (§2b nice-to-have ii).

Puro: numpy sobre arrays. A reamostragem por mercado reusa a aritmética do moinho
(`infra.research.resampling._group_sums/_resample_diff`), só lendo a cauda das réplicas.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from infra.research.resampling import _group_sums, _resample_diff
from infra.research.stats import CurvePoint


def _codes(values: Sequence[object]) -> np.ndarray:
    _, inv = np.unique(np.asarray([str(v) for v in values], dtype=object), return_inverse=True)
    return inv.astype(np.int64)


def episode_perm_p(y: np.ndarray, sel: np.ndarray, episode: Sequence[object], stratum: Sequence[object], *,
                   reps: int = 10_000, seed: int = 0, chunk: int = 250) -> float:
    """p bilateral: rótulos alto/baixo embaralhados entre **episódios** dentro do estrato.

    Um episódio (estratégia, mercado, obs) leva todas as suas linhas juntas — as versões que decidiram a mesma
    barra não viram réplicas independentes. Um episódio com rótulos mistos é partido pelo rótulo (não acontece
    com tercis por estratégia, porque o rótulo só depende de mercado e obs).
    """
    y = np.asarray(y, float)
    sel = np.asarray(sel, bool)
    ep = _codes([f"{e}|{int(s)}" for e, s in zip(episode, sel, strict=True)])
    n_ep = int(ep.max()) + 1
    s_sum = np.bincount(ep, weights=y, minlength=n_ep)
    s_n = np.bincount(ep, minlength=n_ep).astype(float)
    lab = np.zeros(n_ep)
    lab[ep[sel]] = 1.0
    st_rows = _codes(stratum)
    st = np.zeros(n_ep, np.int64)
    st[ep] = st_rows
    total_s, total_n = s_sum.sum(), s_n.sum()

    def d_of(labels: np.ndarray) -> np.ndarray:
        a_s, a_n = labels @ s_sum, labels @ s_n
        return a_s / a_n - (total_s - a_s) / (total_n - a_n)

    obs = float(d_of(lab[None, :])[0])
    order0 = np.argsort(st, kind="stable")
    base = lab[order0]
    rng = np.random.default_rng(seed)
    hits = 0
    done = 0
    while done < reps:
        m = min(chunk, reps - done)
        keys = rng.random((m, n_ep)) + st[None, :] * 2.0  # ordena por estrato, aleatório dentro
        order = np.argsort(keys, axis=1)
        perm = np.empty((m, n_ep))
        np.put_along_axis(perm, order, np.broadcast_to(base, (m, n_ep)), axis=1)
        d = d_of(perm)
        hits += int(np.sum(np.abs(d) >= abs(obs) - 1e-15))
        done += m
    return (hits + 1) / (reps + 1)


def boot_p_two_sided(y: np.ndarray, sel: np.ndarray, cluster: Sequence[object], *, reps: int = 10_000,
                     seed: int = 0) -> float:
    """2·min(P[D* ≤ 0], P[D* ≥ 0]) nas réplicas do bootstrap por cluster do moinho (limitado a 1)."""
    sums = _group_sums(np.asarray(y, float), np.asarray(sel, bool), np.asarray(cluster, dtype=object))
    d = _resample_diff(sums, reps, seed)
    d = d[np.isfinite(d)]
    return float(min(1.0, 2 * min((d <= 0).mean(), (d >= 0).mean())))


def distinct(points: Sequence[CurvePoint]) -> list[CurvePoint]:
    """Colapsa cortes vizinhos que produziram a **mesma** partição (mesmos tamanhos e mesmo D)."""
    out: list[CurvePoint] = []
    for p in points:
        if out and (out[-1].n_selected, out[-1].n_rest, out[-1].d) == (p.n_selected, p.n_rest, p.d):
            continue
        out.append(p)
    return out
