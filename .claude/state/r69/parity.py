"""Paridade SQL <-> Python da coorte e do percentil, e medida do vazamento evitado."""
import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from cohort import Row, live_cohort, percentile


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


groups: dict[str, list[Row]] = defaultdict(list)
meta: dict[str, tuple[str, datetime]] = {}
for r in csv.DictReader(open("parity.csv", encoding="utf-8")):
    bid = r["bet_id"]
    meta[bid] = (r["subject"], ts(r["t"]))
    groups[bid].append(
        Row(
            mint=r["mint"],
            as_of=ts(r["as_of"]),
            computed_at=ts(r["computed_at"]),
            tape_as_of=ts(r["tape_as_of"]) if r["tape_as_of"] else None,
            values={
                "buys": Decimal(r["buys_60s"]) if r["buys_60s"] else None,
                "dprog": Decimal(r["progress_delta_60s"]) if r["progress_delta_60s"] else None,
            },
        )
    )

sql = {r["bet_id"]: r for r in csv.DictReader(open("pct.csv", encoding="utf-8"))}

VARS = [("buys", "p_buys"), ("dprog", "p_dprog")]
ok = bad = 0
null_subject = 0
leak_rows = leak_changed = 0
for bid, rows in groups.items():
    subject, t = meta[bid]
    coh = live_cohort(rows, t)
    for var, col in VARS:
        p = percentile(coh, subject, var)
        ref = sql[bid][col]
        if p is None:
            null_subject += 1
        if p is None and not ref:
            ok += 1
            continue
        if p is not None and ref and abs(float(p) - float(ref)) < 1e-9:
            ok += 1
        else:
            bad += 1
            print("DIVERGE", bid, col, p, ref, "cohort_n", len(coh) - 1, "sql", sql[bid]["cohort_n"])
    p = percentile(coh, subject, "buys")
    # quanto o futuro mudaria se a guarda nao existisse
    naive: dict[str, Row] = {}
    for r in rows:
        if r.as_of > t:
            continue  # so remove a guarda de computed_at
        if r.as_of <= t - __import__("cohort").WINDOW:
            continue
        cur = naive.get(r.mint)
        if cur is None or r.as_of > cur.as_of:
            naive[r.mint] = r
    leak = [m for m, r in naive.items() if r.computed_at > t]
    leak_rows += len(leak)
    pn = percentile(naive, subject, "buys")
    if (pn is None) != (p is None) or (pn is not None and p is not None and pn != p):
        leak_changed += 1

print(f"paridade: {ok} iguais, {bad} divergentes, em {len(groups)} decisoes x {len(VARS)} variaveis")
print(f"  contrastes com sujeito SEM valor (o caso que escondeu o erro): {null_subject}")
print(f"guarda computed_at: {leak_rows} linhas de coorte seriam admitidas sem ela")
print(f"percentil mudaria em {leak_changed} das {len(groups)} decisoes sem a guarda")
