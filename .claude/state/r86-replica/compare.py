"""r86-replica — comparação com o primário (lido só depois de out_replica.txt salvo, md5 0eaedb8b…).

Compara dados, não código: conjunto elegível, painel diário e covariáveis da janela de 24 h.
"""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from replica import enrich, load, ts

P = Path(__file__).parent.parent / "r86" / "cache"


def main():
    sig, days, win = load()
    rows = enrich(sig, days, win)
    mine = {r["signal_id"]: r for r in rows if r["rn"] is not None and r["razao"] is not None
            and r["dlow"] is not None and r["r4"] is not None and r["atr"] is not None}
    theirs = {r["signal_id"]: r["strategy"] for r in csv.DictReader(open(P / "eligible.csv", encoding="utf-8"))}
    print("elegíveis: meus", len(mine), "deles", len(theirs), "só meus", len(mine.keys() - theirs.keys()),
          "só deles", len(theirs.keys() - mine.keys()))
    print("  por estratégia meus", Counter(r["strategy"] for r in mine.values()), "deles", Counter(theirs.values()))
    for sid in sorted(mine.keys() ^ theirs.keys())[:10]:
        print("  diferença", sid, mine.get(sid, {}).get("strategy"), theirs.get(sid))

    # painel diário: (mercado, dia) em comum
    td = {}
    for f in sorted(P.glob("daily_*.csv")):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            td[(r["market_id"], date.fromisoformat(r["day"]))] = r
    common = diff_n = diff_c = diff_r = 0
    for mid, dd in days.items():
        for d, a in dd.items():
            t = td.get((mid, d))
            if t is None:
                continue
            common += 1
            diff_n += int(t["n_final"]) != a.n_final
            tc = Decimal(t["close_2359"]) if t["close_2359"] else None
            diff_c += tc != a.c2359
            diff_r += ts(t["max_recv"]) != a.max_recv_final
    mine_keys = {(m, d) for m, dd in days.items() for d in dd}
    print(f"diário: (mercado, dia) em comum {common}; n_final ≠ {diff_n}; fechamento 23:59 ≠ {diff_c}; "
          f"max_recv ≠ {diff_r}; meus sem par {len(mine_keys - td.keys())}")
    diffs = [(m, d) for (m, d) in mine_keys & td.keys() if int(td[(m, d)]["n_final"]) != days[m][d].n_final]
    for m, d in sorted(diffs, key=lambda x: x[1])[:8]:
        print("  n_final difere", m[-6:], d, "meu", days[m][d].n_final, "deles", td[(m, d)]["n_final"])

    # janela de 24 h por sinal
    tf = {r["signal_id"]: r for r in csv.DictReader(open(P / "feat.csv", encoding="utf-8"))}
    print("feat.csv deles:", len(tf), "sinais; meus win:", len(win), "; em comum", len(tf.keys() & win.keys()))
    atr_of = {s["signal_id"]: s["atr_pct"] for s in sig}
    bad = Counter()
    for sid, w in win.items():
        t = tf.get(sid)
        if t is None:
            bad["sem_par"] += 1
            continue
        bad["n"] += int(t["n"]) != w["n"]
        bad["lo"] += (Decimal(t["lo24"]) if t["lo24"] else None) != w["lo"]
        bad["max_recv"] += ts(t["max_recv"]) != w["max_recv"]
        bad["c_m1"] += (Decimal(t["close_last"]) if t["close_last"] else None) != w["c_m1"]
        bad["c_m241"] += (Decimal(t["close_m240"]) if t["close_m240"] else None) != w["c_m241"]
        bad["atr"] += t["env_atr_pct"] != atr_of[sid]
    print("janela 24 h, divergências por campo:", dict(bad))
    # guarda de 24 h, contagem não exclusiva
    g = Counter(r["strategy"] for r in rows if r["why_w"] == "guarda_24h")
    print("guarda 24 h (não exclusiva):", dict(g), "total", sum(g.values()))


if __name__ == "__main__":
    main()
