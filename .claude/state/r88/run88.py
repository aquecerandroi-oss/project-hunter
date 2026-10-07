"""R88 (H-031) — análise exatamente como pré-registada + emenda de 00:36Z.

Entradas: cache/eligible.csv (congelada 00:39:40Z, sha256 18dcd185…) e cache/outcomes.csv
(lida 00:40:00Z). Saída no stdout (h031.txt).
"""

from __future__ import annotations

import csv
import math
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from stats88 import (  # noqa: E402
    CONFIRMA,
    LIMITE,
    NAO,
    REFUTA,
    Units,
    adjusted,
    bootstrap,
    halves,
    holm,
    plateau,
    supported_sets,
    verdict,
)

REPS = 10_000
SEED = 20261007
MRE = 0.05
THR = {"A": 0.12216842020537061, "B": 0.35}
GRIDS = {
    "A": (0.10128969511707292, 0.11523434542508668, 0.12216842020537061, 0.13064277622410203, 0.1478777578808908),
    "B": (0.2, 0.25, 0.3, 0.35, 0.4, 0.45),
}
MIN_SET = 5
ATA_PP = 0.0186


def load() -> list[dict[str, object]]:
    out_rows = {r["bet_id"]: r for r in csv.DictReader(open(HERE / "cache" / "outcomes.csv", encoding="utf-8"))}
    rows: list[dict[str, object]] = []
    for r in csv.DictReader(open(HERE / "cache" / "eligible.csv", encoding="utf-8")):
        o = out_rows.get(r["bet_id"])
        row: dict[str, object] = dict(r)
        row["share_f"] = float(r["share"])
        row["day"] = r["proposed_at"][:10]
        if o is None:
            row["cls"] = "sem_linha"
        elif o["status"] != "closed" or not o["exit_at"]:
            row["cls"] = "aberta"
        elif o["outcome_quality"] == "indeterminate":
            row["cls"] = "indeterminate"
        elif o["pnl_sol"] and o["sol_spent"]:
            row["cls"] = "measured"
            row["pnl"] = Decimal(o["pnl_sol"])
            row["y"] = float(Decimal(o["pnl_sol"]) / Decimal(o["sol_spent"]))
        else:
            row["cls"] = "sem_pnl"
        if o is not None:
            row["exit_reason"] = o["exit_reason"]
            row["fee_pct"] = o["fee_pct"]
        rows.append(row)
    return rows


def to_units(rows: list[dict[str, object]], thr: float, s1: bool = False) -> Units:
    keep = [r for r in rows if r["cls"] == "measured" or (s1 and r["cls"] == "indeterminate")]
    y = np.array([float(r["y"]) if r["cls"] == "measured" else -1.0 for r in keep])
    return Units(
        y=y,
        low=np.array([float(r["share_f"]) <= thr for r in keep], bool),
        s=np.array([r["rs"] for r in keep], object),
        mint=np.array([r["mint"] for r in keep], object),
        day=np.array([r["day"] for r in keep], object),
    )


def evaluable(u: Units) -> bool:
    hi = ~u.low
    return (
        u.low.sum() >= 20 and hi.sum() >= 20 and len(set(u.mint[u.low])) >= 8 and len(set(u.mint[hi])) >= 8
        and bool(supported_sets(u, min_per_arm=MIN_SET))
    )


def analyse(m: str, rows: list[dict[str, object]], s1: bool) -> dict[str, object]:
    u = to_units(rows, THR[m], s1)
    hi = ~u.low
    limit = None
    if len(u.y) < 100:
        limit = f"{len(u.y)} unidades < 100"
    elif hi.sum() < 30:
        limit = f"{int(hi.sum())} no braço excluído < 30"
    elif len(set(u.day)) < 8:
        limit = f"{len(set(u.day))} dias < 8"
    elif min(len(set(u.mint[u.low])), len(set(u.mint[hi]))) < 8:
        limit = "< 8 mints num braço"
    w = supported_sets(u, min_per_arm=MIN_SET)
    d, level = adjusted(u, w)
    bm = bootstrap(u, w, by="mint", reps=REPS, seed=SEED)
    bd = bootstrap(u, w, by="day", reps=REPS, seed=SEED)
    curve = []
    for g in GRIDS[m]:
        ug = to_units(rows, g, s1)
        wg = supported_sets(ug, min_per_arm=MIN_SET)
        ok = evaluable(ug)
        bg = bootstrap(ug, wg, by="mint", reps=REPS, seed=SEED) if ok else None
        curve.append((g, bg.d if bg else adjusted(ug, wg)[0], bg.lo if bg else math.nan, bg.hi if bg else math.nan,
                      ok, int(ug.low.sum()), int((~ug.low).sum())))
    shape = plateau([(c[1], c[2], c[4]) for c in curve])
    f, s = halves(u.day)
    half = []
    for mask in (f, s):
        uh = u.take(mask)
        half.append(adjusted(uh, supported_sets(uh, min_per_arm=MIN_SET))[0])
    halves_pos = all(math.isfinite(h) and h > 0 for h in half)
    days_ok = len(set(u.day[u.low])) >= 8 and len(set(u.day[hi])) >= 8
    pooled = float(u.y[u.low].mean() - u.y[hi].mean()) if u.low.any() and hi.any() else math.nan
    per_set = []
    for k in sorted(set(u.s.tolist())):
        mk = u.s == k
        lo_y, hi_y = u.y[mk & u.low], u.y[mk & hi]
        per_set.append((k, len(lo_y), len(hi_y), lo_y.mean() if len(lo_y) else math.nan,
                        hi_y.mean() if len(hi_y) else math.nan, k in w))
    return dict(u=u, limit=limit, w=w, d=d, level=level, bm=bm, bd=bd, curve=curve, shape=shape,
                half=half, halves_pos=halves_pos, days_ok=days_ok, pooled=pooled, per_set=per_set,
                p=max(bm.p, bd.p) if limit is None else 1.0)


