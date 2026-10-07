"""R90 / H-033 — modelo conjunto, bootstrap por dia, Holm e o rótulo pré-registrado.

Estatística em float (médias de R ~ 1e-1); nenhum dinheiro é publicado aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SEED = 20261007
REPS = 10_000
MRE = 0.05  # R por 1 desvio robusto de x = −oi_rel7d, no modelo conjunto
MIN_UNITS, MIN_DAYS, MIN_GROUP = 150, 15, 30
CUTS = (-0.04, -0.02, 0.0, 0.02, 0.04)  # sobre x = −oi_rel7d: 1[x > c] ⇔ oi_rel7d < −c


def robust_z(x: np.ndarray) -> np.ndarray:
    """(x − mediana) ÷ (1,4826 · MAD) — escala fixada na amostra da estratégia."""
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * 1.4826
    if mad <= 0:
        raise ValueError("MAD zero: variável sem dispersão")
    return (x - med) / mad


def fit(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    """OLS com intercepto: devolve [b0, b1, …]."""
    a = np.column_stack([np.ones(len(y)), x])
    coef, *_ = np.linalg.lstsq(a, y, rcond=None)
    return coef


class Unidentified(ValueError):
    """Ajuste não identificável (não finito, MAD zero, posto incompleto): falha fechada."""


def fit_checked(y: np.ndarray, x: np.ndarray) -> np.ndarray:
    a = np.column_stack([np.ones(len(y)), x])
    if not (np.all(np.isfinite(y)) and np.all(np.isfinite(a))):
        raise Unidentified("valor não finito")
    if np.linalg.matrix_rank(a) < a.shape[1]:
        raise Unidentified("matriz de posto incompleto")
    return fit(y, x)


def day_index(days: list[str]) -> tuple[np.ndarray, list[np.ndarray]]:
    uniq = sorted(set(days))
    pos = {d: i for i, d in enumerate(uniq)}
    code = np.array([pos[d] for d in days])
    return code, [np.flatnonzero(code == i) for i in range(len(uniq))]


def cluster_boot(y: np.ndarray, x: np.ndarray, days: list[str], col: int = 1,
                 reps: int = REPS, seed: int = SEED) -> tuple[float, float, float, float, int]:
    """Bootstrap de clusters por dia UTC (reamostra dias inteiros). Devolve (β̂, IC inf, IC sup, p unilateral, inválidas).

    p unilateral do bootstrap centrado sob H0: β ≤ 0 → P(β* − β̂ ≥ β̂).
    """
    b = float(fit(y, x)[col])
    _, members = day_index(days)
    rng = np.random.default_rng(seed)
    k = len(members)
    draws, bad = [], 0
    for _ in range(reps):
        pick = rng.integers(0, k, size=k)
        idx = np.concatenate([members[i] for i in pick])
        if np.linalg.matrix_rank(np.column_stack([np.ones(idx.size), x[idx]])) < x.shape[1] + 1:
            bad += 1
            continue
        draws.append(fit(y[idx], x[idx])[col])
    d = np.asarray(draws)
    if not d.size:
        return b, float("nan"), float("nan"), 1.0, bad
    lo, hi = np.percentile(d, [2.5, 97.5])
    return b, float(lo), float(hi), float(np.mean(d - b >= b)), bad


def holm(ps: list[float]) -> list[float]:
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    m, out, running = len(ps), [0.0] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * ps[i]))
        out[i] = running
    return out


def sign_plateau(betas: list[float], partitions: list[object]) -> tuple[int, bool]:
    """Conta cortes com β > 0 entre partições distintas; patamar = ≥ 4 distintas positivas e consecutivas."""
    seen, run, best = set(), 0, 0
    for b, part in zip(betas, partitions, strict=True):
        if part in seen:
            continue
        seen.add(part)
        run = run + 1 if np.isfinite(b) and b > 0 else 0
        best = max(best, run)
    return best, best >= 4


@dataclass(frozen=True)
class Verdict:
    label: str
    clauses: dict[str, bool]


def verdict(*, n: int, days: int, n_pos: int, n_neg: int, beta: float, lo: float, hi: float, lo_m: float,
            hi_m: float, p_holm: float, level_pos: float, plateau: bool, halves: tuple[float, float],
            invalid_frac: float) -> Verdict:
    """Ordem: dado → instrumento → REFUTA (IC sup < MRE nos dois bootstraps) → CONFIRMA (todas) → NÃO CONFIRMA."""
    nums = (beta, lo, hi, lo_m, hi_m, p_holm, level_pos, *halves)
    c = {
        "dado_ok": n >= MIN_UNITS and days >= MIN_DAYS and min(n_pos, n_neg) >= MIN_GROUP,
        "instrumento_ok": all(bool(np.isfinite(v)) for v in nums) and invalid_frac <= 0.01,
        "beta>=MRE": beta >= MRE, "IC_inf>0 (dia)": lo > 0, "IC_inf>0 (mercado)": lo_m > 0,
        "Holm<0,05": p_holm < 0.05, "nivel_favoravel>0": level_pos > 0, "patamar": plateau,
        "metade1>0": halves[0] > 0, "metade2>0": halves[1] > 0,
        "IC_sup<MRE (dia)": hi < MRE, "IC_sup<MRE (mercado)": hi_m < MRE,
    }
    if not c["dado_ok"]:
        return Verdict("LIMITE DE DADO", c)
    if not c["instrumento_ok"]:
        return Verdict("LIMITE (instrumento)", c)
    if c["IC_sup<MRE (dia)"] and c["IC_sup<MRE (mercado)"]:
        return Verdict("REFUTA", c)
    keys = ("beta>=MRE", "IC_inf>0 (dia)", "IC_inf>0 (mercado)", "Holm<0,05", "nivel_favoravel>0", "patamar",
            "metade1>0", "metade2>0")
    if all(c[k] for k in keys):
        return Verdict("CONFIRMA", c)
    return Verdict("NÃO CONFIRMA", c)


def global_label(labels: list[str]) -> str:
    """Emenda 03:02Z: alguma confirma → CONFIRMA; as duas refutam → REFUTA; as duas em limite de dado → LIMITE."""
    if "CONFIRMA" in labels:
        return "CONFIRMA"
    if labels and all(x == "REFUTA" for x in labels):
        return "REFUTA"
    if labels and all(x.startswith("LIMITE") for x in labels):
        return "LIMITE"  # emenda H-033: as duas em limite, de qualquer causa (a causa sai por estratégia)
    return "NÃO CONFIRMA"
