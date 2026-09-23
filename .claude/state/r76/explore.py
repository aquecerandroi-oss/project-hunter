"""R76 — EXPLORATÓRIO (fora do veredito): confusão com nº de compradoras, AUC do bundle com IC, AIRAA."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run as R
import report as RP
rows = json.loads((R.HERE / "rows.json").read_text(encoding="utf-8"))
for r in rows:
    if r.get("censor") not in (None, "None"):
        r["sim_ret"] = None
el = [r for r in rows if r["group"] == "pop" and r["eligible"] and r["sim_ret"] is not None and r["pct"] is not None]
print("n", len(el))
med = float(np.median([r["n_buyers"] for r in el]))
print(f"mediana de compradoras {med}")
for lab, sub in (("poucas compradoras (≤ mediana)", [r for r in el if r["n_buyers"] <= med]),
                 ("muitas compradoras (> mediana)", [r for r in el if r["n_buyers"] > med])):
    z = [r for r in sub if r["pct"] == 0]; nz = [r for r in sub if r["pct"] > 0]
    y0 = np.mean([r["sim_ret"] for r in z]) if z else float("nan")
    y1 = np.mean([r["sim_ret"] for r in nz]) if nz else float("nan")
    m = np.array([r["pct"] == 0 for r in sub])
    iv = R.cluster_bootstrap(np.array([r["sim_ret"] for r in sub]), m, [r["mint"] for r in sub], reps=10000, seed=761)
    print(f"{lab}: n={len(sub)} rede=0: {len(z)} média {y0:+.4f} | rede>0: {len(nz)} média {y1:+.4f} | D(0 − >0) {y0 - y1:+.4f} IC [{iv.lo:+.4f}, {iv.hi:+.4f}]")
print("Spearman(n_buyers, rede)", round(RP.spearman([r["n_buyers"] for r in el], [r["pct"] for r in el]), 3),
      "Spearman(n_buyers, ret)", round(RP.spearman([r["n_buyers"] for r in el], [r["sim_ret"] for r in el]), 3))
# AUC do bundle para perda >= 50 %, com bootstrap por mint
big = [r["sim_ret"] <= -0.5 for r in el]
print("perdas >= 50 % (simulador):", sum(big), "de", len(el), "| despejos:", sum(bool(r["dump"]) for r in el))
rng = np.random.default_rng(76)
for p in ("p_bundle_sol", "p_bundle", "p_holders_frac"):
    x = np.array([float(r[p]) if r[p] is not None else np.nan for r in el]); y = np.array(big)
    ok = ~np.isnan(x); x, y = x[ok], y[ok]
    a0 = RP.auc(x, y)
    bs = []
    for _ in range(2000):
        i = rng.integers(0, len(x), len(x))
        if y[i].any() and not y[i].all():
            bs.append(RP.auc(x[i], y[i]))
    print(f"AUC {p} perda>=50%: {a0:.3f} IC95 [{np.quantile(bs, .025):.3f}, {np.quantile(bs, .975):.3f}]")
    yd = np.array([bool(r["dump"]) for r in el])[ok]
    bs = []
    for _ in range(2000):
        i = rng.integers(0, len(x), len(x))
        bs.append(RP.auc(x[i], yd[i]))
    print(f"AUC {p} despejo: {RP.auc(x, yd):.3f} IC95 [{np.nanquantile(bs, .025):.3f}, {np.nanquantile(bs, .975):.3f}]")
for r in rows:
    if r["symbol"] in ("AIRAA", "WEENY", "RESERVED") and r["group"] == "live_all":
        print(r["symbol"], "compradoras", r["n_buyers"], "maior grupo", r["max_group"], "financiador", r["top_funder"],
              "rede", round(r["pct"] or 0, 3), "s1", round(r["s1_pct"] or 0, 3), "criador", r["creator_pct"], "pnl", r["pnl_sol"])

# quem encabeça o maior grupo no tercil alto (principal)
import re
from collections import Counter
ident = {json.loads(l)["w"]: json.loads(l) for l in open(R.HERE / "cache_identity.jsonl", encoding="utf-8")}
xf = {}
for p in sorted(R.HERE.glob("cache_xfers*.jsonl")):
    for l in open(p, encoding="utf-8"):
        o = json.loads(l); xf[o["funder"]] = o
q2 = np.quantile([r["pct"] for r in el], 2 / 3)
hi = [r for r in el if r["pct"] > q2]
kinds = Counter()
by_funder = Counter(r["top_funder"] for r in hi)
for r in hi:
    f = r["top_funder"]; o = ident.get(f, {})
    x = xf.get(f)
    st = "sem xfers" if x is None else ("esgotado ≤1000" if x["exhausted"] else "desconhecido (15 págs.)")
    kinds[(o.get("category") or "sem rótulo", st)] += 1
print("tercil alto:", len(hi), "mints; financiadores distintos a encabeçar:", len(by_funder))
for k, v in kinds.most_common(): print("  ", k, v)
print("financiadores que encabeçam >= 3 mints do tercil alto:")
for f, n in by_funder.most_common(8):
    o = ident.get(f, {}); x = xf.get(f, {})
    print("  ", f[:8], n, o.get("name"), o.get("category"), (o.get("tags") or [])[:2], "xfers distintos", x.get("distinct"), "págs", x.get("pages"), "esgotado", x.get("exhausted"))

# D sem os mints encabeçados pelos dois financiadores recorrentes (exploratório)
rec2 = {"H7sWT7eP83vkim7Gp81qsPwQzuzJK3E6Ps9KLbUezoCc", "AgmLJBMDCqWynYnQiPCuj9ewsNNsBJXyzoUhD9LJzN51"}
lo = [r for r in el if r["pct"] <= np.quantile([x["pct"] for x in el], 1 / 3)]
for lab, h in (("alto, só H7sWT7eP/FOMO", [r for r in hi if r["top_funder"] in rec2]),
               ("alto, sem eles", [r for r in hi if r["top_funder"] not in rec2])):
    sub = lo + h
    m = np.array([r in lo for r in sub])
    y = np.array([r["sim_ret"] for r in sub])
    iv = R.cluster_bootstrap(y, m, [r["mint"] for r in sub], reps=10000, seed=762)
    print(f"{lab}: n alto {len(h)} média {np.mean([r['sim_ret'] for r in h]):+.4f}; D(baixo − este) {y[m].mean() - y[~m].mean():+.4f} IC [{iv.lo:+.4f}, {iv.hi:+.4f}]; despejos {sum(bool(r['dump']) for r in h)}")
print("dias dos mints H7sWT7eP:", Counter(r["dia"] for r in hi if r["top_funder"] == "H7sWT7eP83vkim7Gp81qsPwQzuzJK3E6Ps9KLbUezoCc"))