def label(res: dict[str, object], p_holm: float) -> str:
    bm, bd = res["bm"], res["bd"]
    return verdict(limit=res["limit"], invalid=max(bm.invalid, bd.invalid), d=res["d"], lo_m=bm.lo, hi_m=bm.hi,
                   lo_d=bd.lo, hi_d=bd.hi, p_holm=p_holm, level=res["level"], shape=res["shape"],
                   halves_pos=res["halves_pos"], days_each_arm_ok=res["days_ok"], mre=MRE)


def show(m: str, tag: str, res: dict[str, object], p_holm: float, lab: str) -> None:
    u, bm, bd = res["u"], res["bm"], res["bd"]
    print(f"\n--- {m} · {tag} ---")
    print(f"unidades {len(u.y)} (baixo {int(u.low.sum())}, alto {int((~u.low).sum())}) · mints {len(set(u.mint))} · "
          f"dias {len(set(u.day))} · limite: {res['limit']}")
    print(f"conjuntos suportados (pesos ∝ unidades): {res['w']}")
    print(f"D_adj = {res['d']:+.4f} · nível ajustado do braço baixo {res['level']:+.4f} · D agrupado {res['pooled']:+.4f}")
    print(f"IC mint [{bm.lo:+.4f}; {bm.hi:+.4f}] p {bm.p:.4f} inválidas {100*bm.invalid:.2f}% · "
          f"IC dia [{bd.lo:+.4f}; {bd.hi:+.4f}] p {bd.p:.4f} inválidas {100*bd.invalid:.2f}%")
    print(f"p decisório (maior) {res['p']:.4f} · Holm {p_holm:.4f}")
    print(f"metades D_adj {res['half'][0]:+.4f} / {res['half'][1]:+.4f} · ≥ 8 dias em cada braço: {res['days_ok']}")
    print("curva: " + " | ".join(
        f"{g:.4f}: D {d:+.4f} [{lo:+.4f}; {hi:+.4f}] {'ok' if ok else 'n/a'} ({nl}/{nh})"
        for g, d, lo, hi, ok, nl, nh in res["curve"]) + f" → {res['shape']}")
    print("por conjunto (n baixo, n alto, média baixo, média alto, suportado): " + "; ".join(
        f"{k} {a}/{b} {ma:+.3f}/{mb:+.3f}{'' if sup else ' (fora)'}" for k, a, b, ma, mb, sup in res["per_set"]))
    print(f"RÓTULO ({tag}): {lab}")


def secondary(m: str, rows: list[dict[str, object]]) -> None:
    closed = [r for r in rows if r["cls"] in ("measured", "indeterminate")]
    rng = np.random.default_rng(SEED)
    hi = np.array([float(r["share_f"]) > THR[m] for r in closed])
    mints = np.array([r["mint"] for r in closed], object)
    uniq, inv = np.unique(mints.astype(str), return_inverse=True)
    meas = np.array([r["cls"] == "measured" for r in closed])
    for name, flag, base in (
        ("golpe (saída creator_dump), fechadas", [r.get("exit_reason") == "creator_dump" for r in closed], None),
        ("perda ≥ 50 %, só measured (correção Astra: denominador = measured)",
         [r["cls"] == "measured" and float(r["y"]) <= -0.5 for r in closed], meas),
        ("indeterminate, fechadas", [r["cls"] == "indeterminate" for r in closed], None),
    ):
        x = np.array(flag, float)
        if base is not None:  # restringe ao denominador declarado
            closed_b = [r for r, b in zip(closed, base) if b]
            x = x[base]
            hi_b, inv_b = hi[base], inv[base]
        else:
            closed_b, hi_b, inv_b = closed, hi, inv
        hi, inv, hi_all, inv_all = hi_b, inv_b, hi, inv
        r_hi, r_lo = x[hi].mean(), x[~hi].mean()
        diffs = []
        for _ in range(2000):
            cnt = np.bincount(rng.integers(0, len(uniq), len(uniq)), minlength=len(uniq))[inv].astype(float)
            a, b = (cnt * hi).sum(), (cnt * ~hi).sum()
            if a > 0 and b > 0:
                diffs.append((cnt * x * hi).sum() / a - (cnt * x * ~hi).sum() / b)
        lo, up = np.percentile(diffs, [2.5, 97.5])
        ratio = r_hi / r_lo if r_lo > 0 else math.inf
        print(f"  {name}: alto {int(x[hi].sum())}/{int(hi.sum())} = {100*r_hi:.1f}% · baixo {int(x[~hi].sum())}/"
              f"{int((~hi).sum())} = {100*r_lo:.1f}% · razão {ratio:.2f}× · alto − baixo {100*(r_hi-r_lo):+.1f} pp "
              f"IC mint [{100*lo:+.1f}; {100*up:+.1f}]")
        hi, inv = hi_all, inv_all


