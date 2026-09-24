"""R77 — de onde vem a distância entre o controlo simulado (+0,4 %) e o PnL real (−5,4 %) nas 65 reais.

Decomposição: PnL real por SOL → R72 no fill real (gasto com aluguel/taxas, saída congelada) → R72 no fill
real com gasto nominal → controlo do R77 (compra modelada em t0 + 1,6 s na cadeia sem nós).
Uso: cd .claude/state/r77 && uv run --project ../../.. python fidelity.py > fidelity.txt
"""

from __future__ import annotations

import csv
import json
import statistics as st
from decimal import Decimal

from chain import load_photos, load_tape, ts
from entry import r72, sim
from report import eligible, load
from sim_all import HERE, own_fills, with_own


def main() -> None:
    recs = {r["bet_id"]: r for r in load() if r["pop"] == "real" and eligible(r)}
    with (HERE / "pop.csv").open(encoding="utf-8", newline="") as f:
        rows = {r["bet_id"]: r for r in csv.DictReader(f) if r["bet_id"] in recs}
    tapes, photos, own = load_tape(), load_photos(), own_fills()
    out = []
    for bid, rec in recs.items():
        r = rows[bid]
        e = json.loads(r["entry_json"])
        tape, _ = with_own(tapes.get(("real", r["mint"]), []), own.get(r["mint"], []))
        base = dict(mint=r["mint"], tokens=int(e["token_amount"]), entry_slot=int(e["slot"]),
                    entry_bt=ts(e["block_time"]), vsol0=int(e["virtual_sol_reserves_after"]),
                    vtok0=int(e["virtual_token_reserves_after"]))
        P = dict(base, spent=int(r["spent_lamports"]))
        r72.build_path(P, {r["mint"]: tape}, {r["mint"]: photos.get(("real", r["mint"]), [])})
        res = sim.simulate_current(P)
        full = sim.per_sol(res, P)
        ata = int(e.get("ata_rent_lamports") or 0)
        Pn = dict(P, spent=int(r["spent_lamports"]) - ata)
        nominal = sim.per_sol(sim.simulate_current(Pn), Pn)
        out.append(dict(sym=rec["sym"], hist=rec["hist_ret"], full=None if full is None else float(full),
                        noata=None if nominal is None else float(nominal), ctrl=rec["arms"]["ctrl@1.6"]["ret"],
                        lag=(base["entry_bt"] - ts(rec["t0"])).total_seconds(),
                        params=json.loads(r["params"] or "{}")))
    ok = [o for o in out if o["full"] is not None and o["noata"] is not None]
    print("n = %d (de %d elegíveis; R72 não resolveu %d)" % (len(ok), len(out), len(out) - len(ok)))
    for k, name in (("hist", "PnL real por SOL (gasto total, saída histórica)"),
                    ("full", "R72 no fill real, gasto total com aluguel (saída congelada)"),
                    ("noata", "R72 no fill real, gasto sem aluguel de ATA (saída congelada)"),
                    ("ctrl", "controlo R77 (compra modelada em t0 + 1,6 s)")):
        print("  %-62s média %+.4f  mediana %+.4f" % (name, st.mean(o[k] for o in ok), st.median(o[k] for o in ok)))
    print("  correlação R72-sem-aluguel × controlo R77: %.2f" % st.correlation([o["noata"] for o in ok],
                                                                             [o["ctrl"] for o in ok]))
    diffs = sorted((o["ctrl"] - o["noata"], o["sym"], o["lag"]) for o in ok)
    print("  controlo R77 − R72 sem aluguel: média %+.4f, mediana %+.4f" % (
        st.mean(d[0] for d in diffs), st.median(d[0] for d in diffs)))
    print("  atraso fill real − t0 (s): mediana %.1f, min %.1f, max %.1f" % (
        st.median(o["lag"] for o in ok), min(o["lag"] for o in ok), max(o["lag"] for o in ok)))
    hist_rules = sum(1 for o in ok if Decimal(str(o["params"].get("target_x", "1.15"))) != Decimal("1.15")
                     or str(o["params"].get("trailing_pct", "10")) not in ("10", "10.0"))
    print("  posições com saída histórica diferente da congelada (alvo ≠ 1,15 ou recuo ≠ 10 %%): %d" % hist_rules)
    print("  maiores diferenças (controlo R77 − R72 sem aluguel):")
    for d, s, lag in diffs[:4] + diffs[-4:]:
        print("    %-12s %+.4f  (fill real %+.1f s depois de t0)" % (s, d, lag))


if __name__ == "__main__":
    main()
