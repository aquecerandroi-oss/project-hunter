# R82 — H-017 (EXP-M25): classificação de cada armação de recuo_v1/1 e emparelhamento com recuo_ctrl_v1/1
# na mesma (mint, t0). Lógica pura (sem IO fora de load()).
import csv
import os
from collections import Counter
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
COHORT_START = datetime.fromisoformat("2026-09-26T15:05:30+00:00")
SETTLE = timedelta(minutes=15)  # janela 60 s + max_hold 300 s + fill + folga: armações mais novas estão "em voo"

ZERO = ("no_pullback", "pullback_killed")  # não entrou → r = 0 no braço
OUT = ("pullback_censored", "pullback_dropped_cap", "pullback_not_inserted", "pullback_insert_failed",
       "pullback_insert_saturated")  # perda operacional → fora dos dois lados


def ts(s: str) -> datetime:
    s = s.strip().replace(" ", "T")
    if s.endswith("+00"):
        s += ":00"
    return datetime.fromisoformat(s)


def _resolved(status: str, pnl: str, oq: str) -> bool:
    return status == "closed" and pnl != "" and oq != "indeterminate"


def classify_arm(r: dict) -> tuple[str, float | None]:
    """(classe, r do braço por SOL decidido). A aposta manda; sem aposta, o 1.º desfecho do recuo na trilha."""
    if r["arm_bet"]:
        if r["arm_status"] != "closed" or r["arm_pnl"] == "":
            return "open", None
        if r["arm_oq"] == "indeterminate":
            return "indeterminate", None
        return "entered", float(r["arm_pnl"]) / float(r["arm_size"])
    if r["arm_prop"]:
        return "prop_no_bet", None  # proposta no banco sem aposta de papel (não preenchida)
    for item in (r["outcomes"] or "").split(" | "):
        base = item.split("@")[0].strip().split(":")[0]
        if base == "no_pullback":
            return "no_pullback", 0.0
        if base == "pullback_killed":
            return "killed", 0.0
        if base in OUT:
            return "censored", None
    return "no_outcome", None


def classify_ctl(r: dict) -> tuple[str, float | None]:
    """(classe, r do controle). Fora dos dois lados: ausente, sem fill, indeterminate, aberta."""
    if not r["ctl_prop"]:
        if r["ctl_first_fet"] and ts(r["ctl_first_fet"]) < ts(r["t0"]):
            return "absent_already_open", None  # o controle entrou no mint antes (pista de 15 s)
        return "absent", None
    if not r["ctl_bet"]:
        return "unfilled", None
    if r["ctl_status"] != "closed" or r["ctl_pnl"] == "":
        return "open", None
    if r["ctl_oq"] == "indeterminate":
        return "indeterminate", None
    return "resolved", float(r["ctl_pnl"]) / float(r["ctl_size"])


def in_population(r: dict, extracted_at: datetime) -> str:
    """'in' ou o motivo de ficar fora da população (antes de qualquer desfecho)."""
    t0 = ts(r["t0"])
    if t0 < COHORT_START:
        return "before_cohort"
    if t0 > extracted_at - SETTLE:
        return "in_flight"
    return "in"


def pair_rows(rows: list[dict]) -> tuple[list[dict], Counter]:
    """Pares resolvidos (r_braço, r_controle) e a contagem de cada motivo de exclusão."""
    pairs, why = [], Counter()
    for r in rows:
        ca, ra = classify_arm(r)
        cc, rc = classify_ctl(r)
        why[f"arm:{ca}"] += 1
        if ra is None:
            continue
        why[f"ctl:{cc}"] += 1
        if rc is None:
            continue
        pairs.append(dict(r, cls=ca, ra=ra, rc=rc))
    return pairs, why


def same_snapshot(p: dict) -> bool:
    """Os dois lados preencheram na MESMA foto (mesmo observed_at e mesmas reservas virtuais)."""
    return (p["cls"] == "entered" and p["arm_snap_at"] != "" and p["arm_snap_at"] == p["ctl_snap_at"]
            and p["arm_vsol"] == p["ctl_vsol"] and p["arm_vtok"] == p["ctl_vtok"])


def part(p: dict) -> str:
    if p["cls"] != "entered":
        return "nao_entrou"
    if not all(p[k] for k in ("arm_snap_at", "arm_vsol", "arm_vtok", "ctl_snap_at", "ctl_vsol", "ctl_vtok")):
        return "foto_desconhecida"
    return "mesma_foto" if same_snapshot(p) else "foto_posterior"


def load(path: str | None = None) -> list[dict]:
    with open(path or os.path.join(HERE, "cache", "h017.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def population(rows: list[dict]) -> tuple[list[dict], Counter]:
    ext = ts(rows[0]["extracted_at"])
    cnt = Counter(in_population(r, ext) for r in rows)
    return [r for r in rows if in_population(r, ext) == "in"], cnt