def main() -> None:
    rows = load()
    print("R88 — H-031 · lista congelada sha256 18dcd185… (00:39:40Z) · desfechos lidos 00:40:00Z")
    for m in ("A", "B"):
        rm = [r for r in rows if r["medida"] == m]
        print(f"[{m}] classes: {dict(Counter(str(r['cls']) for r in rm))} · fee_pct: {dict(Counter(str(r.get('fee_pct')) for r in rm))}")
        hi = [r for r in rm if float(r["share_f"]) > THR[m]]
        lo = [r for r in rm if float(r["share_f"]) <= THR[m]]
        print(f"[{m}] censura por braço — alto: {dict(Counter(str(r['cls']) for r in hi))} · baixo: {dict(Counter(str(r['cls']) for r in lo))}")
    res = {(m, s1): analyse(m, [r for r in rows if r["medida"] == m], s1) for m in ("A", "B") for s1 in (False, True)}
    labels: dict[str, str] = {}
    for s1 in (False, True):
        ph = holm({m: float(res[(m, s1)]["p"]) for m in ("A", "B")})
        for m in ("A", "B"):
            lab = label(res[(m, s1)], ph[m])
            show(m, "S1 (indeterminate = −1)" if s1 else "primário (measured)", res[(m, s1)], ph[m], lab)
            labels[f"{m}{'_s1' if s1 else ''}"] = lab
    final = {}
    for m in ("A", "B"):
        a, b = labels[m], labels[m + "_s1"]
        if a == LIMITE:
            final[m] = LIMITE
        elif a == b and a in (CONFIRMA, REFUTA):
            final[m] = a
        else:
            final[m] = NAO
    if CONFIRMA in final.values():
        fam = CONFIRMA
    elif all(v == REFUTA for v in final.values()):
        fam = REFUTA
    else:
        fam = NAO
    print(f"\nRÓTULO POR MEDIDA (primário e S1 têm de concordar): {final}")
    print(f"RÓTULO H-031 (família, emenda item 5): {fam}{' — limite de dado em ' + ', '.join(k for k, v in final.items() if v == LIMITE) if LIMITE in final.values() else ''}")
    print("\n=== secundária (não decide): taxas por braço, todas as apostas fechadas (measured + indeterminate) ===")
    for m in ("A", "B"):
        print(f"[{m}] limiar {THR[m]:.4f}")
        secondary(m, [r for r in rows if r["medida"] == m])
    print("\n=== descritivo ===")
    for m in ("A", "B"):
        rm = [r for r in rows if r["medida"] == m]
        money = sum((r["pnl"] for r in rm if r["cls"] == "measured"), Decimal(0))
        u = res[(m, False)]["u"]
        print(f"[{m}] Σ pnl_sol (measured, Decimal) {money} SOL · média r baixo {u.y[u.low].mean():+.4f} alto {u.y[~u.low].mean():+.4f}"
              f" · nível ajustado com ATA {res[(m, False)]['level'] - ATA_PP:+.4f}")
        # uma unidade por mint (a mais antiga entre conjuntos)
        first: dict[str, dict[str, object]] = {}
        for r in sorted((r for r in rm if r["cls"] == "measured"), key=lambda r: str(r["proposed_at"])):
            first.setdefault(str(r["mint"]), r)
        uf = to_units(list(first.values()), THR[m])
        wf = supported_sets(uf, min_per_arm=MIN_SET)
        print(f"[{m}] uma por mint: n {len(uf.y)} · D_adj {adjusted(uf, wf)[0]:+.4f} · D agrupado "
              f"{uf.y[uf.low].mean() - uf.y[~uf.low].mean():+.4f}")
        if m == "A":
            print("[A] sem criador como maior comprador: não avaliável (o pedigree_e2b não grava is_creator)")
            continue
        nc = [r for r in rm if r.get("is_creator") == "false"]
        un = to_units(nc, THR[m])
        print(f"[{m}] sem criador como maior comprador: n {len(un.y)} · D_adj {adjusted(un, supported_sets(un, min_per_arm=MIN_SET))[0]:+.4f}")


if __name__ == "__main__":
    main()
