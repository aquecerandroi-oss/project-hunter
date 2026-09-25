# R79 — H-017 (EXP-M24): classificação de cada armação do braço recuo_v1/1 e emparelhamento com a
# sombra de papel de operator/5 na mesma (mint, t0). Lógica pura.
import csv
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))

ZERO = ("no_pullback", "pullback_killed")  # não entrou → retorno 0 no braço
OUT = ("pullback_censored", "pullback_dropped_cap", "pullback_not_inserted", "pullback_insert_failed",
       "pullback_insert_saturated")  # perda operacional → fora dos dois lados


def _resolved(status: str, pnl: str, oq: str) -> bool:
    return status == "closed" and pnl != "" and oq != "indeterminate"


def classify_decision(r: dict) -> tuple[str, float | None]:
    """(classe, retorno do braço por SOL decidido). Aposta presente manda; senão o 1.º desfecho do
    recuo na trilha (recusas comuns da porta em tiques posteriores são ignoradas)."""
    if r["arm_bet"]:
        if r["arm_status"] != "closed" or r["arm_pnl"] == "":
            return "open", None
        if r["arm_oq"] == "indeterminate":
            return "indeterminate", None
        return "entered", float(r["arm_pnl"]) / float(r["arm_size"])
    for item in (r["outcomes"] or "").split(" | "):
        ref = item.split("@")[0].strip()
        base = ref.split(":")[0]
        if base == "no_pullback":
            return "no_pullback", 0.0
        if base == "pullback_killed":
            return "killed", 0.0
        if base in OUT:
            return "censored", None
    return "no_outcome", None


def control(r: dict) -> float | None:
    if r["op_bet"] and _resolved(r["op_status"], r["op_pnl"], r["op_oq"]):
        return float(r["op_pnl"]) / float(r["op_size"])
    return None


def pair_rows(rows: list[dict]) -> tuple[list[dict], Counter]:
    pairs, why = [], Counter()
    for r in rows:
        cls, ra = classify_decision(r)
        why[cls] += 1
        if ra is None:
            continue
        rc = control(r)
        if rc is None:
            why["no_control"] += 1
            continue
        pairs.append(dict(r, cls=cls, ra=ra, rc=rc))
    return pairs, why


def load(path: str | None = None) -> list[dict]:
    with open(path or os.path.join(HERE, "cache", "h017.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))
