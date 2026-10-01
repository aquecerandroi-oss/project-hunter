"""H-026 B coorte prospectiva — rompimento de topo SEM LTA (o comparador incremental).

Rompimento simples na vela t: o fechamento C_t passa a máxima H_j do pivô de alta mais recente já confirmado em t
(pivô k = 5 do R85: máxima estritamente maior que as 5 anteriores e ≥ que as 5 seguintes, conhecido só em j + 5), e é
o primeiro fechamento acima de H_j desde o pivô. Um rompimento por pivô; um pivô novo confirmado substitui o anterior.
Causal: o pivô em j só é lido a partir de t = j + k, e `pivots_high` em j usa só as máximas ≤ j + k.
"""

from __future__ import annotations

import numpy as np
from geom85 import K, pivots_high


def plain_breakout(high: np.ndarray, close: np.ndarray, k: int = K) -> np.ndarray:
    ph = pivots_high(high, k)
    out = np.zeros(close.size, dtype=bool)
    top: float | None = None
    for t in range(close.size):
        j = t - k
        if j >= 0 and ph[j]:
            top = float(high[j])  # entre j e j + k nenhum fechamento passa H_j (as máximas não passam)
        if top is not None and close[t] > top:
            out[t] = True
            top = None  # um rompimento por pivô
    return out
