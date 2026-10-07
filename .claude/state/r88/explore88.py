"""R88 — EXPLORATÓRIO, fora do veredito (pós-execução): o golpe a mais no braço alto de B vem do criador ser o maior comprador?"""
import sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run88 import load, THR
rows = [r for r in load() if r["medida"] == "B" and r["cls"] in ("measured", "indeterminate")]
g = defaultdict(list)
for r in rows:
    g[(float(r["share_f"]) > THR["B"], r.get("is_creator") == "true")].append(r)
print("braço alto?, criador é o maior comprador? -> n, golpe %, r médio (measured), perda>=50 %")
for k in sorted(g):
    v = g[k]
    meas = [float(r["y"]) for r in v if r["cls"] == "measured"]
    golpe = sum(r.get("exit_reason") == "creator_dump" for r in v)
    big = sum(1 for y in meas if y <= -0.5)
    print(k, len(v), f"{100*golpe/len(v):.1f}%", f"{sum(meas)/len(meas):+.4f}", f"{100*big/len(v):.1f}%")
ex = defaultdict(int)
for r in rows:
    ex[(float(r["share_f"]) > THR["B"], r.get("exit_reason"))] += 1
print("saídas por braço:", {k: v for k, v in sorted(ex.items(), key=lambda kv: (kv[0][0], -kv[1]))})
