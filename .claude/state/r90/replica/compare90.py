"""R90 réplica — concordância por sinal de oi_rel7d: SQL (feat2_15.csv, percentile_cont) × Python cru (replica90.oi_rel)."""
import csv
import math

from replica90 import HERE, UP, epoch, load_oi, oi_rel

el = {r["signal_id"] for r in csv.DictReader((UP / "eligible.csv").open(encoding="utf-8")) if r["strategy"] == "momentum"}
oi = load_oi(HERE / "cache" / "oi_raw.csv")
d, n = [], 0
for r in csv.DictReader((UP / "feat2_15.csv").open(encoding="utf-8")):
    if r["signal_id"] in el:
        sql = math.log(float(r["oi_cur"])) - float(r["med_ln_oi"])
        d.append(abs(sql - oi_rel(*oi[r["market_id"]], epoch(r["obs"]))))
        n += 1
print(f"sinais {n} | max |SQL − réplica| = {max(d):.3e} | > 1e-9: {sum(x > 1e-9 for x in d)}")
