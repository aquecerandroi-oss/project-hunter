"""R84 — bootstrap de blocos móveis contíguos (8 semanas), p unilateral centrado e o veredito da H-024.

Holm vem do moinho (`infra.research.stats.adjust_family`); o bootstrap é escrito aqui porque o do moinho reamostra
grupos rotulados, não blocos móveis sobrepostos concatenados e truncados como o bloco congelado pede.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from infra.research.stats import adjust_family  # noqa: E402

SEED = 20260928
REPS = 10_000
BLOCK = 8
MIN_WEEKS = 200


def mbb_indices(n: int, block: int = BLOCK, reps: int = REPS, seed: int = SEED) -> np.ndarray:
    """(reps, n): ⌈n/b⌉ blocos contíguos com início uniforme em [0, n−b], concatenados e truncados em n."""
    k = -(-n // block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(reps, k))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, k * block)
    return idx[:, :n]


def boot_means(d: np.ndarray, idx: np.ndarray) -> np.ndarray:
    return np.asarray(d)[idx].mean(axis=1)


def ci(d: np.ndarray, idx: np.ndarray) -> tuple[float, float]:
    lo, hi = np.percentile(boot_means(d, idx), [2.5, 97.5])
    return float(lo), float(hi)


def p_centered(d: np.ndarray, idx: np.ndarray) -> float:
    """p unilateral de H0: D ≤ 0, com a distribuição do bootstrap centrada na estimativa."""
    est = float(np.mean(d))
    diff = boot_means(d, idx) - est
    return float((np.sum(diff >= est) + 1) / (diff.size + 1))


def summarize(d: np.ndarray, idx: np.ndarray) -> dict[str, float]:
    lo, hi = ci(d, idx)
    return {"n": int(d.size), "d": float(np.mean(d)), "lo": lo, "hi": hi, "p": p_centered(d, idx), "sd": float(np.std(d, ddof=1))}


def _confirms(s: dict, p_holm: float, mre: float) -> bool:
    return bool(s["d"] >= mre and s["lo"] > 0 and p_holm < 0.05 and s["level"] > 0 and s["plateau"] and s["split"])


def bound_verdicts(prim: list[dict], sec: list[dict], mre: float) -> list[dict[str, object]]:
    out = []
    for a, b in zip(prim, sec, strict=True):
        fam = adjust_family([a["p"], b["p"]])
        out.append({"holm_ts": fam.holm_adjusted[0], "holm_cs": fam.holm_adjusted[1],
                    "confirma": _confirms(a, fam.holm_adjusted[0], mre), "refuta": bool(a["hi"] < mre)})
    return out


def holm_verdict(prim: list[dict], sec: list[dict], mre: float) -> str:
    """Primária nos dois limites de deslistagem; `sec` só precisa do p (família de Holm)."""
    if any(s["n"] < MIN_WEEKS for s in prim):
        return "LIMITE DE DADO"
    per = bound_verdicts(prim, sec, mre)
    if all(v["confirma"] for v in per):
        return "CONFIRMA"
    if all(v["refuta"] for v in per):
        return "REFUTA"
    return "NÃO CONFIRMA"
