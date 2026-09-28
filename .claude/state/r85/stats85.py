"""R85 — inferência congelada (emenda 3): calendário completo, S_d/N_d por dia, D* = ΣS*/ΣN* por blocos móveis contíguos.

Holm vem do moinho (`infra.research.stats.adjust_family`); o bootstrap é escrito aqui, como no R84, porque o do moinho
reamostra grupos rotulados e não blocos móveis concatenados e truncados.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from infra.research.stats import adjust_family

SEED = 20260928
REPS = 10_000
MIN_EVENTS = 150
MIN_COVER = 40


def day_sums(days: np.ndarray, x: np.ndarray, n_days: int) -> tuple[np.ndarray, np.ndarray]:
    s = np.bincount(days, weights=x, minlength=n_days).astype(float)
    n = np.bincount(days, minlength=n_days).astype(np.int64)
    return s, n


def mbb_idx(n: int, block: int, reps: int = REPS, seed: int = SEED) -> np.ndarray:
    """(reps, n): ⌈n/b⌉ blocos contíguos com início uniforme em [0, n − b], concatenados e truncados em n."""
    k = -(-n // block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(reps, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, k * block)
    return idx[:, :n].astype(np.int32)


def boot_d(s: np.ndarray, n: np.ndarray, idx: np.ndarray, chunk: int = 1000) -> tuple[np.ndarray, int]:
    num = np.concatenate([s[idx[c : c + chunk]].sum(axis=1) for c in range(0, idx.shape[0], chunk)])
    den = np.concatenate([n[idx[c : c + chunk]].sum(axis=1) for c in range(0, idx.shape[0], chunk)])
    ok = den > 0
    return num[ok] / den[ok], int((~ok).sum())


def summarize(s: np.ndarray, n: np.ndarray, idx: np.ndarray) -> dict[str, float]:
    est = float(s.sum() / n.sum()) if n.sum() else float("nan")
    d_star, dropped = boot_d(s, n, idx)
    lo, hi = np.percentile(d_star, [2.5, 97.5])
    diff = d_star - est
    p = float((np.sum(diff >= est) + 1) / (diff.size + 1))
    return {"d": est, "lo": float(lo), "hi": float(hi), "p": p, "dropped": dropped}


def coverage(days: np.ndarray, width: int) -> int:
    """Intervalos NÃO sobrepostos de `width` dias (ancorados no dia 0 da janela) com ≥ 1 evento."""
    return int(np.unique(np.asarray(days) // width).size)


def holm(ps: list[float]) -> list[float]:
    return list(adjust_family(ps).holm_adjusted)


def arm_verdict(bounds: list[dict], holm_p: list[float], mre: float, plateau: bool, split: bool, k6: bool,
                min_events: int = MIN_EVENTS, min_cover: int = MIN_COVER) -> str:
    """`bounds` = [otimista, pessimista], cada um com d, lo, hi, level, n, cov; `holm_p` na mesma ordem."""
    if any(b["n"] < min_events or b["cov"] < min_cover for b in bounds):
        return "LIMITE DE DADO"
    if k6:  # o braço é de uma moeda só: NÃO CONFIRMA, nem REFUTA (Astra, resultado #3)
        return "NÃO CONFIRMA"
    confirms = all(b["d"] >= mre and b["lo"] > 0 and hp < 0.05 and b["level"] > 0
                   for b, hp in zip(bounds, holm_p, strict=True))
    if confirms and plateau and split:
        return "CONFIRMA"
    if all(b["hi"] < mre for b in bounds):
        return "REFUTA"
    return "NÃO CONFIRMA"
