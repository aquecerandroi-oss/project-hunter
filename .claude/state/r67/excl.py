"""R67 - sensibilidade das exclusoes `indeterminate` (pendencia apontada pela Astra no veredito).

A fatia principal exclui apostas com `outcome_quality='indeterminate'`. Se as indeterminadas
nao forem um sorteio, a media do balde que perde mais delas melhora artificialmente.
Aqui reponho-as com (a) ret = 0 e (b) o pior caso possivel para a hipotese.
"""
import csv
from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

from load67 import load_paper
from oos import dedup, lo, r65_mints
from stats67 import cluster_boot_diff, mean, median, pct, perm_p_strat

HERE = Path(__file__).resolve().parent
BRT = timezone(timedelta(hours=-3))
OUT = []


def p(s=""):
    OUT.append(s)


def indeterminate_rows(excl):
    """Indeterminadas sujeitas a MESMA selecao da fatia principal (flow_v2, sem mints do R65)."""
    from load67 import _ts
    out = []
    for r in csv.DictReader(open(HERE / "paper.csv", newline="", encoding="utf-8")):
        if r["outcome_quality"] != "indeterminate" or not r["arm"].startswith("flow_v2"):
            continue
        if r["shared_live"] == "t" or r["mint"] in excl or not (r["buys_1m"] or "").strip():
            continue
        entry = _ts(r["entry_at"])
        pnl = Decimal(r["pnl_sol"]) if (r["pnl_sol"] or "").strip() else None
        size = Decimal(r["size_sol"] or "0.05")
        out.append(dict(mint=r["mint"], arm=r["arm"], entry_at=entry,
                        day=entry.astimezone(BRT).date().isoformat(),
                        buys_1m=float(r["buys_1m"]), hold_s=None, hit15=None,
                        ret=float(pnl / size) if pnl is not None else None,
                        pnl_sol=pnl, size_sol=size, reason=r["exit_reason"] or ""))
    return out


def report(rows, label):
    a = [r["ret"] for r in rows if lo(r)]
    b = [r["ret"] for r in rows if not lo(r)]
    ci_lo, ci_hi, pneg, _ = cluster_boot_diff(rows, "mint", lo, "ret")
    p("  %-38s n=%4d/%4d  D=%+.4f  IC95[%+.4f,%+.4f]  P(D<=0)=%.3f  p=%.4f"
      % (label, len(a), len(b), mean(a) - mean(b), ci_lo, ci_hi, pneg, perm_p_strat(rows, lo, "ret")))


def main():
    excl = r65_mints()
    paper = load_paper()
    base = dedup([r for r in paper if r["arm"].startswith("flow_v2") and r["mint"] not in excl])
    known = {r["mint"] for r in base}
    ind = [r for r in indeterminate_rows(excl) if r["mint"] not in known]
    seen, ind_d = set(), []
    for r in sorted(ind, key=lambda x: x["entry_at"]):
        if r["mint"] not in seen:
            seen.add(r["mint"])
            ind_d.append(r)

    p("fatia principal (measured): n=%d | indeterminadas em mints NAO representados: n=%d (%.1f %% do total)"
      % (len(base), len(ind_d), 100 * len(ind_d) / (len(base) + len(ind_d))))
    p("  <=25 entre as indeterminadas: %.1f %%   (fatia principal: %.1f %%)"
      % (100 * mean([1.0 if lo(r) else 0.0 for r in ind_d]),
         100 * mean([1.0 if lo(r) else 0.0 for r in base])))
    p("  motivo de saida das indeterminadas: %s"
      % sorted({(r["reason"] or "sem saida") for r in ind_d}))
    p("  com pnl_sol gravado: %d de %d" % (sum(1 for r in ind_d if r["ret"] is not None), len(ind_d)))
    p("  por dia (indeterminadas <=25 / >25):")
    for d in sorted({r["day"] for r in ind_d}):
        s = [r for r in ind_d if r["day"] == d]
        p("    %s  %d/%d" % (d, sum(1 for r in s if lo(r)), sum(1 for r in s if not lo(r))))
    p()
    p("D da fatia principal com as indeterminadas REPOSTAS:")
    report(base, "(0) so measured - referencia")
    z = [dict(r, ret=0.0) for r in ind_d]
    report(base + z, "(a) indeterminadas com ret = 0")
    lo_q = pct([r["ret"] for r in base], 0.10)
    hi_q = pct([r["ret"] for r in base], 0.90)
    worst = [dict(r, ret=(lo_q if lo(r) else hi_q)) for r in ind_d]
    report(base + worst, "(b) pior caso (p10 no <=25, p90 no >25)")
    best = [dict(r, ret=(hi_q if lo(r) else lo_q)) for r in ind_d]
    report(base + best, "(c) melhor caso (simetrico, so por simetria)")
    p("  p10/p90 do ret da fatia principal usados no pior/melhor caso: %+.4f / %+.4f" % (lo_q, hi_q))
    p()
    p("mediana do ret por balde na fatia principal: <=25 %+.4f | >25 %+.4f"
      % (median([r["ret"] for r in base if lo(r)]), median([r["ret"] for r in base if not lo(r)])))
    txt = "\n".join(OUT)
    (HERE / "excl.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
