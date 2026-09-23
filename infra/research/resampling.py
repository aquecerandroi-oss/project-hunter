"""Reamostragem: bootstrap de cluster, bootstrap de blocos e permutação estratificada.

Separado de `stats.py` só pelo orçamento de 350 linhas por módulo; a API pública
continua a ser `infra.research.stats`, que reexporta tudo o que está aqui.

Os três estimadores partilham a mesma aritmética -- somas por grupo, depois
reamostragem de GRUPOS inteiros -- e diferem no que tratam como trocável:
cluster (mint/mercado) no R65/R67, bloco temporal (dia/hora) no R68/R69.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from infra.research.stats_core import REPS, contrast

_CHUNK_CELLS = 2_000_000  # limite de células (reps x grupos) por bloco de bootstrap


# ------------------------------------------------------------------------- bootstraps


@dataclass(frozen=True)
class Interval:
    """IC 95 % de D, a fração de reamostragens com D ≤ 0 e o suporte que o sustenta.

    `groups_selected`/`groups_rest` existem por causa de um contraexemplo da Astra
    (revisão da T4.87): oito clusters no total, **um só** com linhas selecionadas, e o
    IC saía `[1,0; 1,0]` porque 689 de 2 000 réplicas eram descartadas por não conterem
    esse cluster. Contar clusters no total não protege um braço sustentado por um
    episódio; `invalid` publica quantas réplicas foram descartadas.
    """

    lo: float
    hi: float
    p_le0: float
    groups: int
    groups_selected: int = 0
    groups_rest: int = 0
    invalid: float = 0.0


def _group_sums(
    outcome: np.ndarray, selected: np.ndarray, group: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(outcome, dtype=np.float64)
    sel = np.asarray(selected, dtype=bool)
    _, gid = np.unique(np.asarray(group), return_inverse=True)
    k = int(gid.max()) + 1
    s_sel = np.bincount(gid[sel], weights=y[sel], minlength=k)
    n_sel = np.bincount(gid[sel], minlength=k).astype(np.float64)
    s_oth = np.bincount(gid[~sel], weights=y[~sel], minlength=k)
    n_oth = np.bincount(gid[~sel], minlength=k).astype(np.float64)
    return s_sel, n_sel, s_oth, n_oth


def _resample_diff(sums: tuple[np.ndarray, ...], reps: int, seed: int) -> np.ndarray:
    s_sel, n_sel, s_oth, n_oth = sums
    k = s_sel.size
    rng = np.random.default_rng(seed)
    per = max(1, _CHUNK_CELLS // max(k, 1))
    out: list[np.ndarray] = []
    done = 0
    while done < reps:
        m = min(per, reps - done)
        draw = rng.integers(0, k, size=(m, k))
        ns = n_sel[draw].sum(1)
        no = n_oth[draw].sum(1)
        ok = (ns > 0) & (no > 0)
        d = np.full(m, np.nan)
        d[ok] = s_sel[draw].sum(1)[ok] / ns[ok] - s_oth[draw].sum(1)[ok] / no[ok]
        out.append(d)
        done += m
    return np.concatenate(out)


def to_interval(
    diffs: np.ndarray,
    groups: int,
    n_sel: np.ndarray | None = None,
    n_oth: np.ndarray | None = None,
) -> Interval:
    """IC pelos percentis das réplicas válidas, com o suporte por braço declarado."""
    gs = 0 if n_sel is None else int((n_sel > 0).sum())
    go = 0 if n_oth is None else int((n_oth > 0).sum())
    total = int(diffs.size)
    d = diffs[np.isfinite(diffs)]
    invalid = 0.0 if total == 0 else float((total - d.size) / total)
    if d.size < 100:
        return Interval(float("nan"), float("nan"), float("nan"), groups, gs, go, invalid)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return Interval(float(lo), float(hi), float((d <= 0).mean()), groups, gs, go, invalid)


def cluster_bootstrap(
    outcome: np.ndarray,
    selected: np.ndarray,
    cluster: Sequence[object],
    *,
    reps: int = REPS,
    seed: int = 0,
) -> Interval:
    """IC 95 % de D reamostrando **clusters inteiros** (mint, mercado).

    Motivo (R65): várias apostas partilham a mesma moeda e o mesmo destino de mercado;
    reamostrar linhas independentes subestima o erro.
    """
    sums = _group_sums(outcome, selected, np.asarray(cluster, dtype=object))
    return to_interval(_resample_diff(sums, reps, seed), sums[0].size, sums[1], sums[3])


def block_bootstrap(
    outcome: np.ndarray,
    selected: np.ndarray,
    block: Sequence[object],
    *,
    reps: int = REPS,
    seed: int = 0,
) -> Interval:
    """IC 95 % de D reamostrando **blocos temporais** (dia, hora) — R68/R69.

    Aritmeticamente é o mesmo estimador do bootstrap de cluster; o que muda é o que se
    trata como trocável. Para série temporal o bloco é o dia, nunca a linha.
    """
    sums = _group_sums(outcome, selected, np.asarray(block, dtype=object))
    return to_interval(_resample_diff(sums, reps, seed), sums[0].size, sums[1], sums[3])


# ------------------------------------------------------------------------ permutação


def permutation_p(
    outcome: np.ndarray,
    selected: np.ndarray,
    stratum: Sequence[object] | None = None,
    *,
    reps: int = REPS,
    seed: int = 0,
) -> float:
    """p bilateral por permutação dos rótulos **dentro de cada estrato** (R67).

    Sem estrato, é a permutação global do R65. Com estrato = dia, o efeito de dia é
    preservado sob o nulo — sem isso um dia bom com muitos selecionados vira "sinal".
    """
    y = np.asarray(outcome, dtype=np.float64)
    sel = np.asarray(selected, dtype=bool)
    obs = contrast(y, sel)
    if not np.isfinite(obs):
        return float("nan")
    ids = np.zeros(y.size, dtype=np.int64) if stratum is None else _codes(stratum)
    rng = np.random.default_rng(seed)
    total = float(y.sum())
    n = y.size
    per = max(1, _CHUNK_CELLS // max(n, 1))
    hits = 0
    done = 0
    while done < reps:
        m = min(per, reps - done)
        s_sum = np.zeros(m)
        s_n = np.zeros(m)
        for g in np.unique(ids):
            idx = np.flatnonzero(ids == g)
            lab = np.repeat(sel[idx].astype(np.float64)[None, :], m, axis=0)
            perm = rng.permuted(lab, axis=1)
            s_sum += perm @ y[idx]
            s_n += perm.sum(1)
        ok = (s_n > 0) & (s_n < n)
        d = np.full(m, np.nan)
        d[ok] = s_sum[ok] / s_n[ok] - (total - s_sum[ok]) / (n - s_n[ok])
        hits += int(np.sum(np.abs(d[ok]) >= abs(obs) - 1e-15))
        done += m
    return (hits + 1) / (reps + 1)


def _codes(values: Sequence[object]) -> np.ndarray:
    _, inv = np.unique(np.asarray(values, dtype=object), return_inverse=True)
    return inv.astype(np.int64)
