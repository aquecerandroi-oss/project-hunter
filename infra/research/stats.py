"""Estatística do moinho — o que os R65/R67/R68/R69 usaram, destilado e testado.

Tudo aqui roda em **float**: os contrastes são médias de retornos (~1e-2) e o erro de
Monte Carlo do bootstrap domina qualquer erro de representação. Dinheiro somado para
publicação é `Decimal` e vive em `protocol.py`/`report.py`, nunca aqui.

Convenção única, para a previsão pré-registada ser sempre "D > 0":
`D = média(selecionados) − média(resto)`, com `selecionados` já orientado pela direção
da hipótese (ver `select`).

Este módulo é a porta de entrada: `stats_core` (básicos) e `resampling` (bootstraps e
permutação) existem só para caber no orçamento de 350 linhas e são reexportados aqui.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from infra.research.resampling import (
    Interval,
    block_bootstrap,
    cluster_bootstrap,
    permutation_p,
    to_interval,
)
from infra.research.stats_core import REPS, contrast, mean, median, quantile, select

__all__ = [
    "REPS",
    "Bucket",
    "CurvePoint",
    "Family",
    "Interval",
    "Shape",
    "adjust_family",
    "block_bootstrap",
    "bucket_table",
    "check_grid",
    "cluster_bootstrap",
    "contrast",
    "mean",
    "median",
    "permutation_p",
    "plateau_or_spike",
    "quantile",
    "quantile_buckets",
    "select",
    "terciles",
    "threshold_curve",
]


# ---------------------------------------------------------------------------- baldes


@dataclass(frozen=True)
class Bucket:
    """Um balde de um contraste descritivo."""

    label: str
    n: int
    mean: float
    median: float
    indices: tuple[int, ...]


def quantile_buckets(values: Sequence[float], k: int) -> list[tuple[str, tuple[int, ...]]]:
    """Corta em `k` baldes por quantil — cortes do R65 (`.claude/state/r65/stats.py`)."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    n = len(order)
    out: list[tuple[str, tuple[int, ...]]] = []
    for j in range(k):
        idx = order[j * n // k : (j + 1) * n // k]
        if idx:
            out.append((f"{values[idx[0]]:.4g}..{values[idx[-1]]:.4g}", tuple(idx)))
    return out


def bucket_table(
    values: Sequence[float | None], outcome: Sequence[float], edges: Sequence[float]
) -> list[Bucket]:
    """Baldes `(-inf, e0], (e0, e1], ..., (en, +inf)` — a tabela do R67.

    Um valor ausente (`None`) **não** cai no primeiro balde: fica de fora. É o bug que o
    R69 apanhou (ausente virando percentil zero) posto como regra.
    """
    bounds = [(-np.inf, edges[0])]
    bounds += [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]
    bounds += [(edges[-1], np.inf)]
    out: list[Bucket] = []
    for lo, hi in bounds:
        idx = tuple(i for i, v in enumerate(values) if v is not None and lo < v <= hi)
        if not idx:
            continue
        ys = [float(outcome[i]) for i in idx]
        label = f"{'' if lo == -np.inf else f'{lo:g}'}-{'inf' if hi == np.inf else f'{hi:g}'}"
        out.append(Bucket(label, len(idx), mean(ys), median(ys), idx))
    return out


def terciles(values: Sequence[float | None]) -> tuple[float, float] | None:
    xs = sorted(v for v in values if v is not None)
    if len(xs) < 6:
        return None
    return (float(xs[len(xs) // 3]), float(xs[2 * len(xs) // 3]))


# ------------------------------------------------------------- múltiplas comparações


@dataclass(frozen=True)
class Family:
    """Uma família congelada de hipóteses e o que sobra dela."""

    p: tuple[float, ...]
    bh_threshold: tuple[float, ...]
    bh_adjusted: tuple[float, ...]
    bh_survives: tuple[bool, ...]
    holm_adjusted: tuple[float, ...]
    holm_survives: tuple[bool, ...]


def adjust_family(p: Sequence[float], *, q: float = 0.10, alpha: float = 0.05) -> Family:
    """Benjamini-Hochberg (FDR `q`) e Holm (familiar `alpha`) sobre a **mesma** família.

    O R68 (E1.8) fixou a divisão de trabalho: BH é reportado, **Holm é quem confirma**,
    porque a pergunta "existe pelo menos uma vantagem" é controlo familiar, não FDR.
    """
    m = len(p)
    if m == 0:
        return Family((), (), (), (), (), ())
    ps = list(map(float, p))
    bad = [v for v in ps if not np.isfinite(v) or v < 0.0 or v > 1.0]
    if bad:
        raise ValueError(
            f"p fora de [0, 1] ou não finito na família: {bad}. Um p ausente NÃO pode "
            "entrar como zero nem ser omitido em silêncio — decida a política de "
            "ausência no pré-registo (achado da Astra, T4.87)."
        )
    order = sorted(range(m), key=lambda i: ps[i])
    thr = [0.0] * m
    bh_adj = [0.0] * m
    holm_adj = [0.0] * m
    run = 1.0
    for rank in range(m - 1, -1, -1):
        i = order[rank]
        run = min(run, min(1.0, m / (rank + 1) * ps[i]))
        bh_adj[i] = run
        thr[i] = q * (rank + 1) / m
    run = 0.0
    for rank in range(m):
        i = order[rank]
        run = max(run, min(1.0, (m - rank) * ps[i]))
        holm_adj[i] = run
    return Family(
        p=tuple(ps),
        bh_threshold=tuple(thr),
        bh_adjusted=tuple(bh_adj),
        bh_survives=tuple(a <= q for a in bh_adj),
        holm_adjusted=tuple(holm_adj),
        holm_survives=tuple(a <= alpha for a in holm_adj),
    )


# ------------------------------------------------------------------ planalto vs pico


@dataclass(frozen=True)
class CurvePoint:
    """Um limiar da varredura."""

    threshold: float
    n_selected: int
    n_rest: int
    d: float
    ci: Interval
    evaluable: bool


@dataclass(frozen=True)
class Shape:
    """Diagnóstico planalto-vs-pico (KB-0149 §5, item 26)."""

    form: str  # "planalto" | "pico" | "ausente"
    longest_run: int
    ci_clear: int
    detail: str


def threshold_curve(
    values: Sequence[float | None],
    outcome: Sequence[float],
    cluster: Sequence[object],
    thresholds: Sequence[float],
    *,
    direction: str = "low",
    min_per_side: int = 20,
    reps: int = REPS,
    seed: int = 0,
) -> list[CurvePoint]:
    """D e IC por limiar. `direction='low'` seleciona `valor <= limiar`.

    A grelha tem de ser **estritamente crescente**: repetir o mesmo limiar quatro vezes
    satisfazia o teste de planalto sem testar nenhum vizinho (contraexemplo da Astra).
    """
    check_grid(thresholds)
    y = np.array([float(v) for v in outcome], dtype=np.float64)
    out: list[CurvePoint] = []
    for j, t in enumerate(thresholds):
        sel = select(values, float(t), direction)
        ns, nr = int(sel.sum()), int((~sel).sum())
        if ns < min_per_side or nr < min_per_side:
            out.append(
                CurvePoint(float(t), ns, nr, float("nan"), to_interval(np.array([]), 0), False)
            )
            continue
        ci = cluster_bootstrap(y, sel, cluster, reps=reps, seed=seed + j)
        out.append(CurvePoint(float(t), ns, nr, contrast(y, sel), ci, True))
    return out


def check_grid(thresholds: Sequence[float]) -> None:
    """Recusa grelha vazia, repetida ou fora de ordem."""
    xs = [float(t) for t in thresholds]
    if any(not np.isfinite(t) for t in xs):
        raise ValueError(f"grelha de limiares com valor não finito: {xs}")
    if any(b <= a for a, b in zip(xs, xs[1:], strict=False)):
        raise ValueError(
            f"grelha de limiares tem de ser estritamente crescente e sem repetição: {xs}"
        )


def plateau_or_spike(curve: Sequence[CurvePoint], *, min_run: int = 4, min_clear: int = 2) -> Shape:
    """Efeito real sobrevive a limiares vizinhos; artefato é um pico isolado.

    Planalto = `min_run` limiares **consecutivos** com D > 0, dos quais pelo menos
    `min_clear` com IC 95 % que não cobre zero.
    """
    pts = [c for c in curve if c.evaluable]
    best_run = 0
    best_clear = 0
    run = 0
    clear = 0
    for c in pts:
        if c.d > 0:
            run += 1
            clear += 1 if c.ci.lo > 0 else 0
            if run > best_run or (run == best_run and clear > best_clear):
                best_run, best_clear = run, clear
        else:
            run, clear = 0, 0
    detail = (
        f"{len(pts)} limiares avaliáveis; maior corrida positiva {best_run}"
        f" ({best_clear} com IC acima de zero)"
    )
    if best_run == 0:
        return Shape("ausente", 0, 0, detail)
    if best_run >= min_run and best_clear >= min_clear:
        return Shape("planalto", best_run, best_clear, detail)
    return Shape("pico", best_run, best_clear, detail)
