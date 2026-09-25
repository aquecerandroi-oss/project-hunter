# R78 — H-015: SOL comprado por outras carteiras no slot REAL da criação. Lógica pura.
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

DUMP_SELLERS, DUMP_WINDOW_S = 10, 300


def sol_in_create_slot(cb: dict, slot: int | None) -> tuple[float | None, str]:
    """`sol_others` da entrada de `early_slots` com o slot real; ausente e ≤ maior slot listado → 0
    (nenhuma troca de outra carteira nesse slot desde a assinatura); depois do maior listado → não resolvida."""
    es = cb.get("early_slots") or []
    if slot is None:
        return None, "no_slot"
    if not es:
        return None, "no_early_slots"
    for e in es:
        if int(e["slot"]) == int(slot):
            return float(e["sol_others"]), "match"
    if int(slot) <= max(int(e["slot"]) for e in es):
        return 0.0, "absent_zero"
    return None, "after_listed"


def tertiles(vals: list[float]) -> tuple[list[int], list[int], tuple[float, float]]:
    """Índices do tercil baixo (≤ q1/3) e alto (> q2/3), por posto; empates sempre juntos."""
    a = np.asarray(vals, dtype=float)
    c1, c2 = np.quantile(a, [1 / 3, 2 / 3])
    return [i for i, v in enumerate(a) if v <= c1], [i for i, v in enumerate(a) if v > c2], (float(c1), float(c2))


def coordinated_dump(sells: list[tuple[datetime, int, str]], entry: datetime, our: str) -> tuple[bool, int]:
    """≥ 10 vendedoras distintas (sem a nossa carteira) num mesmo slot com block_time em [entrada, entrada + 300 s]."""
    end = entry + timedelta(seconds=DUMP_WINDOW_S)
    per: dict[int, set[str]] = defaultdict(set)
    for bt, slot, trader in sells:
        if entry <= bt <= end and trader != our:
            per[slot].add(trader)
    worst = max((len(v) for v in per.values()), default=0)
    return worst >= DUMP_SELLERS, worst
