# R79 — H-019: aceleração de compra na fita da decisão. Lógica pura (sem IO de rede).
import csv
import json
import os
from datetime import datetime

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace(" ", "T"))
    if d.tzinfo is None:
        raise ValueError(f"instante sem fuso: {s}")
    return d


def accel(win: dict | None, key: str = "buy_sol") -> float | None:
    """(x10/10) ÷ (x60/60) = 6·x10/x60, lido do derivado congelado. Ausente (janela não coberta,
    derivado recusado, x60 = 0) → None, nunca zero."""
    if not win:
        return None
    w10, w60 = win.get("10s") or {}, win.get("60s") or {}
    if key not in w10 or key not in w60:
        return None
    x10, x60 = float(w10[key]), float(w60[key])
    if x60 <= 0:
        return None
    return 6.0 * x10 / x60


def peak_le_cost(r: dict) -> bool | None:
    """'Pico ≤ custo' (T4.92): real high_water_sol ≤ initial_risk_sol; papel high_water_x ≤ 1
    (high_water_x = maior marca líquida ÷ sol gasto). Sem marca → None."""
    if r["lane"] == "real":
        if not r["hw_sol"]:
            return None
        return float(r["hw_sol"]) <= float(r["cost_sol"])
    if not r["hw_x"]:
        return None
    return float(r["hw_x"]) <= 1.0


def load(path: str | None = None) -> list[dict]:
    with open(path or os.path.join(HERE, "cache", "pop.csv"), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["winj"] = json.loads(r["win"]) if r["win"] else None
        r["has_tape"] = bool(r["tape_as_of"])
        r["resolved"] = bool(r["exit_at"]) and r["pnl_sol"] != "" and r["status"] == "closed" and r["oq"] != "indeterminate"
    return rows


def first_per_mint(rows: list[dict]) -> list[dict]:
    """Uma decisão por mint: a primeira no tempo (features_end_time); empate → real, depois entrada."""
    rows = sorted(rows, key=lambda r: (ts(r["features_end_time"]), r["lane"] != "real", ts(r["entry_at"]), r["bet_id"]))
    first: dict[str, dict] = {}
    for r in rows:
        first.setdefault(r["mint"], r)
    return list(first.values())


def complete(r: dict, *, no_gaps: bool = False) -> bool:
    if not r["has_tape"] or r["tape_reason"] or accel(r["winj"]) is None:
        return False
    return not (no_gaps and int(r["gaps"] or 0) > 0)


def tertile_idx(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Tercis de posto: baixo ≤ q1/3, alto > q2/3; empates sempre juntos."""
    c1, c2 = np.quantile(x, [1 / 3, 2 / 3])
    return np.flatnonzero(x <= c1), np.flatnonzero(x > c2), float(c1), float(c2)


def extremes_idx(x: np.ndarray, q: float) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Vizinhos do corte: baixo ≤ Q(q), alto > Q(1−q)."""
    lo, hi = np.quantile(x, [q, 1 - q])
    return np.flatnonzero(x <= lo), np.flatnonzero(x > hi), float(lo), float(hi)
