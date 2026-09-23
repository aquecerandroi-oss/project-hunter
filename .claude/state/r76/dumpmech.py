"""R76 — EXPLORATÓRIO: nos despejos coordenados, o criador vende no mesmo slot? As vendedoras eram compradoras pré-decisão?"""
import json, sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import load as L
rows = json.loads((L.HERE / "rows.json").read_text(encoding="utf-8"))
pop = {r["bet_id"]: r for r in L.load_rows()}
tape = L.r73.load_tape(L.HERE / "tape.csv")
funding, _ = L.load_funding()
out = defaultdict(int); fr = []
for r in rows:
    if not r["dump"] or not (r["group"] == "pop" and r["eligible"] or r["group"] == "live_all"):
        continue
    raw = pop[r["bet_id"]]; creator = raw["creator"]
    tp = tape.get(r["mint"], []); dec = L.ts(r["decided_at"])
    entry = L.ts(raw["entry_at"])
    per = defaultdict(set)
    for t in tp:
        if t.side == "sell" and entry - timedelta(seconds=2) <= t.block_time <= entry + timedelta(seconds=300) and t.trader != L.OUR:
            per[t.slot].add(t.trader)
    slot, sellers = max(per.items(), key=lambda kv: len(kv[1]))
    pre = set(L.pre_decision_buyers(tp, dec))
    key = f"{r['group']}"
    out[key + " despejos"] += 1
    out[key + " criador vende no slot"] += creator in sellers
    fs = [funding[s].funder for s in sellers if s in funding]
    from collections import Counter
    top = Counter(fs).most_common(1)[0][1] if fs else 0
    fr.append((r["group"], r["symbol"], len(sellers), len(sellers & pre), creator in sellers, top, len(fs)))
for k, v in sorted(out.items()): print(k, v)
print("grupo | símbolo | vendedoras no slot | eram compradoras pré-decisão | criador no slot | maior grupo de financiador entre as vendedoras resolvidas | resolvidas")
for x in sorted(fr, key=lambda x: -x[2])[:20]: print(x)
