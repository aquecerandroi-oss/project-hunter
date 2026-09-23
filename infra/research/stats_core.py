"""Núcleo numérico do moinho: médias, quantis, o contraste orientado e a seleção.

Separado de `stats.py` só pelo orçamento de 350 linhas por módulo. A API pública
é `infra.research.stats`, que reexporta tudo o que está aqui.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

REPS = 10_000


# --------------------------------------------------------------------------- básicos


def mean(xs: Sequence[float]) -> float:
    return float(np.mean(xs)) if len(xs) else float("nan")


def median(xs: Sequence[float]) -> float:
    return float(np.median(xs)) if len(xs) else float("nan")


def quantile(xs: Sequence[float], q: float) -> float:
    """Quantil por posto mais próximo — a mesma definição do R67 (`stats67.pct`)."""
    if not len(xs):
        return float("nan")
    s = sorted(xs)
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return float(s[i])


def contrast(outcome: np.ndarray, selected: np.ndarray) -> float:
    """D = média(selecionados) − média(resto). NaN se um dos lados é vazio."""
    sel = np.asarray(selected, dtype=bool)
    if not sel.any() or sel.all():
        return float("nan")
    y = np.asarray(outcome, dtype=np.float64)
    return float(y[sel].mean() - y[~sel].mean())


def select(values: Sequence[float | None], threshold: float, direction: str) -> np.ndarray:
    """Máscara já orientada pela direção da hipótese. Ausente nunca é selecionado."""
    if direction not in ("low", "high"):
        raise ValueError(f"direção desconhecida: {direction!r} (use 'low' ou 'high')")
    if direction == "low":
        return np.array([v is not None and v <= threshold for v in values], dtype=bool)
    return np.array([v is not None and v > threshold for v in values], dtype=bool)
